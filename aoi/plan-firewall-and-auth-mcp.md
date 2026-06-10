# AOI Gap Remediation Plan: Agent Firewall + Authenticated MCP

Status: PLAN for review. Nothing in here is applied yet. Target: live demo
Thu 2026-06-11 on `dev.usgov.coderdemo.io` (Coder v2.34.1, GovCloud).

Addresses the two main gaps flagged in `aoi/gaps-aoi.md` (agent firewall missing;
no authenticated MCP), plus other gaps found while planning. Grounded in
read-only research against the Coder source and live probes this session.

Legend: [CRITICAL] demo-blocking for the AOI story. Effort: S (under ~1h),
M (a few hours), L (most of a day). All items below are reversible.

---

## Gap 1: Agent Firewall (Coder Boundary) [CRITICAL] [IMPLEMENTED + VALIDATED]

### Status (2026-06-09): DONE on a new `firewalled` template
Implemented and validated live on `dev.usgov.coderdemo.io`. A new template
`coder-templates/firewalled/` (a copy of `claude-code` with the firewall on)
is pushed to the `coder` org, and `austenplatform/firewall-test` runs Claude
Code jailed. See "As-built" below; the original design notes are retained
for context.

### What it is
A process-level network egress firewall that wraps the agent and enforces an
HTTP(S) allowlist (domain + method + path), streaming every allow/deny decision
to the control plane. It is network egress control, not a shell-command
sandbox: a "blocked command" in the demo means a command whose egress is denied
(for example `curl https://example.com`), not the command being refused. This
is the data-exfiltration / DLP guardrail story for the AOI.

### Mechanism and entitlement (already satisfied)
- Delivered as the embedded `coder agent-firewall` subcommand (Coder v2.30+).
  The Claude Code module 4.7.3 (already pinned) invokes it via `enable_boundary`.
- Backend: landjail (Landlock V4, no added capabilities, recommended) or nsjail
  (transparent interception, needs `NET_ADMIN`, stronger isolation fallback).
- License: AI Governance add-on gates it. Already entitled live
  (`ai_governance_user_limit: 30`; AI Bridge runs on the same add-on).
- Kernel/AMI: AL2023 kernel 6.18 exceeds the landjail 6.7 floor; user
  namespaces enabled in-pod. No AMI or nodepool change.

### Preflight (one read-only node check before enabling)
Confirm Landlock is in the active LSM stack (could not be read from inside an
unprivileged pod):
```
cat /sys/kernel/security/lsm   # expect a list including "landlock"
```
If `landlock` is absent, use the nsjail + `NET_ADMIN` path (still in-pod).

### As-built (what actually shipped, supersedes the spec above)
The `claude-code` module 4.7.3 already supports Boundary natively, so no
custom variables or hand-written `coder_script` were needed. The `firewalled`
template sets, inside `module "claude_code"`:
```hcl
enable_boundary       = true
use_boundary_directly = true   # standalone boundary binary (MIT)
boundary_version      = "latest"
pre_install_script    = <writes ~/.config/coder_boundary/config.yaml>
```
Key findings from implementation:
- The module passes NO `--allow` / `--jail-type` flags, so the allowlist and
  jail type come ONLY from `~/.config/coder_boundary/config.yaml`, written by
  `pre_install_script` before Claude Code launches. Config used:
  `allowlist: [domain=dev.usgov.coderdemo.io, domain=gitlab.usgov.coderdemo.io]`,
  `jail_type: landjail`, `log_dir: /tmp/boundary_logs`, `log_level: warn`.
- `use_boundary_directly = true` was REQUIRED. The default path runs the
  `coder boundary` subcommand, which verifies the deployment license through
  an authenticated client; the agent carries only an agent token (no user
  session), so that path errors with "not logged in". The standalone
  `boundary` binary (installed v0.9.0 via the module install script) has no
  license/login dependency.
- Preflight passed: the node LSM stack is
  `lockdown,capability,landlock,yama,safesetid,selinux,bpf,ima` (landlock
  present), AL2023 kernel 6.18. landjail needs no added pod capabilities, so
  the pod security context was left unchanged (no nsjail / NET_ADMIN).

### Verification results (live)
- Process tree confirms the jail: `agentapi server ... -- boundary -- claude
  --session-id ...` (Claude Code is a child of boundary).
