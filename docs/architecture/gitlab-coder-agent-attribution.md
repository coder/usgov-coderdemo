# GitLab to Coder bridge: AI-agent attribution (WS-23)

Status: DESIGN, authored and STAGED. Nothing in this document has been applied
to the live cluster, GitLab, Coder, Keycloak, or AWS. The apply path is in
`docs/swarm/handoffs/WS-23-handoff.md`.

## Objective

A project manager (PM) assigns a GitLab issue to a developer. That assignment
spawns Coder work owned by and attributed to the assigned developer, not a
shared bot account: either a plain workspace the developer opens, or an
autonomous Coder AI-agent task. The audit trail, the workspace list, and any
resulting Merge Request all point back to the real developer.

This design replicates the proven Red Hat Summit 2026 demo "bridge" service and
adapts it to this environment: self-hosted GitLab as SCM and the stable Coder
2.34 Tasks API for attribution.

Two verified sources ground the design:

- The Coder 2.34 source at `reference/coder` (commit `47a8c9572f`), for the real
  Tasks and workspace API surface and its authorization model.
- The Red Hat Summit bridge at `reference/demo-aigov-rhsummit-2026`, whose shape
  and responsibilities we replicate.

## The rhsummit bridge we replicated (provenance)

The reference bridge is a small Go HTTP service. Files studied (read only, no
code copied), under `reference/demo-aigov-rhsummit-2026`:

| File | Responsibility |
|---|---|
| `services/bridge/cmd/bridge/main.go` | Process wiring, graceful shutdown, JSON logging |
| `services/bridge/internal/config/config.go` | Env load and required-var validation |
| `services/bridge/internal/coder/coder.go` | Minimal Coder API client |
| `services/bridge/internal/gitlab/gitlab.go` | Issue read and note (comment) back |
| `services/bridge/internal/webhook/webhook.go` | Payload, constant-time token verify, label vocabulary, workspace naming |
| `services/bridge/internal/handler/handler.go` | `/webhook` `/healthz` `/readyz`, spawn logic, idempotency |
| `services/bridge/Dockerfile` | Distroless static runtime |
| `manifests/bridge/{deployment,service,route}.yaml` | In-cluster placement in the `coder` namespace |
| `scripts/gitlab-register-bridge-webhook.sh` | Idempotent webhook registration |
| `docs/identity-architecture.md` | Issue-assignment to workspace hero flow |

What the rhsummit bridge does, precisely:

- Receives GitLab Issues Hook POSTs at `/webhook`. Verifies `X-Gitlab-Token`
  against a configured shared secret in constant time (GitLab sends the secret
  verbatim, no HMAC).
- Acts only on `object_kind == "issue"`, action in `{open, update, reopen}`, a
  `coder-*` label, AND a non-empty assignee list. Anything else is a no-op 200.
- Two label modes: `coder-workspace[:slug]` creates a plain workspace the
  assignee opens; `coder-agent[:slug]` creates a workspace plus an autonomous
  chat. Agent wins when both labels are present.
- Attribution is the issue ASSIGNEE, never the actor or author (the author is
  usually the PM). The first assignee is the workspace owner.
- Workspace name is deterministic, `<repo>-issue-<iid>`, sanitized to
  `[a-z0-9-]` and truncated to Coder's 32-char limit while preserving the
  `-issue-<iid>` suffix.
- Idempotent: an existing workspace is reused, an existing agent chat is reused
  (deduped by labels `bridge.source=gitlab`, `gitlab.project`, `gitlab.iid`).
- Wires the GitLab project web URL into the template's `git_repo` rich
  parameter so webhook-driven workspaces track the issue's repo.
- For agent mode it resolves a chatd model from the slug (highest version
  wins), mints a per-user Coder token (because the experimental chat endpoint
  hardcodes `owner_id` to the caller), and creates the chat as that user with a
  seed prompt that embeds the issue title and body.
- Posts a note back on the issue with the workspace, code-server, and chat URLs.

## How we replicated it here (and what changed)

The staged implementation is a single pure standard-library Python program,
`deploy/coder/agent-attribution/bridge.py`, whose sections mirror the rhsummit
Go packages (config, coder client, gitlab client, webhook helpers, handler).
Pure stdlib so it runs on a stock `python:3.12-slim` image mounted from a
ConfigMap, no build step, fully reversible. The header of `bridge.py` carries
the same same-vs-adapted breakdown, file by file.

