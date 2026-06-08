#!/usr/bin/env python3
"""
receiver.py - the WS-23 GitLab to Coder agent-attribution receiver.

A tiny standard-library HTTP service. GitLab delivers Issue events here; for an
issue that carries the `coder-task` label AND an assignee, the receiver creates a
Coder Task owned by the assignee (POST /api/v2/tasks/{assignee}) using a single
scoped service-account token. The workspace is therefore owned by and attributed
to the real developer, not a shared bot.

Pure stdlib so it runs on a stock python image mounted from a ConfigMap; no build
step. Idempotent: the deterministic task/workspace name makes repeat deliveries
and issue edits a no-op once the workspace exists.

Environment:
  LISTEN_ADDR        default ":8080"
  CODER_URL          in-cluster Coder API, e.g. http://coder.coder.svc.cluster.local
  CODER_PUBLIC_URL   external Coder URL for user-facing links
  CODER_TOKEN        service-account token (create tasks on behalf of others)
  WEBHOOK_SECRET     shared secret compared against X-Gitlab-Token
  GITLAB_API_URL     e.g. https://gitlab.usgov.coderdemo.io/api/v4
  GITLAB_PAT         admin PAT for the best-effort issue comment back
  TEMPLATE_NAME      AI-task template name (default claude-code)
  TASK_LABEL         trigger label (default coder-task)
"""
import hmac
import json
import os
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LISTEN = os.environ.get("LISTEN_ADDR", ":8080")
CODER_URL = os.environ.get("CODER_URL", "").rstrip("/")
CODER_PUBLIC_URL = os.environ.get("CODER_PUBLIC_URL", CODER_URL).rstrip("/")
CODER_TOKEN = os.environ.get("CODER_TOKEN", "")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
GITLAB_API = os.environ.get("GITLAB_API_URL", "").rstrip("/")
GITLAB_PAT = os.environ.get("GITLAB_PAT", "")
TEMPLATE_NAME = os.environ.get("TEMPLATE_NAME", "claude-code")
TASK_LABEL = os.environ.get("TASK_LABEL", "coder-task")

ACTIONABLE = {"open", "update", "reopen"}


def http(method, url, headers, body=None):
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers = {**headers, "Content-Type": "application/json"}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        r = urllib.request.urlopen(req, timeout=25)
        raw = r.read().decode()
        return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, raw
    except Exception as e:  # noqa: BLE001
        return 0, str(e)


def coder(method, path, body=None):
    return http(method, CODER_URL + path, {"Coder-Session-Token": CODER_TOKEN}, body)


def gitlab_note(project_id, iid, text):
    if not (GITLAB_API and GITLAB_PAT):
        return
    http("POST", f"{GITLAB_API}/projects/{project_id}/issues/{iid}/notes",
         {"PRIVATE-TOKEN": GITLAB_PAT}, {"body": text})


def workspace_name(project_path, iid):
    repo = (project_path or "").rsplit("/", 1)[-1].lower()
    repo = "".join(c if (c.isalnum() or c == "-") else "-" for c in repo).strip("-")
    suffix = f"-issue-{iid}"
    if not repo:
        return suffix.lstrip("-")
    if len(repo) + len(suffix) > 32:
        repo = repo[:32 - len(suffix)].rstrip("-")
    return repo + suffix


def extract_label_slug(labels):
    """Return (matched, slug). Matches `coder-task` or `coder-task:<slug>`."""
    for l in labels or []:
        title = (l.get("title") if isinstance(l, dict) else str(l)).strip()
        if title == TASK_LABEL:
            return True, ""
        if title.startswith(TASK_LABEL + ":"):
            return True, title.split(":", 1)[1].strip()
    return False, ""


def seed_prompt(project_path, iid, title, desc, url):
    if title:
        body = (f"You have been assigned GitLab issue #{iid} in `{project_path}`.\n\n"
                f"Title: {title}\n\n")
        if (desc or "").strip():
            body += f"Description:\n\n{desc}\n\n"
        body += (f"Source: {url}\n\n"
                 "Investigate the request, make the needed changes in the "
                 "workspace repo, then push a branch and open a Merge Request "
                 f"that references the issue (Closes #{iid}).")
        return body
    return (f"Work on GitLab issue {url}. Investigate, make the changes, then "
            f"push a branch and open a Merge Request that closes issue #{iid}.")


