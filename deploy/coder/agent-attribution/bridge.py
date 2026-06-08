#!/usr/bin/env python3
"""
bridge.py - GitLab Issues to Coder bridge (WS-23), STAGED.

This is a pure standard-library re-implementation of the Red Hat Summit 2026
demo "bridge" service, adapted for self-hosted GitLab plus Coder 2.34.

Provenance (studied, not copied), under reference/demo-aigov-rhsummit-2026:
  services/bridge/cmd/bridge/main.go          process + graceful shutdown
  services/bridge/internal/config/config.go   env load + required-var checks
  services/bridge/internal/coder/coder.go      minimal Coder API client
  services/bridge/internal/gitlab/gitlab.go    issue read + note (comment) back
  services/bridge/internal/webhook/webhook.go  payload, token verify, label
                                               vocabulary, workspace naming
  services/bridge/internal/handler/handler.go  /webhook /healthz /readyz logic
  manifests/bridge/{deployment,service,route}.yaml  in-cluster placement
  scripts/gitlab-register-bridge-webhook.sh    webhook registration

WHAT IS THE SAME AS rhsummit
  - Three endpoints: POST /webhook, GET /healthz (always 200), GET /readyz
    (200 when Coder is reachable, else 503).
  - GitLab Issues Hook receiver. Verifies X-Gitlab-Token against WEBHOOK_SECRET
    in constant time. Acts only on object_kind == "issue" with action in
    {open, update, reopen}, a coder-* label, AND a non-empty assignee list.
  - Two label modes with the same precedence rule: coder-workspace[:slug] creates
    a plain workspace the assignee opens; coder-agent[:slug] dispatches an
    autonomous agent. When both labels are present, agent wins.
  - Attribution is the issue ASSIGNEE, never the actor or author (authors are
    typically PMs). The first assignee is the workspace owner.
  - Deterministic workspace name <repo>-issue-<iid>, lowercased, sanitized to
    [a-z0-9-], truncated to Coder's 32-char limit while preserving the suffix.
  - Idempotent: an existing workspace of that name is reused as a no-op, so
    re-delivery and issue edits do not create duplicates.
  - Best-effort note back on the GitLab issue with the user-facing links.

WHAT WAS ADAPTED FOR THIS ENVIRONMENT (GitLab + Coder 2.34 Tasks API)
  - SCM is self-hosted GitLab (not GitHub). The webhook auth header is
    X-Gitlab-Token (a verbatim shared secret, no HMAC), and the comment-back
    uses the GitLab Notes API with a PRIVATE-TOKEN admin PAT.
  - Agent dispatch uses the STABLE Coder 2.34 Tasks API,
    POST /api/v2/tasks/{assignee}, whose path parameter sets the workspace
    OWNER to the assignee. The rhsummit bridge instead created an experimental
    chat (POST /api/experimental/chats), which hardcodes owner_id to the
    caller and therefore forced it to mint a per-user token first. The Tasks
    API removes that step: a single service-account token attributes the work
    to the developer. No per-user token minting here.
  - rhsummit's coder-agent:<slug> selected a chatd MODEL (model-configs,
    highest-version-wins). Coder 2.34 Tasks does not expose chatd model
    configs; model choice lives inside the AI-task template and the AI Gateway.
    So here coder-agent:<slug> selects a TEMPLATE by name (default claude-code),
    and the model-pinning logic is intentionally dropped.
  - The Tasks request carries no rich_parameter_values (CreateTaskRequest has
    only template_version_id, input, name). The claude-code template exposes an
    ai_prompt parameter that Coder fills from `input`, so the issue context is
    delivered through the seed prompt rather than a git_repo parameter.
  - Workspace mode uses POST /api/v2/users/{assignee}/workspaces with the
    template's active version. It wires git_repo only when the template version
    actually declares that parameter (checked via the rich-parameters API), so
    the rhsummit "templates that declare git_repo track the issue's project"
    promise holds without breaking templates that do not declare it.
  - coder-task[:slug] is retained as an alias for coder-agent[:slug] for
    continuity with earlier WS-23 issues and tooling.

Pure stdlib so it runs on a stock python image mounted from a ConfigMap; no
build step, fully reversible. Sections below mirror the rhsummit Go packages.

Environment (mirrors config.go; required vars validated at startup):
  LISTEN_ADDR        default ":8080"
  CODER_URL          REQUIRED in-cluster Coder API, e.g.
                     http://coder.coder.svc.cluster.local
  CODER_PUBLIC_URL   external Coder URL for user-facing links (default CODER_URL)
  CODER_TOKEN        REQUIRED service-account token (creates workspaces and
                     tasks on behalf of the assignee)
  WEBHOOK_SECRET     REQUIRED shared secret compared against X-Gitlab-Token
  GITLAB_API_URL     REQUIRED e.g. https://gitlab.usgov.coderdemo.io/api/v4
  GITLAB_PAT         REQUIRED admin PAT for issue read + comment back
  DEFAULT_TEMPLATE   default "claude-code"
  WORKSPACE_LABEL    default "coder-workspace"
  AGENT_LABEL        default "coder-agent"
  TASK_LABEL         default "coder-task" (alias of AGENT_LABEL)
  GIT_REPO_PARAM     default "git_repo" (workspace-mode rich parameter name)
  LOG_LEVEL          debug | info | warn | error (default info)
"""
import hmac
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


