#!/usr/bin/env python3
"""
setup-gitlab-ci-runners.py - provision the demo "Coder templates" GitLab CI
pipeline and the GitLab Runner authentication token for the usgov-coderdemo
GovCloud demo.

What it does (idempotent; re-running reconciles in place):

  1. Coder: log in to https://dev.usgov.coderdemo.io as the admin owner
     (CODER_ADMIN_EMAIL / CODER_ADMIN_PASSWORD), rotate a named API token
     ("gitlab-ci") at the server's maximum allowed lifetime, and capture it for
     the GitLab CI/CD variable. The token grants template-admin rights in the
     target org (the owner is template admin everywhere).

  2. GitLab (via gitlab-rails inside the gitlab-0 pod, the established admin
     pattern): create the project root/coder-templates, seed it from
     deploy/gitlab-runner/coder-templates-example/ (a working Coder template +
     .gitlab-ci.yml), protect the default branch, set the CODER_SESSION_TOKEN
     CI/CD variable (masked + protected), and create a PROJECT runner
     authentication token (glrt-...).

  3. AWS Secrets Manager: upsert the runner authentication token into
     usgov-coderdemo/gitlab/runner as {"runner-token": "...",
     "runner-registration-token": ""}, the source of truth that ESO syncs into
     the gitlab-runner namespace (deploy/gitlab-runner/externalsecret.yaml).

No secret value is ever printed or written to git. The Coder admin password is
read from ~/.config/usgov-coderdemo/generated-secrets.env. The Coder token is
passed to gitlab-rails over stdin -> env (never argv). The runner token is
written to a 0600 file inside the pod and retrieved over a captured exec, then
removed.

Istio note: this script only configures GitLab/Coder/ASM. The runner itself is
deployed by Helm (deploy/gitlab-runner/values.yaml) into the non-meshed
gitlab-runner namespace and reaches GitLab/Coder over their external gateway
URLs, so mesh-wide STRICT mTLS is satisfied.

Usage (from the repo root, with the demo kubeconfig + env):
    . ~/.config/usgov-coderdemo/env
    export KUBECONFIG=/home/coder/demoenv-workspace/usgov-coderdemo/kubeconfig
    python3 scripts/setup-gitlab-ci-runners.py
"""
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

# --- Configuration -----------------------------------------------------------
NAMESPACE = "gitlab"
POD = "gitlab-0"
CONTAINER = "gitlab"  # the omnibus container (gitlab-0 also runs an istio sidecar)

CODER_URL = "https://dev.usgov.coderdemo.io"
CODER_TOKEN_NAME = "gitlab-ci"

PROJECT_PATH = "root/coder-templates"
PROJECT_NAME = "coder-templates"
PROJECT_DESC = "Demo: GitOps for Coder templates (CI pushes to Coder)."
RUNNER_DESC = "coder-templates k8s runner (usgov-coderdemo demo)"

REGION = "us-gov-west-1"
ASM_RUNNER = "usgov-coderdemo/gitlab/runner"

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEED_DIR = os.path.join(REPO_ROOT, "deploy", "gitlab-runner",
                        "coder-templates-example")

POD_SEED_DIR = "/tmp/coder-templates-seed"
POD_TOKEN_FILE = "/tmp/gl-runner-token"


# --- Secrets -----------------------------------------------------------------
def read_secret(*keys):
    """Read selected keys from generated-secrets.env without echoing values."""
    path = os.path.expanduser("~/.config/usgov-coderdemo/generated-secrets.env")
    out = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                if k in keys:
                    out[k] = v
    missing = [k for k in keys if k not in out]
    if missing:
        print(f"missing secrets in generated-secrets.env: {missing}",
              file=sys.stderr)
        sys.exit(1)
    return out


# --- Coder API ---------------------------------------------------------------
def coder_request(method, path, token=None, body=None):
    headers = {}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    if token:
        headers["Coder-Session-Token"] = token
    req = urllib.request.Request(CODER_URL + path, data=data,
                                 headers=headers, method=method)
    try:
        r = urllib.request.urlopen(req)
        raw = r.read().decode()
        return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def coder_login(email, password):
    status, body = coder_request(
        "POST", "/api/v2/users/login",
        body={"email": email, "password": password})
    if status != 201 or not isinstance(body, dict) or "session_token" not in body:
        print(f"Coder login failed (HTTP {status})", file=sys.stderr)
        sys.exit(1)
    return body["session_token"]