- Allow/deny enforced from a workspace terminal (use a free `--proxy-port`
  since the agent's boundary owns 8080): gateway buildinfo = 200 (allow),
  gitlab = 302 (allow), example.com = 403 (deny), github.com = 403 (deny).
- coderd emits `boundary_request` audit lines (owner, workspace_name,
  agent_name, decision, http_url, template_id, ...). Real captured denies:
  Claude Code's own calls to `api.anthropic.com` (eval + event_logging) and
  `raw.githubusercontent.com` (update check) are decision=deny, while
  inference through the allowlisted gateway works. This is the exact
  data-exfiltration / DLP story, with attribution, on demand.

### Rollback
Use the un-firewalled `claude-code` template, or set `enable_boundary = false`
and re-push. Running pods survive (`ignore_changes = all`).

### Original design notes (pre-implementation, retained for context)
1. Two default-off variables:
```hcl
variable "enable_agent_firewall" { type = bool   default = false }
variable "agent_firewall_jail_type" { type = string default = "landjail" }
```
2. One line in the `module "claude_code"` block:
```hcl
enable_boundary = var.enable_agent_firewall
```
3. A flag-gated `coder_script` that writes `~/.config/coder_boundary/config.yaml`.
   Environment-specific allowlist (critical: egress is in-boundary via the AI
   Gateway, so DO NOT allow `api.anthropic.com`; DO allow the Coder domain and
   the in-cluster GitLab host):
```yaml
allowlist:
  - "domain=dev.usgov.coderdemo.io"      # reach the in-boundary AI Gateway (required)
  - "domain=gitlab.usgov.coderdemo.io"   # in-cluster GitLab SCM (confirm exact host)
jail_type: landjail
log_dir: /tmp/boundary_logs
proxy_port: 8087
log_level: warn
```
4. nsjail fallback only: if `agent_firewall_jail_type == "nsjail"`, add
   `capabilities.add = ["NET_ADMIN"]` to the container security context. The
   default landjail path leaves the pod security context unchanged.

### Demo, verification, rollback (original notes)
- Demo: in the workspace, `curl https://dev.usgov.coderdemo.io/api/v2/buildinfo`
  (allowed) vs `curl https://example.com` (denied). Claude Code keeps working
  because the gateway domain is allowlisted.
- Proof: coderd emits a structured `boundary_request` log per decision
  (`decision=allow|deny`, `http_url`, `matched_rule`, `workspace_id`,
  `template_id`). The boundary Grafana dashboard (already shipped) parses these
  via Loki and lights up once a workspace runs the firewall (reads 0 today).
- Prometheus series name (RESOLVED): the dashboard's
  `agent_boundary_log_proxy_batches_forwarded_total` is CORRECT, confirmed
  from source `agent/boundarylogproxy/metrics.go` (Namespace `agent`,
  Subsystem `boundary_log_proxy`, Name `batches_forwarded_total`). The
  prefix-less spelling in `docs/architecture/agent-firewall-feasibility.md`
  is wrong; the observability brief tracks that one-line fix.
- Rollback: set `enable_agent_firewall = false` (the default) and re-push the
  template. Running pods survive (`ignore_changes = all`); a restart re-rolls
  without the jail. No infra-layer change to revert.

### Risks
- Landlock-in-LSM preflight (mitigated by nsjail fallback).
- Allowlist is load-bearing: omitting the Coder domain breaks Claude Code.
- Egress-only scope under landjail (no UDP/PID isolation); frame precisely as
  network egress control. Use nsjail for a hardened story.

Effort: S. Owner: platform.

---

## Gap 2: Authenticated MCP [CRITICAL for the AOI auth story]

Goal: demonstrate an MCP tool that requires real authentication and enforces
need-to-know, narrated as "Coder x an internal authenticated service." The
proposed backend is GitHub's hosted MCP (the auth genuinely works), with an
in-boundary fallback that keeps optics clean.

### Backend: GitHub remote MCP (verified specifics)
- URL `https://api.githubcopilot.com/mcp/`, transport `streamable_http`.
- Auth: OAuth (per-user) or PAT (`Authorization: Bearer <token>`).
- Read-only safety: send header `X-MCP-Readonly: true`.
- It clears GitLab blocker #2: its RFC 9728 `resource` is a string (not the JSON
  array that broke Coder's parser). But it advertises no DCR
  `registration_endpoint`, so Coder zero-config oauth2 (auto-DCR) will fail;
  oauth2 must be MANUAL (pre-registered GitHub OAuth App). GitHub OAuth
  endpoints: authorize `https://github.com/login/oauth/authorize`, token
  `https://github.com/login/oauth/access_token`.

### THE GATE (must verify first): 204 vs 202
Coder's MCP client (`mark3labs/mcp-go` v0.38.0) accepts only HTTP 200/202 on the
`notifications/initialized` POST; GitLab returned 204 and was dropped
(CODAGT-570). GitHub's status on that notification is unverifiable without a
token (unauth `initialize` returns 401; the `/_ping` 200 is a different path).
Gate procedure: mint a fine-scoped GitHub PAT, run `initialize` then
`notifications/initialized`, and read the status line; 200/202 = good, 204 =
GitHub MCP unusable as-is. Most authoritative: register it in Coder with
`api_key` + the PAT and watch coderd logs for "skipping MCP server due to
connection failure ... status 204". Do this BEFORE committing the demo to GitHub.

### Paths
- Path A (recommended for speed): `api_key` + fine-scoped PAT. Simplest,
  genuinely authenticated, and the same call that clears the gate. Caveat: a
  single PAT is one shared identity, so the per-user need-to-know story needs
  per-user PATs (one server per demoed user) or Path B.
- Path B (best per-user RBAC headline): manual `oauth2` + a pre-created GitHub
  OAuth App whose callback is
  `https://dev.usgov.coderdemo.io/api/experimental/mcp/servers/{id}/oauth2/callback`.
  Each user clicks Connect once; Coder stores a per-user GitHub token; users see
  only what their GitHub identity can access. Sequencing note: the callback
  needs the Coder server `{id}`, so create the Coder MCP row first (or use a
  placeholder app), then set the OAuth App callback, then patch client id/secret.
- Fallback C (clean GovCloud optics, fully in-boundary): add auth to our
  existing datastore MCP (`deploy/datastore-mcp`). Ranked: (1) manual `oauth2`
  via Keycloak (real per-user, in-boundary, best optics), (2) `user_oidc` (Coder
  forwards the user's OIDC token; the MCP must verify audience), (3) `api_key`
  (shared, simplest). It must also pass the 202 gate, which we control since it
  is our code.

### Registration request (api_key example; `api_key_value` must include `Bearer`)
```json
{
  "display_name": "GitHub (Internal Service)",
  "slug": "github",
  "transport": "streamable_http",
  "url": "https://api.githubcopilot.com/mcp/",
  "auth_type": "api_key",
  "api_key_header": "Authorization",
  "api_key_value": "Bearer <fine_scoped_PAT>",
  "tool_allow_list": ["get_me","search_repositories","get_repository","search_code","list_issues","get_issue"],
  "availability": "default_off",
  "enabled": true
}
```
(oauth2 variant: drop the api_key fields and set `auth_type: oauth2` plus
`oauth2_client_id/secret`, `oauth2_auth_url`, `oauth2_token_url`,
`oauth2_scopes: "read:user repo read:org"`.)

### Egress / optics
Both GitHub options egress to public GitHub. The narration is "internal
service," but packets and tokens leave the boundary. Mitigate with read-only
tools + `X-MCP-Readonly`, a throwaway demo org/repo, and a scoped PAT; or, if
optics must be clean, make Fallback C (in-boundary) the primary and use GitHub
only as a "real external SaaS" bonus.

Effort: api_key S; oauth2 M; in-boundary fallback M to L.

---

## Other gaps (prioritized)

1. Agent attribution / non-repudiation (WS-23, staged, security review pending).
   Who-did-what for agent actions is a core AOI governance capability. Plan:
   complete the security review, then apply `setup-pm-persona.py` /
   `setup-gitlab-agent-webhook.py` (both `--plan` default). Effort M.
2. Audit and observability readiness. Coder audit log + AI Gateway (aibridge)
   and boundary Grafana dashboards already exist. Verify they show live data for
   the demo flow (boundary lights up after Gap 1; aibridge already does).
   Effort S, verification only.
3. Need-to-know data isolation as one narrative thread. Tie together orgs/groups
   RBAC, the per-group/per-user spend limits, and the authenticated MCP (Gap 2)
   into a single "this user sees only their mission's data and budget" story. No
   new build; rehearsal/narrative.
4. Workspace template golden-path e2e (WS-25 remaining): a one-time owner GitLab
   OAuth login, then build one workspace per template and run a connectivity
   check. Readiness gap if templates are part of the flow. Effort M.
5. DLP / guardrails segment: pair the firewall (Gap 1) with the authenticated,
   read-only MCP (Gap 2) as the "agent guardrails" portion of the demo.

---

## Recommended sequencing for Thursday

1. Preflight: confirm `landlock` in the node LSM stack (5 min).
2. Enable firewall on `claude-code` (template edit + push + 1 workspace), verify
   allow/deny + dashboard + `boundary_request` audit lines. [Gap 1]
3. Gate GitHub MCP: register with `api_key` + PAT in a throwaway test, watch
   coderd logs for the 204 failure. [Gap 2 gate]
4. If the gate passes and egress optics are acceptable: keep GitHub MCP
   (api_key for speed, or oauth2 for the per-user RBAC headline). If the gate
   fails or optics must stay in-boundary: stand up the authenticated datastore
   MCP (Fallback C). [Gap 2]
5. Optional: apply attribution (WS-23) after security review; verify
   audit/observability; rehearse the need-to-know narrative.

---

## Open questions for you

1. GitHub: which org/account and repos for the OAuth App / PAT? Is calling
   `github.com` acceptable for demo optics, or must the authenticated MCP stay
   in-boundary (then we do Fallback C as primary)?
2. Auth headline: per-user RBAC (`oauth2`) or fastest-authenticated (`api_key`)?
3. Firewall backend: landjail (zero-touch) or nsjail (stronger isolation)?
4. Include agent attribution (WS-23) in this demo, or defer past Thursday?
5. Anything in `aoi/gaps-aoi.md` not covered here? I have not seen that file yet
   (another agent is writing it); I will reconcile once it lands.

---

## Top risks

- The 204/202 gate (Gap 2) is the single biggest risk. Mitigated by gating
  first and by the in-boundary fallback.
- Firewall landlock LSM preflight. Mitigated by the nsjail fallback.
- GovCloud egress optics for GitHub MCP. Mitigated by the in-boundary fallback.
- Time: every item is S or M and reversible; the demo is Thursday.