# ===========================================================================
# config (mirrors internal/config/config.go)
# ===========================================================================

def _getenv(key, default=""):
    v = os.environ.get(key, "")
    return v if v else default


class Config:
    def __init__(self):
        self.listen_addr = _getenv("LISTEN_ADDR", ":8080")
        self.coder_url = _getenv("CODER_URL").rstrip("/")
        self.coder_public_url = _getenv("CODER_PUBLIC_URL").rstrip("/") or self.coder_url
        self.coder_token = _getenv("CODER_TOKEN")
        self.webhook_secret = _getenv("WEBHOOK_SECRET")
        self.gitlab_api = _getenv("GITLAB_API_URL").rstrip("/")
        self.gitlab_pat = _getenv("GITLAB_PAT")
        self.default_template = _getenv("DEFAULT_TEMPLATE", "claude-code")
        self.workspace_label = _getenv("WORKSPACE_LABEL", "coder-workspace")
        self.agent_label = _getenv("AGENT_LABEL", "coder-agent")
        self.task_label = _getenv("TASK_LABEL", "coder-task")
        self.git_repo_param = _getenv("GIT_REPO_PARAM", "git_repo")
        self.log_level = _getenv("LOG_LEVEL", "info")

    def validate(self):
        missing = [name for name, val in (
            ("CODER_URL", self.coder_url),
            ("CODER_TOKEN", self.coder_token),
            ("WEBHOOK_SECRET", self.webhook_secret),
            ("GITLAB_API_URL", self.gitlab_api),
            ("GITLAB_PAT", self.gitlab_pat),
        ) if not val]
        if missing:
            return "missing required env vars: " + ", ".join(missing)
        if not (self.coder_url.startswith("http://")
                or self.coder_url.startswith("https://")):
            return "CODER_URL must include scheme (http:// or https://)"
        return None


# ===========================================================================
# logging (mirrors the slog JSON handler in main.go)
# ===========================================================================

_LEVELS = {"debug": 10, "info": 20, "warn": 30, "error": 40}


