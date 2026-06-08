#!/usr/bin/env python3
"""
setup-pm-persona.py - create the project-manager (PM) demo persona end to end:
a Keycloak user in realm `coder`, the matching GitLab user, and a project
membership on `coderdemo/coder-templates` so the PM can create and assign the
issues that drive the WS-23 GitLab to Coder bridge (the assignee becomes the
Coder workspace/task owner when the issue carries a coder-workspace or
coder-agent label).

PERSONA
  Morgan Pierce, username `morgan.pm`, a non-technical coordinator who assigns
  work to developers. Intentionally a regular user (no Coder org-admin, no GitLab
  instance admin); the only elevated capability is GitLab project membership so
  they can open and assign issues. This mirrors the platform personas defined in
  scripts/setup-keycloak-hierarchy.py and scripts/setup-gitlab-users.py.

WHAT IT DOES (plan first, mutate only with --apply)
  Keycloak (realm `coder`, the SSO source of truth):
    - ensure user morgan.pm (firstName Morgan, lastName Pierce, verified email)
    - set a non-temporary password (see PASSWORD below)
    - add to the configured group(s) so Coder IdP sync grants org membership
  GitLab (REST API, https://gitlab.usgov.coderdemo.io/api/v4):
    - ensure user morgan.pm (JIT-style account reconciled to match Keycloak)
    - bind the openid_connect identity (extern_uid = username) so a Keycloak SSO
      login lands on the right account
    - add as a project member of coderdemo/coder-templates (id 2) at the
      configured access level (default Developer = 30; Reporter = 20 also works
      for creating and assigning issues)

PASSWORD
  Default: the shared DEMO_USER_PASSWORD from
  ~/.config/usgov-coderdemo/generated-secrets.env (same as the other personas).
  With --generate-password a fresh random password is generated once and stored
  in AWS Secrets Manager at usgov-coderdemo/persona/morgan-pm, then reused on
  later runs. The password value is never printed; only its length is shown.

GITLAB ADMIN CREDENTIAL
  The GitLab REST calls need an admin token. Resolution order:
    1. $GITLAB_ADMIN_PAT (a glpat- token), if set.
    2. AWS Secrets Manager secret usgov-coderdemo/gitlab/admin-pat
       (SecretString is the bare token or a JSON object with a `token` key).
    3. --apply only: mint a short-lived admin PAT inside the gitlab-0 pod with a
       single batched `gitlab-rails runner` call (root user, api + admin_mode,
       7-day expiry). This is the established repo fallback; the token is used
       for the run and not persisted. In --plan no PAT is minted; if none is
       available the GitLab state is described abstractly.

SAFETY
  --plan (default) performs read-only GETs and prints the intended actions; it
  mutates nothing. --apply performs the create/update calls. Secrets are read
  from env / the secrets file / ASM and passed in request bodies over TLS, never
  on argv and never logged.

Usage:
    python3 scripts/setup-pm-persona.py                 # plan (default)
    python3 scripts/setup-pm-persona.py --apply          # operator only
    python3 scripts/setup-pm-persona.py --apply --generate-password
Options:
    --apply                 perform the create/update mutations
    --plan                  read-only plan (default when --apply is absent)
    --generate-password     generate + store the password in ASM instead of
                            using DEMO_USER_PASSWORD
    --gitlab-access-level N GitLab project access level (20=Reporter,
                            30=Developer; default 30)
    --skip-gitlab           only reconcile the Keycloak user
    --verbose               print extra detail
"""
import argparse
import json
import os
import secrets
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

KC = os.environ.get("KEYCLOAK_URL", "https://auth.usgov.coderdemo.io").rstrip("/")
REALM = "coder"
GITLAB_API = os.environ.get(
    "GITLAB_API_URL", "https://gitlab.usgov.coderdemo.io/api/v4").rstrip("/")
SECRETS_ENV = os.path.expanduser("~/.config/usgov-coderdemo/generated-secrets.env")
REGION = "us-gov-west-1"
ASM_PASSWORD_NAME = "usgov-coderdemo/persona/morgan-pm"
ASM_GITLAB_PAT_NAME = "usgov-coderdemo/gitlab/admin-pat"

EMAIL_DOMAIN = "usgov.coderdemo.io"
GITLAB_NS = "gitlab"
GITLAB_POD = "gitlab-0"
GITLAB_CONTAINER = "gitlab"
PROJECT_ID = 2  # coderdemo/coder-templates

