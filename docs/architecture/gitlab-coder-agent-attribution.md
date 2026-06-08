# GitLab to Coder AI-agent attribution (WS-23)

Status: DESIGN, authored and STAGED. Nothing in this document has been applied
to the live cluster, GitLab, Coder, Keycloak, or AWS. The apply path is in
`docs/swarm/handoffs/WS-23-handoff.md`.

## Objective

A project manager (PM) assigns a GitLab issue to a developer. That assignment
spawns a Coder AI-agent workspace (a Coder Task) that does the work, owned by
and attributed to the assigned developer, not a shared bot account. The audit
trail, the workspace list, and any resulting Merge Request all point back to the
real developer.

This design is grounded in two verified sources:

- The Coder 2.34 source at `reference/coder` (commit `47a8c9572f`), for the real
  Tasks API surface and its authorization model.
- The Red Hat Summit demo at `reference/demo-aigov-rhsummit-2026`, which already
  ships a production-shaped GitLab to Coder bridge. We reuse its proven shape and
  adapt the attribution mechanism to the stable Coder 2.34 Tasks API.

## (a) Trigger: webhook on issue events, gated by label plus assignee

Recommendation: a GitLab project webhook on Issue events. Gate the action on two
conditions that must both hold: a `coder-task` label is present AND the issue has
an assignee. The assignee is the attribution target. The actor or author is not
used as the owner, because the author is typically the PM.

Why issue events and not a CI job:

- The demo trigger is "issue assigned to a developer". Assigning an issue does
  not start a CI pipeline. CI pipelines run on push, Merge Request, schedule, or
  the pipeline trigger API. To drive the flow from CI you would still need a
  webhook to bounce the issue event into a `trigger` pipeline, which is strictly
  more moving parts for the same result.
- A webhook delivers the issue payload (project, issue IID, assignees, labels)
  directly, with low latency, and is observable as a single hop.

The Red Hat Summit bridge uses exactly this gating: object kind `issue`, action
in `{open, update, reopen}`, a `coder-*` label, and a first assignee, otherwise a
no-op. See `reference/demo-aigov-rhsummit-2026/services/bridge/internal/webhook/webhook.go`
(`IsActionable`, `ExtractMode`, `FirstAssignee`) and `internal/handler/handler.go`.

Optional extension (documented, not enabled by default): also subscribe to Note
events so a comment slash command such as `/coder` can trigger the same flow.
This adds a second code path and a second trust surface (free-text comments), so
the recommended demo keeps it to the label plus assignee path.

Label convention (mirrors the Summit bridge):

- `coder-task` selects the default AI-agent template (`claude-code`).
- `coder-task:<template-slug>` selects a named template version that exposes a
  `coder_ai_task` resource.

## (b) Receiver: a tiny in-cluster webhook handler

Recommendation for lowest demo risk: a small in-cluster Deployment in the `coder`
namespace, behind a ClusterIP Service. GitLab runs in-cluster on `gitlab-0`, so
delivery is a single in-cluster hop to
`http://agent-attribution-bridge.coder.svc.cluster.local:8080/webhook`. No public
exposure is required for the demo.

Why in-cluster Deployment, not CI-over-webhook:

- One observable, idempotent process holds exactly one scoped Coder credential.
  Blast radius and rotation are easy to reason about.
- It shares the `coder` namespace network and security posture with the Coder
  server, so the call to the Coder API stays in-namespace.
- No dependency on a runner picking up a pipeline, and no public ingress.

To avoid building and pushing a custom image in GovCloud (no pull-through cache),
the staged receiver is a pure standard-library Python program mounted from a
ConfigMap and run on the stock `python:3.12-slim` image mirrored into ECR. This
mirrors the envdocs pattern (a stock image serving ConfigMap content) and keeps
the deliverable fully reversible with no build step. The manifests live under
`deploy/coder/agent-attribution/`.

GitLab blocks webhooks to local or in-cluster addresses by default. Two safe
options, both documented in the deploy README:

1. Enable "Allow requests to the local network from webhooks" in GitLab admin
   settings and target the in-cluster Service URL. Lowest exposure.
2. Expose the receiver through ingress-nginx or the Istio gateway and target a
   public URL. Use this only if option 1 is not acceptable.

## (c) Attribution and auth model

The resulting workspace must be owned by the specific developer. Three candidate
mechanisms were evaluated against the verified 2.34 source.

### Option ii (recommended): service account creates the Task on behalf of the assignee

The Coder 2.34 Tasks API takes the owner as a path parameter. A single service
account token can create a Task whose owner is the assignee.

- SDK: `CreateTask` issues `POST /api/v2/tasks/{user}` with a
  `CreateTaskRequest{TemplateVersionID, Input, Name, ...}` body. See
  `reference/coder/codersdk/aitasks.go:24` (function) and
  `reference/coder/codersdk/aitasks.go:15` (request shape).
- Route: `reference/coder/coderd/coderd.go:1185` registers `/tasks`, and
  `coderd/coderd.go:1190` wraps `/{user}` with
  `httpmw.ExtractOrganizationMembersParam(...)` before `POST -> api.tasksCreate`
  (`coderd/coderd.go:1192`).
- Handler: `reference/coder/coderd/aitasks.go:48` (`tasksCreate`) resolves the
  owner from the `{user}` path param via the organization-member middleware
  (`coderd/aitasks.go:143` onward), then calls `createWorkspace(ctx, ...,
  apiKey.UserID, api, owner, createReq, ...)` at `coderd/aitasks.go:195`. The
  caller is `apiKey.UserID` (the service account); the workspace owner is the
  assignee.
- Authorization: `createWorkspace` checks
  `AuthorizeContext(ctx, policy.ActionCreate,
  rbac.ResourceWorkspace.InOrg(template.OrganizationID).WithOwner(owner.ID))`.
  See `reference/coder/coderd/workspaces.go:557` and `:574`. The service account
  must be allowed to create a workspace owned by another user in that org.
- The template version must expose a `coder_ai_task` resource, otherwise the
  handler returns 400. See `reference/coder/coderd/aitasks.go:97`. The worktree
  `coder-templates/claude-code` already declares `resource "coder_ai_task"`.

Result: one dedicated service account, no per-user token storage, and a workspace
that is genuinely owned by and attributed to the developer. The audit log records
initiator = service account and owner = developer, which is the correct and
honest representation of "the platform created this on the developer's behalf".

Important nuance verified from the Summit bridge: the older experimental chat
endpoint `POST /api/experimental/chats` hardcodes `owner_id` to the caller, which
forced the Summit bridge to mint a per-user token first (see
`reference/demo-aigov-rhsummit-2026/services/bridge/internal/coder/coder.go:233`
and `:248`). The stable Tasks API does not have that limitation, so option ii is
cleaner on 2.34 than the path the Summit demo had to take.

### Option i: per-user Coder API tokens

The service account mints a token for the assignee with
`POST /api/v2/users/{user}/keys/tokens` (`reference/coder/codersdk/apikey.go:63`),
then calls the Tasks API as that user. This also yields correct ownership and
makes the audit initiator the user. The cost is token lifecycle: the minting
right is itself powerful (an admin can mint a token for any user), and tokens
must be short-lived and never persisted. We keep this as a fallback for endpoints
that hardcode the caller as owner (such as the experimental chat path); for Tasks
it is unnecessary.

### Option iii: user impersonation

Coder 2.34 exposes no first-class session impersonation endpoint (no such call in
`codersdk/users.go`). The closest supported "act as user" mechanism is token
minting (option i). True impersonation is sensitive and is not used.

### Decision

Use option ii. Create a dedicated Coder service account `coder-task-bot` with a
least-privilege custom role in org `coder`
(`5de29a6d-8836-4643-a42b-2cb807c8e3e2`) granting workspace create, template read,
and organization member read. A coarser fallback is Organization Admin of org
`coder` only (never site Owner). The service-account token is stored in AWS
Secrets Manager and synced into the cluster by ESO, never committed to git.