class Logger:
    def __init__(self, level):
        self.threshold = _LEVELS.get(level, 20)

    def _emit(self, level, msg, fields):
        if _LEVELS[level] < self.threshold:
            return
        rec = {"time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "level": level, "msg": msg}
        rec.update(fields)
        print(json.dumps(rec), flush=True)

    def debug(self, msg, **f):
        self._emit("debug", msg, f)

    def info(self, msg, **f):
        self._emit("info", msg, f)

    def warn(self, msg, **f):
        self._emit("warn", msg, f)

    def error(self, msg, **f):
        self._emit("error", msg, f)


# ===========================================================================
# coder client (mirrors internal/coder/coder.go)
# ===========================================================================

class CoderError(Exception):
    def __init__(self, status, body):
        super().__init__(f"coder api status={status}")
        self.status = status
        self.body = body


NOT_FOUND = object()


class CoderClient:
    def __init__(self, base_url, token, timeout=20):
        self.base_url = base_url
        self.token = token
        self.timeout = timeout

    def _do(self, method, path, body=None):
        """Return parsed JSON on 2xx, NOT_FOUND on 404, raise CoderError on >=400."""
        headers = {"Coder-Session-Token": self.token, "Accept": "application/json"}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base_url + path, data=data,
                                     headers=headers, method=method)
        try:
            r = urllib.request.urlopen(req, timeout=self.timeout)
            raw = r.read().decode()
            return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            raw = e.read().decode()
            if e.code == 404:
                return NOT_FOUND
            try:
                parsed = json.loads(raw)
            except ValueError:
                parsed = raw
            raise CoderError(e.code, parsed)

    def get_user(self, username):
        return self._do("GET", "/api/v2/users/" + _urlquote(username))

    def get_workspace_by_name(self, username, name):
        return self._do(
            "GET", f"/api/v2/users/{_urlquote(username)}/workspace/{_urlquote(name)}")

    def list_templates(self):
        return self._do("GET", "/api/v2/templates")

    def template_rich_parameters(self, version_id):
        return self._do(
            "GET", f"/api/v2/templateversions/{version_id}/rich-parameters")

    def create_workspace(self, username, version_id, name, rich_params=None):
        body = {"template_version_id": version_id, "name": name}
        if rich_params:
            body["rich_parameter_values"] = rich_params
        return self._do(
            "POST", f"/api/v2/users/{_urlquote(username)}/workspaces", body)

    def create_task(self, username, version_id, name, prompt):
        body = {"template_version_id": version_id, "name": name, "input": prompt}
        return self._do("POST", "/api/v2/tasks/" + _urlquote(username), body)

    def ping(self):
        try:
            self._do("GET", "/api/v2/buildinfo")
            return True
        except CoderError as e:
            return e.status < 500
        except Exception:  # noqa: BLE001
            return False


# ===========================================================================
# gitlab client (mirrors internal/gitlab/gitlab.go)
# ===========================================================================

class GitLabClient:
    def __init__(self, api_url, pat, timeout=10):
        self.api_url = api_url
        self.pat = pat
        self.timeout = timeout

    def _do(self, method, path, body=None):
        headers = {"PRIVATE-TOKEN": self.pat, "Accept": "application/json"}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.api_url + path, data=data,
                                     headers=headers, method=method)
        r = urllib.request.urlopen(req, timeout=self.timeout)
        raw = r.read().decode()
        return json.loads(raw) if raw else None

    def get_issue(self, project_id, iid):
        return self._do("GET", f"/projects/{project_id}/issues/{iid}")

    def post_issue_comment(self, project_id, iid, body):
        return self._do(
            "POST", f"/projects/{project_id}/issues/{iid}/notes", {"body": body})


# ===========================================================================
# webhook helpers (mirrors internal/webhook/webhook.go)
# ===========================================================================

MODE_NONE = ""
MODE_WORKSPACE = "workspace"
MODE_AGENT = "agent"

ACTIONABLE = {"open", "update", "reopen"}
_SLUG_RE = re.compile(r"^[a-z0-9._-]+$")
_NAME_SANITIZE_RE = re.compile(r"[^a-z0-9-]+")


def verify_token(got, want):
    """Constant-time compare of the GitLab webhook token (verbatim, no HMAC)."""
    if not want:
        return False
    return hmac.compare_digest(got or "", want)


def is_actionable(payload):
    if payload.get("object_kind") != "issue":
        return False, "not an issue event"
    attrs = payload.get("object_attributes") or {}
    if attrs.get("action") not in ACTIONABLE:
        return False, "action not in {open, update, reopen}"
    return True, ""


def _match_label(title, base):
    """Return (matched, slug) for `base` or `base:<slug>` with a valid slug."""
    if title == base:
        return True, ""
    prefix = base + ":"
    if title.startswith(prefix):
        slug = title[len(prefix):].strip().lower()
        if _SLUG_RE.match(slug):
            return True, slug
    return False, ""