def resolve_template_version(slug):
    name = slug or TEMPLATE_NAME
    status, templates = coder("GET", "/api/v2/templates")
    if status != 200 or not isinstance(templates, list):
        return None, None
    for t in templates:
        if t.get("name") == name:
            return t.get("active_version_id"), name
    return None, name


def handle_issue(payload):
    """Return (http_status, response_dict)."""
    if payload.get("object_kind") != "issue":
        return 200, {"ok": True, "action": "noop", "reason": "not an issue event"}
    attrs = payload.get("object_attributes") or {}
    if attrs.get("action") not in ACTIONABLE:
        return 200, {"ok": True, "action": "noop", "reason": "action not actionable"}

    matched, slug = extract_label_slug(payload.get("labels"))
    if not matched:
        return 200, {"ok": True, "action": "noop",
                     "reason": f"no `{TASK_LABEL}` label"}
    assignees = payload.get("assignees") or []
    assignee = assignees[0].get("username") if assignees else ""
    if not assignee:
        return 200, {"ok": True, "action": "noop",
                     "reason": "no assignee; assign to attribute the task"}

    project = payload.get("project") or {}
    project_id = project.get("id")
    project_path = project.get("path_with_namespace", "")
    iid = attrs.get("iid")
    name = workspace_name(project_path, iid)

    # Confirm the assignee maps to a Coder user. Fail closed if not.
    status, user = coder("GET", "/api/v2/users/" + assignee)
    if status == 404:
        return 422, {"ok": False,
                     "error": f"coder user not found: {assignee}; "
                              "sign into Coder via Keycloak first"}
    if status != 200:
        return 502, {"ok": False, "error": f"coder user lookup -> {status}"}

    # Idempotency: existing workspace for this issue is a no-op.
    s2, _ = coder("GET", f"/api/v2/users/{assignee}/workspace/{name}")
    if s2 == 200:
        ws_url = f"{CODER_PUBLIC_URL}/@{assignee}/{name}"
        return 200, {"ok": True, "action": "exists", "owner": assignee,
                     "workspace": name, "workspace_url": ws_url}

    tv_id, tmpl = resolve_template_version(slug)
    if not tv_id:
        return 422, {"ok": False, "error": f"template not resolved: {tmpl}"}

    prompt = seed_prompt(project_path, iid, attrs.get("title", ""),
                         attrs.get("description", ""),
                         attrs.get("url") or "")
    s3, res = coder("POST", "/api/v2/tasks/" + assignee, {
        "template_version_id": tv_id, "name": name, "input": prompt})
    if s3 != 201:
        return 502, {"ok": False, "error": f"create task -> {s3}", "detail": res}

    ws_url = f"{CODER_PUBLIC_URL}/@{assignee}/{name}"
    if project_id and iid:
        gitlab_note(project_id, iid,
                    f"Coder agent dispatched. Workspace owned by @{assignee}: "
                    f"{ws_url}\n\n_Posted by the GitLab to Coder attribution bridge._")
    return 201, {"ok": True, "action": "created", "owner": assignee,
                 "workspace": name, "workspace_url": ws_url, "template": tmpl}


class Handler(BaseHTTPRequestHandler):
    def _json(self, status, body):
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):  # noqa: N802
        if self.path == "/healthz":
            return self._json(200, {"ok": True})
        if self.path == "/readyz":
            status, _ = coder("GET", "/api/v2/buildinfo")
            ok = status and status < 500
            return self._json(200 if ok else 503, {"ok": bool(ok)})
        self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self):  # noqa: N802
        if self.path != "/webhook":
            return self._json(404, {"ok": False, "error": "not found"})
        got = self.headers.get("X-Gitlab-Token", "")
        if not WEBHOOK_SECRET or not hmac.compare_digest(got, WEBHOOK_SECRET):
            return self._json(401, {"ok": False, "error": "unauthorized"})
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0 or length > (1 << 20):
            return self._json(400, {"ok": False, "error": "bad length"})
        try:
            payload = json.loads(self.rfile.read(length).decode())
        except ValueError:
            return self._json(400, {"ok": False, "error": "invalid json"})
        try:
            status, body = handle_issue(payload)
        except Exception as e:  # noqa: BLE001
            return self._json(500, {"ok": False, "error": str(e)})
        self._json(status, body)

    def log_message(self, fmt, *args):  # quieter access log
        return


def main():
    host, _, port = LISTEN.partition(":")
    server = ThreadingHTTPServer((host or "", int(port or "8080")), Handler)
    print(f"agent-attribution receiver listening on {LISTEN}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