Same as rhsummit: the three endpoints, constant-time token verification, the
actionable filter, the two label modes with agent-wins precedence, assignee
attribution, the deterministic 32-char workspace name, workspace-existence
idempotency, and the best-effort issue comment back.

Adapted for GitLab plus Coder 2.34:

1. SCM is self-hosted GitLab. Webhook auth is `X-Gitlab-Token`; the comment-back
   uses the GitLab Notes API with a `PRIVATE-TOKEN` admin PAT.
2. Agent dispatch uses the STABLE Tasks API, `POST /api/v2/tasks/{assignee}`,
   whose path parameter sets the workspace OWNER to the assignee. This replaces
   the rhsummit experimental-chat path and removes its per-user-token minting
   step (see the attribution section). One service-account token attributes the
   work.
3. `coder-agent:<slug>` selects a TEMPLATE by name, not a chatd model. Coder
   2.34 Tasks does not expose chatd model configs; model choice lives inside the
   AI-task template and the AI Gateway. The rhsummit highest-version model-slug
   logic is intentionally dropped.
4. `CreateTaskRequest` carries no `rich_parameter_values` (only
   `template_version_id`, `input`, `name`, `display_name`, preset; see
   `reference/coder/codersdk/aitasks.go:15`). The `claude-code` template exposes
   an `ai_prompt` parameter that Coder fills from `input`, so issue context is
   delivered through the seed prompt rather than a `git_repo` parameter.
5. Workspace mode wires `git_repo` only when the template version actually
   declares it (checked via `GET /api/v2/templateversions/{id}/rich-parameters`,
   `reference/coder/codersdk/templateversions.go:133`). `claude-code` does not
   declare `git_repo`, so the bridge omits it there and keeps the promise for
   templates that do.
6. `coder-task[:slug]` is retained as an alias for `coder-agent[:slug]` for
   continuity with earlier WS-23 issues and tooling.

## (a) Trigger: webhook on issue events, gated by label plus assignee

A GitLab project webhook on Issue events. Gate on two conditions that must both
hold: a `coder-*` label AND a non-empty assignee. The assignee is the
attribution target; the actor or author is not used as the owner.

Why issue events and not a CI job: assigning an issue does not start a pipeline,
so a CI path would still need a webhook to bounce the event into a `trigger`
pipeline, which is strictly more moving parts. A webhook delivers the issue
payload directly with low latency, as a single observable hop. This is exactly
the rhsummit gating (`webhook.go` `IsActionable`, `ExtractMode`,
`FirstAssignee`; `handler.go`).

Label vocabulary (mirrors the Summit bridge, mapped to this environment):

- `coder-workspace[:<template-slug>]` creates a plain workspace.
- `coder-agent[:<template-slug>]` (and the `coder-task` alias) dispatches an AI
  task on a template that declares `coder_ai_task` (default `claude-code`).

Optional extension (documented, not enabled): also subscribe to Note events so a
comment slash command could trigger the flow. That adds a second trust surface
(free-text comments), so the demo keeps to the label plus assignee path.

## (b) Receiver: a tiny in-cluster bridge

A small in-cluster Deployment in the `coder` namespace behind a ClusterIP
Service, exactly the rhsummit placement (`manifests/bridge/`). GitLab runs
in-cluster on `gitlab-0`, so delivery is a single in-cluster hop to
`http://agent-attribution-bridge.coder.svc.cluster.local:8080/webhook`. No
public exposure is required.

Why in-cluster, not CI-over-webhook: one observable, idempotent process holds
exactly one scoped Coder credential, so blast radius and rotation are easy to
reason about; it shares the `coder` namespace network and security posture with
the Coder server; and there is no runner dependency or public ingress.

GitLab blocks webhooks to local addresses by default. Two safe options, both in
the deploy README: enable "Allow requests to the local network from webhooks"
and target the Service URL (lowest exposure), or expose the bridge via ingress
and target an https URL.

## (c) Attribution and auth model

The workspace must be owned by the specific developer. Three mechanisms were
evaluated against the verified 2.34 source.