def extract_mode(labels, cfg):
    """Scan labels for the workspace and agent vocabularies.

    Agent labels (cfg.agent_label and its cfg.task_label alias) win over the
    workspace label when both are present, mirroring rhsummit ExtractMode where
    the agent is the superset. Returns (mode, slug); slug selects a template by
    name (empty falls back to cfg.default_template).
    """
    ws_found, ws_slug = False, ""
    for raw in labels or []:
        title = (raw.get("title") if isinstance(raw, dict) else str(raw)).strip()
        for agent_base in (cfg.agent_label, cfg.task_label):
            m, slug = _match_label(title, agent_base)
            if m:
                return MODE_AGENT, slug
        m, slug = _match_label(title, cfg.workspace_label)
        if m:
            ws_found, ws_slug = True, slug
    if ws_found:
        return MODE_WORKSPACE, ws_slug
    return MODE_NONE, ""


def first_assignee(payload):
    assignees = payload.get("assignees") or []
    if not assignees:
        return ""
    return (assignees[0].get("username") or "").strip()


def workspace_name(path_with_namespace, iid):
    """Deterministic <repo>-issue-<iid>, sanitized and truncated to 32 chars."""
    repo = (path_with_namespace or "").rsplit("/", 1)[-1].lower()
    repo = _NAME_SANITIZE_RE.sub("-", repo).strip("-")
    suffix = f"-issue-{iid}"
    if not repo:
        return suffix.lstrip("-")
    if len(repo) + len(suffix) > 32:
        repo = repo[:32 - len(suffix)].rstrip("-")
    return repo + suffix


def issue_url(payload):
    attrs = payload.get("object_attributes") or {}
    if attrs.get("url"):
        return attrs["url"]
    project = payload.get("project") or {}
    web = project.get("web_url")
    if web:
        return f"{web}/-/issues/{attrs.get('iid')}"
    return ""


def build_seed_prompt(project_path, iid, repo_web_url, title, description, url):
    """Compose the agent's first instruction. Embeds the issue body when known so
    the agent does not need to call the GitLab API itself; falls back to URL only.
    """
    if title:
        parts = [
            f"You have been assigned GitLab issue #{iid} in `{project_path}`.",
            "",
            f"Title: {title}",
            "",
        ]
        if (description or "").strip():
            parts += ["Description:", "", description, ""]
        parts += [
            f"Source: {url}",
            f"Repository: {repo_web_url}",
            "",
            ("Clone the repository above, investigate the request, and make the "
             "needed changes. When you are done, push a branch and open a Merge "
             f"Request that references the issue (Closes #{iid}) so it auto-closes "
             "on merge."),
        ]
        return "\n".join(parts)
    return (f"Work on GitLab issue {url} in repository {repo_web_url}. Clone the "
            "repo, investigate, make the changes, then push a branch and open a "
            f"Merge Request that closes issue #{iid}.")


# ===========================================================================
# handler (mirrors internal/handler/handler.go)
# ===========================================================================