# The PM persona. Group membership is deliberately minimal: a regular member of
# /platform so Coder IdP sync grants an org membership, with no admin role.
PERSONA = {
    "username": "morgan.pm",
    "first": "Morgan",
    "last": "Pierce",
    "groups": ["/platform"],
}

TOKEN = None


# --- helpers ---------------------------------------------------------------

def read_secrets():
    out = {}
    try:
        with open(SECRETS_ENV) as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    out[k] = v.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return out


SECRETS = read_secrets()


def mask_len(s):
    return f"{len(s)} chars" if s else "(empty)"


# --- Keycloak --------------------------------------------------------------

def kc_token():
    if "KEYCLOAK_ADMIN_USERNAME" not in SECRETS or "KEYCLOAK_ADMIN_PASSWORD" not in SECRETS:
        sys.exit(f"Keycloak admin creds not found in {SECRETS_ENV}")
    data = urllib.parse.urlencode({
        "grant_type": "password",
        "client_id": "admin-cli",
        "username": SECRETS["KEYCLOAK_ADMIN_USERNAME"],
        "password": SECRETS["KEYCLOAK_ADMIN_PASSWORD"],
    }).encode()
    req = urllib.request.Request(
        KC + "/realms/master/protocol/openid-connect/token", data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    return json.load(urllib.request.urlopen(req))["access_token"]


def kc(method, path, body=None):
    headers = {"Authorization": "Bearer " + TOKEN}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    req = urllib.request.Request(KC + "/admin/realms/" + REALM + path,
                                 data=data, headers=headers, method=method)
    try:
        r = urllib.request.urlopen(req)
        raw = r.read().decode()
        return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def kc_find_user(username):
    _, found = kc("GET", "/users?exact=true&username=" + urllib.parse.quote(username))
    return found[0] if found else None


def kc_group_paths():
    """Return {full_path: id} for the configured persona groups (top-level and
    one level of children), so memberships can be applied by id."""
    _, tops = kc("GET", "/groups?max=200")
    out = {}
    for g in (tops or []):
        out["/" + g["name"]] = g["id"]
        _, kids = kc("GET", f"/groups/{g['id']}/children?max=200")
        for c in (kids or []):
            out[f"/{g['name']}/{c['name']}"] = c["id"]
    return out


# --- GitLab ----------------------------------------------------------------

def gl(method, path, token, body=None):
    headers = {"PRIVATE-TOKEN": token, "Accept": "application/json"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    req = urllib.request.Request(GITLAB_API + path, data=data, headers=headers,
                                 method=method)
    try:
        r = urllib.request.urlopen(req)
        raw = r.read().decode()
        return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, raw


def gitlab_pat(apply):
    """Resolve an admin PAT. Never mints in plan mode."""
    env = os.environ.get("GITLAB_ADMIN_PAT")
    if env:
        return env, "env GITLAB_ADMIN_PAT"
    asm = asm_get_string(ASM_GITLAB_PAT_NAME)
    if asm:
        try:
            obj = json.loads(asm)
            if isinstance(obj, dict) and obj.get("token"):
                return obj["token"], f"ASM {ASM_GITLAB_PAT_NAME}"
        except (ValueError, TypeError):
            return asm, f"ASM {ASM_GITLAB_PAT_NAME}"
    if not apply:
        return None, "none (plan: would mint a 7-day admin PAT via gitlab-rails)"
    return mint_gitlab_pat(), "minted via gitlab-rails (gitlab-0)"


def mint_gitlab_pat():
    """Mint a short-lived admin PAT inside gitlab-0 with one batched rails call.
    The token is returned on stdout only; it is not persisted or logged here."""
    ruby = (
        'u = User.find_by(username: "root"); '
        't = u.personal_access_tokens.create!('
        'scopes: [:api, :admin_mode], name: "ws23-pm-setup", '
        'expires_at: 7.days.from_now); puts t.token'
    )
    r = subprocess.run(
        ["kubectl", "-n", GITLAB_NS, "exec", "-i", GITLAB_POD, "-c",
         GITLAB_CONTAINER, "--", "sh", "-c", "gitlab-rails runner -"],
        input=ruby, text=True, capture_output=True)
    if r.returncode != 0:
        sys.exit("failed to mint GitLab PAT via gitlab-rails:\n" + r.stderr)
    tok = (r.stdout or "").strip().splitlines()[-1] if r.stdout.strip() else ""
    if not tok.startswith("glpat-"):
        sys.exit("gitlab-rails did not return a glpat- token")
    return tok


# --- AWS Secrets Manager ---------------------------------------------------

def asm_get_string(name):
    r = subprocess.run(
        ["aws", "secretsmanager", "get-secret-value", "--region", REGION,
         "--secret-id", name, "--query", "SecretString", "--output", "text"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if r.returncode != 0:
        return None
    return r.stdout.decode().strip() or None


def asm_exists(name):
    r = subprocess.run(
        ["aws", "secretsmanager", "describe-secret", "--region", REGION,
         "--secret-id", name],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return r.returncode == 0


def asm_put_string(name, value, desc):
    import tempfile
    fd, path = tempfile.mkstemp(prefix="asm-", suffix=".txt")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(value)
        ref = "file://" + path
        if asm_exists(name):
            subprocess.run(
                ["aws", "secretsmanager", "put-secret-value", "--region", REGION,
                 "--secret-id", name, "--secret-string", ref],
                check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return "updated"
        subprocess.run(
            ["aws", "secretsmanager", "create-secret", "--region", REGION,
             "--name", name, "--description", desc, "--secret-string", ref],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return "created"
    finally:
        os.unlink(path)


# --- password --------------------------------------------------------------

def resolve_password(generate, apply):
    """Return (password, source). With --generate-password, reuse the ASM value
    if present, otherwise generate one (stored to ASM only on --apply)."""
    if generate:
        existing = asm_get_string(ASM_PASSWORD_NAME)
        if existing:
            try:
                obj = json.loads(existing)
                if isinstance(obj, dict) and obj.get("password"):
                    return obj["password"], f"ASM {ASM_PASSWORD_NAME} (existing)"
            except ValueError:
                pass
        pw = secrets.token_urlsafe(24)
        if apply:
            action = asm_put_string(
                ASM_PASSWORD_NAME, json.dumps({"password": pw}),
                "WS-23 PM persona morgan.pm password")
            return pw, f"ASM {ASM_PASSWORD_NAME} ({action})"
        return pw, f"ASM {ASM_PASSWORD_NAME} (would create on apply)"
    pw = SECRETS.get("DEMO_USER_PASSWORD")
    if not pw:
        sys.exit(f"DEMO_USER_PASSWORD not found in {SECRETS_ENV} "
                 "(or pass --generate-password)")
    return pw, "DEMO_USER_PASSWORD"


# --- plan model ------------------------------------------------------------

class Plan:
    def __init__(self):
        self.items = []  # (system, action, name, detail)

    def add(self, system, action, name, detail):
        self.items.append((system, action, name, detail))

    def print(self):
        print("PLAN (read-only; nothing changed unless --apply):\n")
        width = max((len(i[2]) for i in self.items), default=10)
        for system, action, name, detail in self.items:
            print(f"  [{action:7}] {system:9} {name:<{width}}  {detail}")
        print()


# --- reconcile -------------------------------------------------------------

def reconcile_keycloak(plan, password, pw_source, apply):
    username = PERSONA["username"]
    user = kc_find_user(username)
    paths = kc_group_paths()
    if user is None:
        plan.add("keycloak", "CREATE", username,
                 f"realm {REALM}, email {username}@{EMAIL_DOMAIN}, "
                 f"groups {PERSONA['groups']}, password {mask_len(password)} "
                 f"from {pw_source}")
        if apply:
            rep = {
                "username": username,
                "email": f"{username}@{EMAIL_DOMAIN}",
                "firstName": PERSONA["first"],
                "lastName": PERSONA["last"],
                "enabled": True,
                "emailVerified": True,
            }
            code, _ = kc("POST", "/users", rep)
            user = kc_find_user(username)
            print(f"  keycloak user {username}: CREATED (HTTP {code})")
    else:
        plan.add("keycloak", "UPDATE", username,
                 f"exists; reconcile name/password/groups (password {pw_source})")

    if apply and user:
        uid = user["id"]
        kc("PUT", f"/users/{uid}/reset-password",
           {"type": "password", "value": password, "temporary": False})
        for gpath in PERSONA["groups"]:
            gid = paths.get(gpath)
            if gid:
                kc("PUT", f"/users/{uid}/groups/{gid}")
            else:
                print(f"  WARN: Keycloak group {gpath} not found; skipped")
        print(f"  keycloak user {username}: password set, "
              f"groups -> {', '.join(PERSONA['groups'])}")


def reconcile_gitlab(plan, password, access_level, apply):
    username = PERSONA["username"]
    pat, pat_source = gitlab_pat(apply)
    if pat is None:
        plan.add("gitlab", "PLAN", username,
                 f"no admin PAT available in plan mode ({pat_source}); "
                 f"would ensure user + project {PROJECT_ID} membership "
                 f"(access_level={access_level})")
        return
    plan.add("gitlab", "AUTH", username, f"admin PAT from {pat_source}")

    code, found = gl("GET", "/users?username=" + urllib.parse.quote(username), pat)
    user = found[0] if (code == 200 and found) else None
    if user is None:
        plan.add("gitlab", "CREATE", username,
                 f"user {username}@{EMAIL_DOMAIN}, openid_connect identity, "
                 f"password {mask_len(password)}")
        if apply:
            rep = {
                "username": username,
                "email": f"{username}@{EMAIL_DOMAIN}",
                "name": f"{PERSONA['first']} {PERSONA['last']}",
                "password": password,
                "skip_confirmation": True,
                "provider": "openid_connect",
                "extern_uid": username,
            }
            code, res = gl("POST", "/users", pat, rep)
            if code not in (200, 201):
                print(f"  gitlab user {username}: CREATE FAILED ({code}) {res}")
                return
            user = res
            print(f"  gitlab user {username}: CREATED (id {user.get('id')})")
    else:
        plan.add("gitlab", "UPDATE", username,
                 f"exists (id {user.get('id')}); reconcile name + "
                 f"openid_connect identity")
        if apply:
            gl("PUT", f"/users/{user['id']}", pat, {
                "name": f"{PERSONA['first']} {PERSONA['last']}",
                "provider": "openid_connect",
                "extern_uid": username,
            })
            print(f"  gitlab user {username}: reconciled (id {user['id']})")

    # Project membership.
    level_name = {20: "Reporter", 30: "Developer", 40: "Maintainer"}.get(
        access_level, str(access_level))
    if apply and user:
        uid = user["id"]
        code, _ = gl("GET", f"/projects/{PROJECT_ID}/members/all/{uid}", pat)
        if code == 200:
            gl("PUT", f"/projects/{PROJECT_ID}/members/{uid}", pat,
               {"access_level": access_level})
            print(f"  gitlab project {PROJECT_ID}: {username} -> "
                  f"{level_name} (updated)")
        else:
            c2, r2 = gl("POST", f"/projects/{PROJECT_ID}/members", pat,
                        {"user_id": uid, "access_level": access_level})
            print(f"  gitlab project {PROJECT_ID}: {username} -> "
                  f"{level_name} (HTTP {c2})")
    else:
        plan.add("gitlab", "MEMBER", username,
                 f"project {PROJECT_ID} membership -> {level_name} "
                 f"({access_level})")


# --- main ------------------------------------------------------------------

def main():
    global TOKEN
    ap = argparse.ArgumentParser(description="Create the WS-23 PM persona (morgan.pm).")
    ap.add_argument("--apply", action="store_true", help="perform mutations")
    ap.add_argument("--plan", action="store_true", help="read-only plan (default)")
    ap.add_argument("--generate-password", action="store_true",
                    help="generate + store the password in ASM")
    ap.add_argument("--gitlab-access-level", type=int, default=30,
                    help="GitLab project access level (20=Reporter, 30=Developer)")
    ap.add_argument("--skip-gitlab", action="store_true",
                    help="only reconcile the Keycloak user")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    if args.apply and args.plan:
        sys.exit("--apply and --plan are mutually exclusive")
    apply = args.apply

    password, pw_source = resolve_password(args.generate_password, apply)

    TOKEN = kc_token()
    plan = Plan()
    reconcile_keycloak(plan, password, pw_source, apply)
    if not args.skip_gitlab:
        reconcile_gitlab(plan, password, args.gitlab_access_level, apply)

    if not apply:
        plan.print()
        print("(read-only plan; no changes made. Re-run with --apply to mutate.)")
        return
    print("\nDone. Verify:")
    print("  - Keycloak: morgan.pm can sign into https://dev.usgov.coderdemo.io")
    print(f"  - GitLab: morgan.pm is a member of project {PROJECT_ID} and can "
          "open + assign issues")


if __name__ == "__main__":
    main()