### Option ii (recommended): service account creates on behalf of the assignee

The Coder 2.34 Tasks and workspace endpoints take the owner as a path
parameter, so a single service-account token can create work owned by the
assignee.

- Agent: `POST /api/v2/tasks/{user}` with
  `CreateTaskRequest{TemplateVersionID, Input, Name}`. SDK
  `reference/coder/codersdk/aitasks.go:24` (function) and `:15` (request shape).
  Route `reference/coder/coderd/coderd.go:1185` registers `/tasks`, and `:1190`
  wraps `/{user}` with `httpmw.ExtractOrganizationMembersParam(...)` before
  `POST -> api.tasksCreate` (`:1192`). Handler
  `reference/coder/coderd/aitasks.go:48` (`tasksCreate`) resolves the owner from
  the `{user}` path param, then calls `createWorkspace(ctx, ..., apiKey.UserID,
  api, owner, ...)` (`coderd/aitasks.go:195`): caller is the service account,
  owner is the assignee. The template version must expose `coder_ai_task`, else
  400 (`coderd/aitasks.go:97`). `coder-templates/claude-code` declares
  `resource "coder_ai_task"`.
- Workspace: `POST /api/v2/users/{user}/workspaces` with
  `CreateWorkspaceRequest{TemplateVersionID, Name, RichParameterValues}`. SDK
  shape `reference/coder/codersdk/organizations.go:242`; route registered at
  `reference/coder/coderd/coderd.go:1667` (`api.postUserWorkspaces`).
- Authorization: `createWorkspace` checks
  `AuthorizeContext(ctx, policy.ActionCreate,
  rbac.ResourceWorkspace.InOrg(template.OrganizationID).WithOwner(owner.ID))`
  (`reference/coder/coderd/workspaces.go:557` and `:574`). The service account
  must be allowed to create a workspace owned by another user in that org.

Result: one dedicated service account, no per-user token storage, and a
workspace genuinely owned by and attributed to the developer. The audit log
records initiator = service account and owner = developer, the correct and
honest representation of "the platform created this on the developer's behalf".

Key advantage over rhsummit: the older experimental chat endpoint
`POST /api/experimental/chats` hardcodes `owner_id` to the caller, which forced
the Summit bridge to mint a per-user token first (see
`reference/demo-aigov-rhsummit-2026/services/bridge/internal/coder/coder.go:233`
and `:248`). The stable Tasks API has no such limitation, so option ii is
cleaner on 2.34 than the path the Summit demo had to take, and the same token
serves both modes.

### Option i: per-user Coder API tokens

The service account mints a token for the assignee with
`POST /api/v2/users/{user}/keys/tokens`
(`reference/coder/codersdk/apikey.go:63`), then calls as that user. Also yields
correct ownership and makes the audit initiator the user. The cost is token
lifecycle: the minting right is itself powerful, and tokens must be short-lived
and never persisted. Kept as a fallback for endpoints that hardcode the caller
as owner (the experimental chat path); unnecessary for Tasks.

### Option iii: user impersonation

Coder 2.34 exposes no first-class session impersonation endpoint (no such call
in `codersdk/users.go`). The closest supported mechanism is token minting
(option i). True impersonation is sensitive and is not used.

### Decision

Use option ii. Create a dedicated Coder service account `coder-task-bot` with a
least-privilege custom role in org `coder`
(`5de29a6d-8836-4643-a42b-2cb807c8e3e2`) granting workspace create, template
read, and organization member read. A coarser fallback is Organization Admin of
org `coder` only (never site Owner). The token is stored in AWS Secrets Manager
and synced into the cluster by ESO, never committed to git.

## (d) Idempotency and duplicate avoidance

GitLab re-delivers webhooks and fires an `update` action on every issue edit, so
the bridge must be a no-op after the first successful spawn.

- Deterministic name `<repo>-issue-<iid>` (the Summit `WorkspaceName` rule).
  Passing `Name` to the Tasks API makes both the task and workspace names
  deterministic (`coderd/aitasks.go:137` sets the workspace request `Name` from
  the task name).
- Existence check before create: look up the workspace by owner and name
  (`GET /api/v2/users/{user}/workspace/{name}`). If it exists, return a no-op
  200, regardless of mode.