## (d) Idempotency and duplicate avoidance

GitLab re-delivers webhooks and fires an `update` action on every issue edit, so
the receiver must be a no-op after the first successful spawn.

- Deterministic name: `Name = <repo>-issue-<iid>` where `<repo>` is the last
  segment of `path_with_namespace`, sanitized to `[a-z0-9-]` and truncated to the
  32-character Coder limit while preserving the `-issue-<iid>` suffix (the Summit
  `WorkspaceName` rule). Passing `Name` to the Tasks API makes both the task name
  and the workspace name deterministic (`coderd/aitasks.go:137` sets the workspace
  request `Name` from the task name).
- Existence check before create: look up the workspace by owner and name
  (`GET /api/v2/users/{user}/workspace/{name}`) or list the owner's tasks
  (`GET /api/v2/tasks?q=owner:...`). If it already exists, return a no-op 200.
- Action gate: only act on `{open, update, reopen}` with both the `coder-task`
  label and an assignee present.

## (e) Minimal, safe demo-day happy path

1. PM Morgan Pierce (`morgan.pm`) opens or reuses an issue in
   `coderdemo/coder-templates`, assigns it to a developer (for example
   `dana.dev`), and adds the `coder-task` label.
2. GitLab fires the Issue webhook to the in-cluster receiver.
3. The receiver verifies the `X-Gitlab-Token` shared secret, confirms the
   assignee maps to a Coder user, resolves the `claude-code` active template
   version (which exposes `coder_ai_task`), and creates the Task with
   `POST /api/v2/tasks/dana.dev`. The workspace is owned by `dana.dev`.
4. The receiver posts a comment back on the issue with the workspace and task
   links.
5. The audience sees the workspace and the agent under `dana.dev`, not a shared
   bot. With WS-22 Agent Firewall enabled, the agent egress is sandboxed and all
   model traffic flows through the in-cluster AI Gateway.

No-receiver fallback that is also safe to show: an operator runs
`scripts/setup-gitlab-agent-webhook.py --simulate --issue <iid>` which prints the
exact attributed Tasks API call, and with `--apply` performs that single
`POST /api/v2/tasks/<assignee>` live. This lets the booth demonstrate attribution
even before the receiver Deployment is rolled out.

## Security review surface (must be approved before going live)

1. Service-account token scope and blast radius. The `coder-task-bot` token can
   create workspaces owned by any user in org `coder`. It must be a dedicated
   service account with a least-privilege custom role (workspace create, template
   read, organization member read) bound to org `coder` only, a short token
   lifetime with rotation, storage in ASM and ESO sync, and never in git. Audit
   must show initiator = service account and owner = developer.
2. Webhook authenticity and input trust. GitLab sends the shared secret verbatim
   in `X-Gitlab-Token` (no HMAC), compared in constant time. Enforce TLS, scope
   the hook to the single project (`coderdemo/coder-templates`, id 2), trust only
   the assignee plus label as the trigger, never the actor, and rate-limit or
   dedupe to prevent a workspace flood. The issue body becomes the agent prompt,
   so treat it as untrusted input: run the agent under the Agent Firewall egress
   sandbox and the AI Gateway, and never expose the service-account token to the
   agent workspace.
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
| AI-agent template | `claude-code` (declares `coder_ai_task`) |
| Service account | `coder-task-bot` (custom role, org `coder` only) |
| Coder in-cluster API | `http://coder.coder.svc.cluster.local` |
| Coder public API | `https://dev.usgov.coderdemo.io` |
| GitLab API | `https://gitlab.usgov.coderdemo.io/api/v4` |
| Project | `coderdemo/coder-templates` (id 2), group `coderdemo` (id 13) |
| PM persona | Morgan Pierce, `morgan.pm` (realm `coder`) |
| Receiver | `agent-attribution-bridge` Deployment, ns `coder` |
| ASM secret | `usgov-coderdemo/agent-attribution/bridge` |
| ESO store | `ClusterSecretStore/aws-secretsmanager` |