def coder_rotate_token(session):
    """Delete any existing CI token of the same name, then create a fresh one
    at the server's maximum allowed lifetime. Returns the new token string."""
    # Look up the server's max token lifetime (nanoseconds).
    status, cfg = coder_request(
        "GET", "/api/v2/users/me/keys/tokens/tokenconfig", token=session)
    max_lifetime = 0
    if status == 200 and isinstance(cfg, dict):
        max_lifetime = int(cfg.get("max_token_lifetime", 0))
    # Delete an existing token of the same name (rotate).
    status, tokens = coder_request(
        "GET", "/api/v2/users/me/keys/tokens", token=session)
    if status == 200 and isinstance(tokens, list):
        for t in tokens:
            if t.get("token_name") == CODER_TOKEN_NAME:
                coder_request("DELETE", f"/api/v2/users/me/keys/{t['id']}",
                              token=session)
                print(f"Coder token '{CODER_TOKEN_NAME}': rotated "
                      f"(deleted prior id {t['id'][:8]})")
    body = {"token_name": CODER_TOKEN_NAME, "scope": "all"}
    if max_lifetime > 0:
        body["lifetime"] = max_lifetime
    status, created = coder_request(
        "POST", "/api/v2/users/me/keys/tokens", token=session, body=body)
    if status != 201 or not isinstance(created, dict) or "key" not in created:
        print(f"Coder token create failed (HTTP {status}): {created}",
              file=sys.stderr)
        sys.exit(1)
    days = max_lifetime / (1e9 * 86400) if max_lifetime else 0
    print(f"Coder token '{CODER_TOKEN_NAME}': created "
          f"(scope=all, lifetime~{days:.0f}d)")
    return created["key"]


# --- kubectl helpers ---------------------------------------------------------
def kubectl(args, stdin_data=None, capture=True):
    return subprocess.run(
        ["kubectl", "-n", NAMESPACE, *args],
        input=stdin_data, text=True,
        capture_output=capture)


def rails(ruby, env_lines=None):
    """Run a Ruby script via gitlab-rails. The script is staged on stdin so no
    code or secret is on the command line. Optional env_lines (list of values)
    are read by a tiny shell shim into env vars before exec, matching the
    setup-gitlab-users.py pattern."""
    stage = kubectl(["exec", "-i", "-c", CONTAINER, POD, "--",
                     "sh", "-c", "cat > /tmp/_ci_setup.rb"], stdin_data=ruby)
    if stage.returncode != 0:
        print(stage.stderr, file=sys.stderr)
        sys.exit(1)
    if env_lines is None:
        shell = ("gitlab-rails runner /tmp/_ci_setup.rb; rc=$?; "
                 "rm -f /tmp/_ci_setup.rb; exit $rc")
        r = kubectl(["exec", "-i", "-c", CONTAINER, POD, "--", "sh", "-c", shell])
    else:
        # First line read into CODER_SESSION_TOKEN, passed via env (not argv).
        shell = ("read -r CST; "
                 "CODER_SESSION_TOKEN=\"$CST\" "
                 "gitlab-rails runner /tmp/_ci_setup.rb; rc=$?; "
                 "rm -f /tmp/_ci_setup.rb; exit $rc")
        r = kubectl(["exec", "-i", "-c", CONTAINER, POD, "--", "sh", "-c", shell],
                    stdin_data="\n".join(env_lines) + "\n")
    return r