- Action gate: only act on `{open, update, reopen}` with both a coder-* label
  and an assignee.

Divergence from rhsummit: the Summit bridge could layer a new chat onto an
already-existing workspace (workspace created by a `coder-workspace` trigger,
chat added later by a `coder-agent` trigger). Here the unit is the workspace or
the Task, and both occupy the same deterministic name, so once
`<repo>-issue-<iid>` exists the bridge is a no-op. To switch a plain workspace
to an agent task (or vice versa), delete the workspace first.

## (e) Minimal, safe demo-day happy path

1. PM Morgan Pierce (`morgan.pm`) opens or reuses an issue in
   `coderdemo/coder-templates`, assigns it to a developer (for example
   `dana.dev`), and adds `coder-agent` (autonomous) or `coder-workspace` (plain).
2. GitLab fires the Issue webhook to the in-cluster bridge.
3. The bridge verifies the `X-Gitlab-Token` shared secret, confirms the assignee
   maps to a Coder user, resolves the template active version, and for
   `coder-agent` creates the task with `POST /api/v2/tasks/dana.dev`. The
   workspace and agent are owned by `dana.dev`.
4. The bridge posts a comment back on the issue with the workspace link.
5. The audience sees the workspace and agent under `dana.dev`, not a shared bot.
   With WS-22 Agent Firewall enabled, agent egress is sandboxed and all model
   traffic flows through the in-cluster AI Gateway.

No-bridge fallback that is also safe to show: an operator runs
`scripts/setup-gitlab-agent-webhook.py --simulate --issue <iid>`, which prints
the exact attributed call (Tasks for agent mode, users/workspaces for workspace
mode), and with `--apply` performs that single call live. This demonstrates
attribution even before the bridge Deployment is rolled out.

## Security review surface (must be approved before going live)

1. Service-account token scope and blast radius. The `coder-task-bot` token can
   create workspaces and tasks owned by any user in org `coder`. It must be a
   dedicated service account with a least-privilege custom role (workspace
   create, template read, organization member read) bound to org `coder` only, a
   short token lifetime with rotation, storage in ASM and ESO sync, never in
   git. Audit must show initiator = service account and owner = developer.
2. Webhook authenticity and input trust. GitLab sends the shared secret verbatim
   in `X-Gitlab-Token` (no HMAC), compared in constant time. Enforce TLS, scope
   the hook to the single project (`coderdemo/coder-templates`, id 2), trust only
   the assignee plus label as the trigger, never the actor, and dedupe via the
   deterministic name to prevent a workspace flood. The issue body becomes the
   agent prompt, so treat it as untrusted input: run the agent under the WS-22
   Agent Firewall egress sandbox and the AI Gateway, and never expose the
   service-account token to the agent workspace.
3. Identity mapping integrity. Attribution assumes the GitLab username equals the
   Coder username, both provisioned from Keycloak realm `coder`. If a GitLab
   username does not resolve to a Coder user, fail closed; never fall back to a
   shared bot owner. The assignee must have signed into Coder at least once so
   the JIT account exists. Confirm the PM cannot escalate by self-assigning,
   since the owner is always the assignee.

## Identity and name reference

| Thing | Value |
|---|---|
| Coder primary org | `coder` (`5de29a6d-8836-4643-a42b-2cb807c8e3e2`) |
| AI-agent template | `claude-code` (declares `coder_ai_task`, `ai_prompt`) |
| Service account | `coder-task-bot` (custom role, org `coder` only) |
| Coder in-cluster API | `http://coder.coder.svc.cluster.local` |
| Coder public API | `https://dev.usgov.coderdemo.io` |
| GitLab API | `https://gitlab.usgov.coderdemo.io/api/v4` |
| Project | `coderdemo/coder-templates` (id 2), group `coderdemo` (id 13) |
| PM persona | Morgan Pierce, `morgan.pm` (realm `coder`) |
| Bridge | `agent-attribution-bridge` Deployment, ns `coder` (`bridge.py`) |
| Labels | `coder-workspace[:tmpl]`, `coder-agent[:tmpl]`, `coder-task` (alias) |
| ASM secret | `usgov-coderdemo/agent-attribution/bridge` |
| ESO store | `ClusterSecretStore/aws-secretsmanager` |
