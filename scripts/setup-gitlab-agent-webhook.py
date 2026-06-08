#!/usr/bin/env python3
"""
setup-gitlab-agent-webhook.py - configure the GitLab project webhook that drives
the WS-23 GitLab to Coder agent-attribution flow, and (optionally) simulate the
attributed Task creation so the demo can run before the receiver is deployed.

DESIGN (see docs/architecture/gitlab-coder-agent-attribution.md)
  A GitLab Issue-events webhook on coderdemo/coder-templates (id 2) delivers
  issue events to the in-cluster receiver (`agent-attribution-bridge`, ns coder).
  The receiver verifies the shared X-Gitlab-Token, and for an issue that has the
  `coder-task` label AND an assignee, creates a Coder Task owned by the assignee:
  POST /api/v2/tasks/{assignee}. Attribution is by the assignee, never the author.

WHAT IT DOES (plan first, mutate only with --apply)
  Webhook mode (default):
    - resolve project coderdemo/coder-templates (id 2) and its existing hooks
    - idempotently create or update an Issue-events webhook pointing at the
      receiver URL, with token verification, all other event types disabled
  Simulate mode (--simulate --issue N): no webhook needed; reproduces exactly
  what the receiver would do for issue N:
    - read the issue (assignee, labels, title, body) via the GitLab API
    - resolve the claude-code active template version via the Coder API
    - print the exact POST /api/v2/tasks/{assignee} request; with --apply, send it

CREDENTIALS (never logged; lengths only)
  GitLab admin PAT: $GITLAB_ADMIN_PAT, else ASM usgov-coderdemo/gitlab/admin-pat.
  Webhook shared secret: $BRIDGE_WEBHOOK_SECRET, else the `webhook-secret` key of
    ASM usgov-coderdemo/agent-attribution/bridge.
  Coder token (simulate only): $CODER_TASK_BOT_TOKEN, else the `coder-token` key
    of ASM usgov-coderdemo/agent-attribution/bridge, else admin login from
    ~/.config/usgov-coderdemo/generated-secrets.env.

SAFETY
  --plan (default) only performs read-only GETs and prints intended actions.
  --apply performs the webhook create/update (and, in simulate, the task POST).
  This script never requires the receiver to be running; --check-receiver probes
  it but a failed probe is a warning, not an error.

Usage:
    python3 scripts/setup-gitlab-agent-webhook.py                       # plan
    python3 scripts/setup-gitlab-agent-webhook.py --apply                # register
    python3 scripts/setup-gitlab-agent-webhook.py --simulate --issue 7   # print
    python3 scripts/setup-gitlab-agent-webhook.py --simulate --issue 7 --apply
Options:
    --apply              perform mutations (register hook, or send the task POST)
    --plan               read-only plan (default)
    --url URL            receiver webhook URL (default in-cluster Service URL)
    --simulate           simulate the receiver for a single issue (--issue N)
    --issue N            issue IID for --simulate
    --check-receiver     probe the receiver /readyz (warning only)
    --verbose            print extra detail
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

GITLAB_API = os.environ.get(
    "GITLAB_API_URL", "https://gitlab.usgov.coderdemo.io/api/v4").rstrip("/")
CODER_URL = os.environ.get("DEMO_CODER_URL", "https://dev.usgov.coderdemo.io").rstrip("/")
SECRETS_ENV = os.path.expanduser("~/.config/usgov-coderdemo/generated-secrets.env")
REGION = "us-gov-west-1"
ASM_BRIDGE_NAME = "usgov-coderdemo/agent-attribution/bridge"
ASM_GITLAB_PAT_NAME = "usgov-coderdemo/gitlab/admin-pat"

PROJECT_ID = 2  # coderdemo/coder-templates
PROJECT_PATH = "coderdemo/coder-templates"
DEFAULT_RECEIVER_URL = (
    "http://agent-attribution-bridge.coder.svc.cluster.local:8080/webhook")
TASK_LABEL = "coder-task"
TEMPLATE_NAME = "claude-code"
CODER_ORG_ID = "5de29a6d-8836-4643-a42b-2cb807c8e3e2"  # org "coder"


# --- shared helpers --------------------------------------------------------

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


def http(method, url, headers, body=None):
    data = None
    if body is not None:
        if isinstance(body, (dict, list)):
            data = json.dumps(body).encode()
            headers = {**headers, "Content-Type": "application/json"}
        else:
            data = body
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
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


# --- AWS Secrets Manager ---------------------------------------------------

def asm_get_string(name):
    import subprocess
    r = subprocess.run(
        ["aws", "secretsmanager", "get-secret-value", "--region", REGION,
         "--secret-id", name, "--query", "SecretString", "--output", "text"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if r.returncode != 0:
        return None
    return r.stdout.decode().strip() or None


def asm_json_key(name, key):
    raw = asm_get_string(name)
    if not raw:
        return None
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj.get(key)
    except ValueError:
        return None
    return None


# --- credential resolution -------------------------------------------------

def gitlab_pat():
    env = os.environ.get("GITLAB_ADMIN_PAT")
    if env:
        return env, "env GITLAB_ADMIN_PAT"
    raw = asm_get_string(ASM_GITLAB_PAT_NAME)
    if raw:
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict) and obj.get("token"):
                return obj["token"], f"ASM {ASM_GITLAB_PAT_NAME}"
        except ValueError:
            return raw, f"ASM {ASM_GITLAB_PAT_NAME}"
    return None, "none"


def webhook_secret():
    env = os.environ.get("BRIDGE_WEBHOOK_SECRET")
    if env:
        return env, "env BRIDGE_WEBHOOK_SECRET"
    val = asm_json_key(ASM_BRIDGE_NAME, "webhook-secret")
    if val:
        return val, f"ASM {ASM_BRIDGE_NAME}[webhook-secret]"
    return None, "none"


def gl(method, path, pat, body=None):
    return http(method, GITLAB_API + path,
                {"PRIVATE-TOKEN": pat, "Accept": "application/json"}, body)


# --- Coder (simulate) ------------------------------------------------------

def coder_token():
    env = os.environ.get("CODER_TASK_BOT_TOKEN")
    if env:
        return env, "env CODER_TASK_BOT_TOKEN"
    val = asm_json_key(ASM_BRIDGE_NAME, "coder-token")
    if val:
        return val, f"ASM {ASM_BRIDGE_NAME}[coder-token]"
    email = SECRETS.get("CODER_ADMIN_EMAIL")
    pw = SECRETS.get("CODER_ADMIN_PASSWORD")
    if email and pw:
        status, res = http("POST", CODER_URL + "/api/v2/users/login", {},
                           {"email": email, "password": pw})
        if status == 201 and isinstance(res, dict):
            return res["session_token"], "admin login (generated-secrets.env)"
    return None, "none"


def coder_api(method, path, token, body=None):
    return http(method, CODER_URL + path, {"Coder-Session-Token": token}, body)


def resolve_template_version(token):
    """Return (template_version_id, note) for the claude-code active version."""
    status, templates = coder_api("GET", "/api/v2/templates", token)
    if status != 200 or not isinstance(templates, list):
        return None, f"GET /api/v2/templates -> {status}"
    for t in templates:
        if t.get("name") == TEMPLATE_NAME:
            return t.get("active_version_id"), f"template {TEMPLATE_NAME} active version"
    return None, f"template {TEMPLATE_NAME} not found"


# --- name + prompt ---------------------------------------------------------

def workspace_name(project_path, iid):
    repo = project_path.rsplit("/", 1)[-1].lower()
    repo = "".join(c if (c.isalnum() or c == "-") else "-" for c in repo).strip("-")
    suffix = f"-issue-{iid}"
    if not repo:
        return suffix.lstrip("-")
    if len(repo) + len(suffix) > 32:
        repo = repo[:32 - len(suffix)].rstrip("-")
    return repo + suffix


def seed_prompt(issue, project_path, iid):
    title = (issue or {}).get("title", "")
    desc = (issue or {}).get("description", "") or ""
    url = (issue or {}).get("web_url", "")
    if title:
        body = (f"You have been assigned GitLab issue #{iid} in `{project_path}`.\n\n"
                f"Title: {title}\n\n")
        if desc.strip():
            body += f"Description:\n\n{desc}\n\n"
        body += (f"Source: {url}\n\n"
                 "Investigate the request, make the needed changes in the "
                 "workspace repo, then push a branch and open a Merge Request "
                 f"that references the issue (Closes #{iid}).")
        return body
    return (f"Work on GitLab issue {url}. Investigate, make the changes, then "
            f"push a branch and open a Merge Request that closes issue #{iid}.")


# --- webhook registration --------------------------------------------------

def register_webhook(url, apply, verbose):
    pat, pat_source = gitlab_pat()
    secret, secret_source = webhook_secret()
    print(f"Receiver URL         : {url}")
    print(f"GitLab admin PAT     : {pat_source}")
    print(f"Webhook shared secret: {secret_source} ({mask_len(secret or '')})")
    if url.startswith("http://"):
        print("NOTE: an in-cluster http:// target requires GitLab admin setting "
              "'Allow requests to the local network from webhooks', or expose the "
              "receiver via ingress and use an https:// URL.")
    if pat is None:
        print("\nNo GitLab admin PAT available; cannot read or register hooks.")
        print("Provide $GITLAB_ADMIN_PAT or populate ASM "
              f"{ASM_GITLAB_PAT_NAME}, then re-run.")
        return 1

    status, hooks = gl("GET", f"/projects/{PROJECT_ID}/hooks", pat)
    if status != 200 or not isinstance(hooks, list):
        print(f"GET project {PROJECT_ID} hooks -> {status} {hooks}")
        return 1
    existing = next((h for h in hooks if h.get("url") == url), None)

    payload = {
        "url": url,
        "issues_events": True,
        "push_events": False,
        "merge_requests_events": False,
        "tag_push_events": False,
        "note_events": False,
        "enable_ssl_verification": url.startswith("https://"),
    }
    if secret:
        payload["token"] = secret

    if existing:
        action = "UPDATE"
        detail = f"hook id {existing['id']} (issues_events, token refreshed)"
    else:
        action = "CREATE"
        detail = "new Issue-events hook with token verification"
    print(f"\n[{action}] project {PROJECT_PATH} (id {PROJECT_ID}): {detail}")

    if not apply:
        print("\n(read-only plan; no changes made. Re-run with --apply.)")
        if secret is None:
            print("WARNING: no webhook secret resolved; --apply would register a "
                  "hook WITHOUT token verification. Populate the secret first.")
        return 0
    if secret is None:
        print("Refusing to register a hook without a shared secret. "
              "Populate $BRIDGE_WEBHOOK_SECRET or ASM "
              f"{ASM_BRIDGE_NAME}[webhook-secret] first.")
        return 1

    if existing:
        code, res = gl("PUT", f"/projects/{PROJECT_ID}/hooks/{existing['id']}",
                       pat, payload)
    else:
        code, res = gl("POST", f"/projects/{PROJECT_ID}/hooks", pat, payload)
    ok = code in (200, 201)
    print(f"  {'ok' if ok else 'FAIL'}: hook {action.lower()} -> {code}"
          + ("" if ok else f" {res}"))
    return 0 if ok else 1


# --- simulate --------------------------------------------------------------

def simulate(iid, apply, verbose):
    pat, pat_source = gitlab_pat()
    if pat is None:
        print("simulate requires a GitLab admin PAT to read the issue.")
        return 1
    status, issue = gl("GET", f"/projects/{PROJECT_ID}/issues/{iid}", pat)
    if status != 200 or not isinstance(issue, dict):
        print(f"GET issue {iid} -> {status} {issue}")
        return 1

    assignees = issue.get("assignees") or []
    assignee = assignees[0]["username"] if assignees else None
    labels = issue.get("labels") or []
    has_label = TASK_LABEL in labels or any(
        str(l).startswith(TASK_LABEL + ":") for l in labels)

    print(f"Issue #{iid}: {issue.get('title', '')!r}")
    print(f"  labels   : {labels}")
    print(f"  assignee : {assignee or '(none)'}")
    if not has_label:
        print(f"NO-OP: issue lacks the `{TASK_LABEL}` label.")
        return 0
    if not assignee:
        print("NO-OP: issue has no assignee (assign it to attribute the task).")
        return 0

    token, token_source = coder_token()
    if token is None:
        print("simulate requires a Coder token to resolve the template version.")
        return 1
    tv_id, tv_note = resolve_template_version(token)
    name = workspace_name(PROJECT_PATH, iid)
    prompt = seed_prompt(issue, PROJECT_PATH, iid)

    print(f"\nCoder token  : {token_source}")
    print(f"Template     : {tv_note} -> {tv_id}")
    print("\nAttributed Task request (owner = assignee):")
    print(f"  POST {CODER_URL}/api/v2/tasks/{assignee}")
    print(f"  body: {json.dumps({'template_version_id': tv_id, 'name': name, 'input': '<issue prompt>'} )}")
    if verbose:
        print(f"\n  input prompt:\n{prompt}\n")

    if tv_id is None:
        print("\nCannot send: no AI-task template version resolved.")
        return 1
    if not apply:
        print("\n(read-only; no task created. Re-run with --apply to send.)")
        return 0

    code, res = coder_api("POST", f"/api/v2/tasks/{assignee}", token, {
        "template_version_id": tv_id,
        "name": name,
        "input": prompt,
    })
    ok = code == 201
    if ok:
        print(f"\nok: task created, owner {assignee}, workspace {name} "
              f"(id {res.get('id') if isinstance(res, dict) else '?'})")
    else:
        print(f"\nFAIL: POST tasks/{assignee} -> {code} {res}")
    return 0 if ok else 1


def check_receiver(url):
    base = url.rsplit("/webhook", 1)[0]
    try:
        status, _ = http("GET", base + "/readyz", {})
        print(f"receiver /readyz -> {status}")
    except Exception as e:  # noqa: BLE001 - probe is best-effort
        print(f"receiver probe failed (warning only): {e}")


# --- main ------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Configure the WS-23 GitLab webhook.")
    ap.add_argument("--apply", action="store_true", help="perform mutations")
    ap.add_argument("--plan", action="store_true", help="read-only plan (default)")
    ap.add_argument("--url", default=DEFAULT_RECEIVER_URL,
                    help="receiver webhook URL")
    ap.add_argument("--simulate", action="store_true",
                    help="simulate the receiver for a single issue")
    ap.add_argument("--issue", type=int, help="issue IID for --simulate")
    ap.add_argument("--check-receiver", action="store_true",
                    help="probe the receiver /readyz (warning only)")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    if args.apply and args.plan:
        sys.exit("--apply and --plan are mutually exclusive")

    if args.check_receiver:
        check_receiver(args.url)

    if args.simulate:
        if args.issue is None:
            sys.exit("--simulate requires --issue N")
        sys.exit(simulate(args.issue, args.apply, args.verbose))

    sys.exit(register_webhook(args.url, args.apply, args.verbose))


if __name__ == "__main__":
    main()