# --- Ruby payloads -----------------------------------------------------------
RUBY_PROJECT_AND_RUNNER = r'''
root = User.find_by(username: "root") or abort("root user not found")

path  = "%(name)s"
full  = "%(full)s"
# Find or create the project in root's personal namespace.
project = Project.find_by_full_path(full)
if project.nil?
  res = ::Projects::CreateService.new(
    root,
    name: path, path: path,
    namespace_id: root.namespace.id,
    description: "%(desc)s",
    visibility_level: Gitlab::VisibilityLevel::PRIVATE,
    initialize_with_readme: false
  ).execute
  project = res.is_a?(Project) ? res : (res[:project] if res.respond_to?(:[]))
  abort("project create failed") unless project&.persisted?
  puts "project #{full}: CREATED id=#{project.id}"
else
  puts "project #{full}: exists id=#{project.id}"
end

# Seed files from the staged directory. Only files that are new or whose
# content differs become commit actions, so a re-run with identical content is
# a true no-op (no empty commit, no redundant pipeline).
branch = project.default_branch || "main"
seed = "%(seed)s"
actions = []
Dir.glob(File.join(seed, "**", "*"), File::FNM_DOTMATCH).each do |fp|
  next if File.directory?(fp)
  rel = fp.sub(/\A#{Regexp.escape(seed)}\/?/, "")
  next if rel.empty?
  content = File.binread(fp)
  blob = project.empty_repo? ? nil : project.repository.blob_at(branch, rel)
  if blob.nil?
    actions << { action: "create", file_path: rel, content: content }
  elsif blob.data.b != content.b
    actions << { action: "update", file_path: rel, content: content }
  end
end
actions.sort_by! { |a| a[:file_path] }
if actions.empty?
  puts "seed: no changes (already up to date)"
else
  start = project.empty_repo? ? nil : branch
  res = ::Files::MultiService.new(
    project, root,
    start_branch: start, branch_name: branch,
    commit_message: "chore: seed coder-templates demo (Coder Agents)",
    actions: actions
  ).execute
  if res[:status] == :success
    puts "seed: committed #{actions.length} file(s) to #{branch}"
  else
    puts "seed: ERROR #{res[:message]}"
  end
end

# Ensure the project has a default branch set and protect it (so masked +
# protected CI/CD variables are exposed to default-branch pipelines).
project.reload
db = project.default_branch || branch
project.change_head(db) if project.default_branch.nil?
unless project.protected_branches.exists?(name: db)
  ::ProtectedBranches::CreateService.new(
    project, root,
    name: db,
    push_access_levels_attributes: [{ access_level: Gitlab::Access::MAINTAINER }],
    merge_access_levels_attributes: [{ access_level: Gitlab::Access::MAINTAINER }]
  ).execute
  puts "protected branch: #{db}"
else
  puts "protected branch: #{db} (already)"
end

# Find or create the PROJECT runner authentication token.
runner = project.runners.find_by(description: "%(rdesc)s")
if runner.nil?
  resp = ::Ci::Runners::CreateRunnerService.new(
    user: root,
    params: {
      runner_type: "project_type", scope: project,
      description: "%(rdesc)s",
      tag_list: ["kubernetes", "coder"],
      run_untagged: true
    }
  ).execute
  abort("runner create failed: #{resp.message}") unless resp.success?
  runner = resp.payload[:runner]
  puts "runner: CREATED id=#{runner.id} type=#{runner.runner_type} untagged=#{runner.run_untagged}"
else
  puts "runner: exists id=#{runner.id} type=#{runner.runner_type}"
end

# Write the auth token to a 0600 file for out-of-band retrieval (never printed).
File.open("%(tokenfile)s", File::WRONLY | File::CREAT | File::TRUNC, 0o600) do |f|
  f.write(runner.token.to_s)
end
puts "runner token: staged (glrt prefix=#{runner.token.to_s.start_with?('glrt-')})"
'''

RUBY_SET_CI_VARIABLE = r'''
project = Project.find_by_full_path("%(full)s") or abort("project not found")
val = ENV["CODER_SESSION_TOKEN"].to_s
abort("CODER_SESSION_TOKEN empty") if val.empty?
key = "CODER_SESSION_TOKEN"
var = project.variables.find_or_initialize_by(key: key)
var.value = val
var.masked = true
var.protected = true
var.variable_type = "env_var"
var.save!
puts "ci variable #{key}: masked=#{var.masked} protected=#{var.protected}"
'''