class Bridge:
    def __init__(self, cfg, coder, gitlab, logger):
        self.cfg = cfg
        self.coder = coder
        self.gitlab = gitlab
        self.log = logger

    def workspace_link(self, owner, name):
        return f"{self.cfg.coder_public_url}/@{owner}/{name}"

    def resolve_template_version(self, mode, slug):
        """Return (version_id, template_name) for the selected template.

        For both modes the slug selects a template by name; empty slug uses the
        configured default. Returns (None, name) when the template is absent.
        """
        name = slug or self.cfg.default_template
        templates = self.coder.list_templates()
        if not isinstance(templates, list):
            return None, name
        for t in templates:
            if t.get("name") == name:
                return t.get("active_version_id"), name
        return None, name

    def git_repo_params(self, version_id, repo_web_url):
        """Wire git_repo only when the template version declares that parameter,
        matching rhsummit's promise without breaking templates that omit it."""
        if not (version_id and repo_web_url):
            return None
        params = self.coder.template_rich_parameters(version_id)
        if not isinstance(params, list):
            return None
        for p in params:
            if p.get("name") == self.cfg.git_repo_param:
                return [{"name": self.cfg.git_repo_param, "value": repo_web_url}]
        return None

    def handle_issue(self, payload, log):
        """Return (http_status, response_dict)."""
        ok, reason = is_actionable(payload)
        if not ok:
            log.info("noop: not actionable", reason=reason)
            return 200, {"ok": True, "action": "noop", "reason": reason}

        mode, slug = extract_mode(payload.get("labels"), self.cfg)
        if mode == MODE_NONE:
            log.info("noop: no coder-{workspace,agent} label")
            return 200, {"ok": True, "action": "noop",
                         "reason": "no coder-{workspace,agent} label"}

        assignee = first_assignee(payload)
        if not assignee:
            log.info("noop: no assignee")
            return 200, {"ok": True, "action": "noop",
                         "reason": "no assignee; assign the issue to trigger spawn"}

        project = payload.get("project") or {}
        attrs = payload.get("object_attributes") or {}
        project_id = project.get("id")
        project_path = project.get("path_with_namespace", "")
        repo_web_url = project.get("web_url", "")
        iid = attrs.get("iid")
        name = workspace_name(project_path, iid)

        # 1. Confirm the assignee maps to a Coder user. Fail closed on 404.
        try:
            user = self.coder.get_user(assignee)
        except CoderError as e:
            return self._coder_error(log, "lookup user", e)
        if user is NOT_FOUND:
            log.warn("coder user not found", assignee=assignee)
            return 422, {"ok": False,
                         "error": f"coder user not found: {assignee}; "
                                  "sign into Coder via Keycloak first"}

        # 2. Idempotency: an existing workspace of this name is a no-op.
        try:
            existing = self.coder.get_workspace_by_name(assignee, name)
        except CoderError as e:
            return self._coder_error(log, "lookup workspace", e)
        if existing is not NOT_FOUND:
            log.info("workspace exists, reusing", workspace=name)
            ws_url = self.workspace_link(assignee, name)
            return 200, {"ok": True, "action": "exists", "mode": mode,
                         "owner": assignee, "workspace": name,
                         "workspace_url": ws_url}

        # 3. Resolve the template version selected by the label slug.
        version_id, template_name = self.resolve_template_version(mode, slug)
        if not version_id:
            log.warn("template not found", template=template_name)
            return 422, {"ok": False,
                         "error": f"template not found in coder: {template_name}"}

        # 4. Create the workspace (human-in-the-loop) or the AI task (agent).
        try:
            if mode == MODE_WORKSPACE:
                rich = self.git_repo_params(version_id, repo_web_url)
                created = self.coder.create_workspace(
                    assignee, version_id, name, rich)
            else:
                issue = self._fetch_issue(project_id, iid, log)
                prompt = build_seed_prompt(
                    project_path, iid, repo_web_url,
                    (issue or attrs).get("title", ""),
                    (issue or attrs).get("description", ""),
                    issue_url(payload))
                created = self.coder.create_task(
                    assignee, version_id, name, prompt)
        except CoderError as e:
            return self._coder_error(log, "create " + mode, e)

        ws_url = self.workspace_link(assignee, name)
        wid = created.get("id") if isinstance(created, dict) else None
        log.info("spawn ok", mode=mode, owner=assignee, workspace=name,
                 template=template_name, id=wid)

        # 5. Best-effort comment back on the issue (async, never blocks 201).
        if project_id and iid:
            threading.Thread(
                target=self._comment_back,
                args=(project_id, iid, mode, assignee, ws_url, log),
                daemon=True).start()

        return 201, {"ok": True, "action": "created", "mode": mode,
                     "owner": assignee, "workspace": name,
                     "workspace_url": ws_url, "template": template_name}

    def _fetch_issue(self, project_id, iid, log):
        if not (project_id and iid):
            return None
        try:
            return self.gitlab.get_issue(project_id, iid)
        except Exception as e:  # noqa: BLE001 - fall back to webhook attrs
            log.warn("gitlab GetIssue failed; using webhook attrs", err=str(e))
            return None

    def _comment_back(self, project_id, iid, mode, owner, ws_url, log):
        if mode == MODE_AGENT:
            body = ("Coder agent dispatched. The workspace and agent are owned "
                    f"by @{owner}: {ws_url}")
        else:
            body = f"Coder workspace ready, owned by @{owner}: {ws_url}"
        body += "\n\n_Posted by the GitLab to Coder attribution bridge._"
        try:
            self.gitlab.post_issue_comment(project_id, iid, body)
        except Exception as e:  # noqa: BLE001 - best effort
            log.error("issue comment failed", err=str(e))

    def _coder_error(self, log, op, err):
        log.error("coder api error", op=op, status=err.status, body=err.body)
        status = 502 if err.status >= 500 else err.status
        return status, {"ok": False, "error": f"{op} failed", "detail": err.body}


