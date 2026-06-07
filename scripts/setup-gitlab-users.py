#!/usr/bin/env python3
"""
setup-gitlab-users.py - populate the in-boundary GitLab with the demo persona
users and set the GitLab instance admin attribute, since GitLab Community
Edition does not implement OIDC group-to-role assignment (admin_groups is an EE
feature and is a no-op on the CE image, see deploy/gitlab/statefulset.yaml).

Idempotent: re-running finds existing users (including any JIT-created by an SSO
login) and reconciles name, admin flag, active state, and the openid_connect
identity (extern_uid = username) so a Keycloak SSO login lands on the right
account. Mirrors the personas in scripts/setup-keycloak-hierarchy.py.

Mapping applied (mirrors the Coder org-admin role; only the operator super admin
gets GitLab instance admin, to preserve tenant isolation):
  austen.platform -> instance admin (operator super admin)
  all demo personas -> regular users

Runs gitlab-rails inside the gitlab-0 pod (ROPC/password grant is disabled, so a
REST token is not available without a bootstrap). The demo password is read from
~/.config/usgov-coderdemo/generated-secrets.env (DEMO_USER_PASSWORD) and passed
to the pod over stdin, never on the command line.

Usage (from the repo root, with the demo kubeconfig):
    . ~/.config/usgov-coderdemo/env && export KUBECONFIG=./kubeconfig
    python3 scripts/setup-gitlab-users.py
"""
import os
import subprocess
import sys

NAMESPACE = "gitlab"
POD = "gitlab-0"

RUBY = r'''
admin = User.find_by(username: "root")
org   = Organizations::Organization.default_organization
pwmap = {
  "DEMO_USER_PASSWORD"  => ENV["DEMO_USER_PASSWORD"].to_s,
  "SUPERADMIN_PASSWORD" => ENV["SUPERADMIN_PASSWORD"].to_s,
}

personas = [
  ["austen.platform", "Austen Platform", true,  "SUPERADMIN_PASSWORD"],
  ["pat.platform",    "Pat Rivera",      false, "DEMO_USER_PASSWORD"],
  ["sky.sre",         "Sky Nguyen",      false, "DEMO_USER_PASSWORD"],
  ["alex.admin",      "Alex Carter",     false, "DEMO_USER_PASSWORD"],
  ["dana.dev",        "Dana Brooks",     false, "DEMO_USER_PASSWORD"],
  ["quinn.data",      "Quinn Lee",       false, "DEMO_USER_PASSWORD"],
  ["morgan.isso",     "Morgan Diaz",     false, "DEMO_USER_PASSWORD"],
  ["riley.admin",     "Riley Fox",       false, "DEMO_USER_PASSWORD"],
  ["jordan.dev",      "Jordan Kim",      false, "DEMO_USER_PASSWORD"],
]

personas.each do |uname, fullname, is_admin, pw_env|
  pw = pwmap[pw_env].to_s
  abort("password #{pw_env} not provided") if pw.empty?
  email = "#{uname}@usgov.coderdemo.io"
  u = User.find_by(username: uname)
  if u.nil?
    res = Users::CreateService.new(
      admin,
      username: uname, email: email, name: fullname,
      password: pw, password_confirmation: pw,
      skip_confirmation: true, organization_id: org.id
    ).execute
    u = res.is_a?(User) ? res : User.find_by(username: uname)
    unless u&.persisted?
      puts "#{uname}: CREATE FAILED: #{u&.errors&.full_messages&.join('; ')}"
      next
    end
  end
  u.name  = fullname
  u.admin = is_admin
  u.state = "active"
  u.save!(validate: false)
  unless u.identities.exists?(provider: "openid_connect")
    u.identities.create!(provider: "openid_connect", extern_uid: uname)
  end
  puts "#{uname}: id=#{u.id} admin=#{u.admin} oidc=#{u.identities.where(provider: "openid_connect").first&.extern_uid}"
end
'''


def read_passwords():
    path = os.path.expanduser("~/.config/usgov-coderdemo/generated-secrets.env")
    out = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            for key in ("DEMO_USER_PASSWORD", "SUPERADMIN_PASSWORD"):
                if line.startswith(key + "="):
                    out[key] = line.split("=", 1)[1]
    if "DEMO_USER_PASSWORD" not in out:
        print("DEMO_USER_PASSWORD not found in generated-secrets.env", file=sys.stderr)
        sys.exit(1)
    return out["DEMO_USER_PASSWORD"], out.get("SUPERADMIN_PASSWORD", "")


def kubectl_exec(stdin_data, shell_cmd):
    return subprocess.run(
        ["kubectl", "-n", NAMESPACE, "exec", "-i", POD, "--", "sh", "-c", shell_cmd],
        input=stdin_data, text=True, capture_output=True)


def main():
    demo_pw, super_pw = read_passwords()
    # 1. Stage the Ruby script in the pod (contains no secret).
    r = kubectl_exec(RUBY, "cat > /tmp/setup-gitlab-users.rb")
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr)
        sys.exit(1)
    # 2. Run it with the passwords supplied over stdin -> env (not argv).
    r = kubectl_exec(
        demo_pw + "\n" + super_pw + "\n",
        'read -r DPW; read -r SPW; '
        'DEMO_USER_PASSWORD="$DPW" SUPERADMIN_PASSWORD="$SPW" '
        'gitlab-rails runner /tmp/setup-gitlab-users.rb; '
        'rc=$?; rm -f /tmp/setup-gitlab-users.rb; exit $rc')
    sys.stdout.write(r.stdout)
    if r.returncode != 0:
        sys.stderr.write(r.stderr)
        sys.exit(r.returncode)


if __name__ == "__main__":
    main()