# --- AWS Secrets Manager -----------------------------------------------------
def asm_exists(name):
    r = subprocess.run(
        ["aws", "secretsmanager", "describe-secret", "--region", REGION,
         "--secret-id", name],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return r.returncode == 0


def asm_put(name, payload):
    fd, path = tempfile.mkstemp(prefix="asm-", suffix=".json")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(payload, f)
        ref = "file://" + path
        if asm_exists(name):
            subprocess.run(
                ["aws", "secretsmanager", "put-secret-value", "--region", REGION,
                 "--secret-id", name, "--secret-string", ref],
                check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return "updated"
        subprocess.run(
            ["aws", "secretsmanager", "create-secret", "--region", REGION,
             "--name", name,
             "--description", "usgov-coderdemo GitLab Runner auth token (ESO).",
             "--secret-string", ref],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return "created"
    finally:
        os.unlink(path)


# --- Main --------------------------------------------------------------------
def main():
    secrets = read_secret("CODER_ADMIN_EMAIL", "CODER_ADMIN_PASSWORD")

    # 1. Coder token.
    session = coder_login(secrets["CODER_ADMIN_EMAIL"],
                          secrets["CODER_ADMIN_PASSWORD"])
    coder_token = coder_rotate_token(session)

    # 2. Stage the example project into the pod.
    if not os.path.isdir(SEED_DIR):
        print(f"seed dir not found: {SEED_DIR}", file=sys.stderr)
        sys.exit(1)
    kubectl(["exec", "-c", CONTAINER, POD, "--", "rm", "-rf", POD_SEED_DIR])
    cp = subprocess.run(
        ["kubectl", "-n", NAMESPACE, "cp", "-c", CONTAINER,
         SEED_DIR + "/.", f"{POD}:{POD_SEED_DIR}"],
        capture_output=True, text=True)
    if cp.returncode != 0:
        print("kubectl cp failed:\n" + cp.stderr, file=sys.stderr)
        sys.exit(1)
    print(f"staged example project -> {POD}:{POD_SEED_DIR}")

    # 3. Project + seed + protect + runner token.
    ruby = RUBY_PROJECT_AND_RUNNER % {
        "name": PROJECT_NAME, "full": PROJECT_PATH, "desc": PROJECT_DESC,
        "seed": POD_SEED_DIR, "rdesc": RUNNER_DESC, "tokenfile": POD_TOKEN_FILE,
    }
    r = rails(ruby)
    sys.stdout.write(r.stdout)
    if r.returncode != 0:
        sys.stderr.write(r.stderr)
        sys.exit(r.returncode)

    # 4. Retrieve the runner token (captured, never echoed) -> ASM.
    got = kubectl(["exec", "-i", "-c", CONTAINER, POD, "--",
                   "sh", "-c", f"cat {POD_TOKEN_FILE}"])
    runner_token = (got.stdout or "").strip()
    kubectl(["exec", "-c", CONTAINER, POD, "--", "rm", "-f", POD_TOKEN_FILE])
    if not runner_token.startswith("glrt-"):
        print("failed to retrieve a glrt- runner token", file=sys.stderr)
        sys.exit(1)
    action = asm_put(ASM_RUNNER, {
        "runner-token": runner_token,
        "runner-registration-token": "",
    })
    print(f"ASM {ASM_RUNNER}: {action} (runner-token, {len(runner_token)} chars)")

    # 5. Set the masked + protected CODER_SESSION_TOKEN CI/CD variable.
    ruby_var = RUBY_SET_CI_VARIABLE % {"full": PROJECT_PATH}
    r = rails(ruby_var, env_lines=[coder_token])
    sys.stdout.write(r.stdout)
    if r.returncode != 0:
        sys.stderr.write(r.stderr)
        sys.exit(r.returncode)

    # Cleanup staged files.
    kubectl(["exec", "-c", CONTAINER, POD, "--", "rm", "-rf", POD_SEED_DIR])

    print("\nDone. Next:")
    print("  kubectl apply -f deploy/gitlab-runner/namespace.yaml")
    print("  kubectl apply -f deploy/gitlab-runner/externalsecret.yaml")
    print("  helm upgrade --install gitlab-runner gitlab/gitlab-runner \\")
    print("    --version 0.89.1 --namespace gitlab-runner \\")
    print("    -f deploy/gitlab-runner/values.yaml")


if __name__ == "__main__":
    main()