# ===========================================================================
# http server (mirrors main.go wiring)
# ===========================================================================

def _urlquote(s):
    return urllib.request.quote(str(s), safe="")


BRIDGE = None  # set in main()
LOG = None     # set in main()


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
            ready = BRIDGE.coder.ping()
            return self._json(200 if ready else 503, {"ok": bool(ready)})
        self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self):  # noqa: N802
        if self.path != "/webhook":
            return self._json(404, {"ok": False, "error": "not found"})
        req_id = "%08x" % (int(time.time() * 1000) & 0xffffffff)
        log = _Bound(LOG, request_id=req_id)
        got = self.headers.get("X-Gitlab-Token", "")
        if not verify_token(got, BRIDGE.cfg.webhook_secret):
            log.warn("webhook auth failed", remote=self.client_address[0])
            return self._json(401, {"ok": False, "error": "unauthorized"})
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0 or length > (1 << 20):
            return self._json(400, {"ok": False, "error": "bad length"})
        try:
            payload = json.loads(self.rfile.read(length).decode())
        except ValueError:
            return self._json(400, {"ok": False, "error": "invalid json"})
        attrs = payload.get("object_attributes") or {}
        project = payload.get("project") or {}
        log = _Bound(LOG, request_id=req_id, object_kind=payload.get("object_kind"),
                     action=attrs.get("action"), iid=attrs.get("iid"),
                     project=project.get("path_with_namespace"))
        try:
            status, body = BRIDGE.handle_issue(payload, log)
        except Exception as e:  # noqa: BLE001
            log.error("handler panic", err=str(e))
            return self._json(500, {"ok": False, "error": str(e)})
        self._json(status, body)

    def log_message(self, fmt, *args):  # silence default access log
        return


class _Bound:
    """A logger with bound structured fields, like slog's With()."""

    def __init__(self, logger, **fields):
        self._logger = logger
        self._fields = fields

    def _call(self, level, msg, f):
        getattr(self._logger, level)(msg, **{**self._fields, **f})

    def debug(self, msg, **f):
        self._call("debug", msg, f)

    def info(self, msg, **f):
        self._call("info", msg, f)

    def warn(self, msg, **f):
        self._call("warn", msg, f)

    def error(self, msg, **f):
        self._call("error", msg, f)


def main():
    global BRIDGE, LOG
    cfg = Config()
    err = cfg.validate()
    LOG = Logger(cfg.log_level)
    if err:
        LOG.error("config load failed", err=err)
        sys.exit(2)
    coder = CoderClient(cfg.coder_url, cfg.coder_token)
    gitlab = GitLabClient(cfg.gitlab_api, cfg.gitlab_pat)
    BRIDGE = Bridge(cfg, coder, gitlab, LOG)

    host, _, port = cfg.listen_addr.partition(":")
    server = ThreadingHTTPServer((host or "", int(port or "8080")), Handler)
    LOG.info("bridge listening", addr=cfg.listen_addr, coder_url=cfg.coder_url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        LOG.info("shutdown initiated")
        server.shutdown()


if __name__ == "__main__":
    main()
