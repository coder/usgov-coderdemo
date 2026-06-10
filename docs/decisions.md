# Decisions and reference provenance

Append-only log of decisions and of code copied/adapted from `$REFERENCE_ROOT`
(the read-only reference clones). Each sub-agent also records its provenance in
its `docs/swarm/handoffs/WS-NN-handoff.md`; the orchestrator consolidates here.

## Reference clones (SHAs at the start of the Phase-2 wave)
| Repo | SHA |
|------|-----|
| reference/coder | 47a8c9572f |
| reference/demo-aigov-rhsummit-2026 | da48a48 |
| reference/observability | 863d498 |

## Phase-2 decisions

### Recreation: coderdemo/coder-templates on UBI9 (fold-in)
- source: reference/demo-aigov-rhsummit-2026@da48a48
- files: coder-templates/images/ubi9-base-workspace/{Dockerfile,uid_entrypoint.sh},
  coder-templates/images/ubi9-node-workspace/Dockerfile
- changes: reused the UBI9 base + node Dockerfiles for the GitLab CI build; built
  with Kaniko in the gitlab-runner namespace and pushed to the
  coderdemo/coder-templates GitLab Container Registry; rewrote 19 emdashes and a
  literal spaced double hyphen out of the reference Dockerfiles to satisfy
  make lint/emdash; the starship install step was changed to download-then-run.
- decision: NOT a strict air gap. GovCloud/CUI can egress to the internet
  (verified the gitlab-runner namespace reaches registry.access.redhat.com,
  EPEL, NodeSource, Rocky, starship.rs), so the UBI dnf/npm builds run directly.
  ECR mirroring is a performance/reliability choice, not a hard requirement.
- decision: the coder-templates project lives at coderdemo/coder-templates (group
  coderdemo, austen.platform Owner); the runner is a coderdemo GROUP runner. The
  prior root/coder-templates project was deleted.

### Realm name
- The live identity realm is "coder" (per docs/as-built/45-idp-sync-personas.md
  and the Phase-2 tasking), not "usgov" as written in the Phase-1
  docs/decisions-locked.md. The live system is authoritative.

## WS-2x provenance (consolidated from handoffs)
- WS-20: see docs/swarm/handoffs/WS-20-handoff.md
- WS-21: see docs/swarm/handoffs/WS-21-handoff.md
- WS-22: see docs/swarm/handoffs/WS-22-handoff.md
- WS-23: see docs/swarm/handoffs/WS-23-handoff.md. Decision: attribute Coder
  AI-agent work to the assigned GitLab developer via the stable 2.34 Tasks API
  service-account on-behalf-of model (`POST /api/v2/tasks/{user}` sets the
  workspace owner to the path-param user; verified in reference/coder
  coderd/aitasks.go and coderd/workspaces.go). Trigger is a GitLab Issue webhook
  gated by a `coder-task` label + assignee, landing on a small in-cluster
  receiver. STAGED only; requires the security review in the handoff before any
  apply.
- WS-24: see docs/swarm/handoffs/WS-24-handoff.md (upstream reference/observability@863d498)
- WS-25: see docs/swarm/handoffs/WS-25-handoff.md

## Follow-on wave decisions (2026-06-09)

All entries below are committed and pushed on branch ws-2x/phase2 (DRAFT PR #38),
applied live this session.

### 2026-06-09: Coder control plane v2.34.0 -> v2.34.1
- driver: Bedrock SigV4 proxy-header fix (backport #26053); v2.34.0 returned a
  SigV4 403 for the anthropic-bedrock provider.
- change: bumped the control plane to ghcr/coder/coder:v2.34.1 (live
  v2.34.1+2e8d80a, coderd 2/2, 0 restarts) and rebuilt the two external
  provisioner daemons (alpha/bravo) to v2.34.1.
- decision: supersedes the Phase-1 versions.lock pin of Coder 2.34.0; v2.34.1 is
  now authoritative for the demo.

### 2026-06-09: enable the anthropic-bedrock AI Gateway provider
- change: enabled anthropic-bedrock (GovCloud IRSA, us-gov-west-1, Sonnet 4.5)
  alongside the already-enabled anthropic (direct) and openai (direct).
- verification: Bedrock returns HTTP 200 for blocking, streaming, and
  anthropic-beta requests (previously blocked by the v2.34.0 SigV4 403).

### 2026-06-09: curate the Coder Agents model picker to 4 models
- change: curated the picker to exactly 4 enabled models, each at reasoning
  effort high with an estimated per-model cost (USD per 1M in/out): Opus 4.8
  (Anthropic Direct) 15/75; Sonnet 4.6 (Anthropic Direct, DEFAULT) 3/15; GPT 5.5
  (OpenAI Direct) 1.25/10; Sonnet 4.5 (GovCloud Bedrock) 3/15.
- change: extended scripts/reconcile-ai-providers.py to manage model_config
  (cost + effort).

### 2026-06-09: register the datastore MCP, remove the gateway-injected MCP
- change: registered a read-only datastore MCP server (deploy/datastore-mcp) via
  the supported path POST /api/experimental/mcp/servers (slug datastore,
  auth_type none, default_on, enabled).
- decision: removed the deprecated gateway-injected MCP and the datastore
  External Auth in favor of the supported MCP servers path.

### 2026-06-09: drop the GitLab MCP (Linear CODAGT-570)
- finding: GitLab CE 19.0.1 official /api/v4/mcp works standalone, but Coder
  v2.34.1 cannot connect: GitLab returns 204 on notifications/initialized while
  mark3labs/mcp-go accepts only 200/202, and the RFC 9728 resource-array breaks
  oauth2 auto-DCR.
- decision: drop the GitLab MCP; not worth a 204-to-202 shim.

### 2026-06-09: configure Coder Agents chat spend-limits
- change: configured live spend-limits: global default $500/month (master ON),
  group alpha/developers $100, group bravo "Everyone" $250 (org-wide), user
  patrickplatform $50. Precedence is user > MIN(group) > default; enforcement is
  a hard HTTP 409.
- artifacts: control script scripts/demo-chat-spend-limits.py; doc
  docs/plans/chat-spend-limits.md.
- decision: the AI Bridge /ai/budget path is non-functional scaffolding and is
  not used.

### 2026-06-09: disable built-in Coder password auth (Keycloak-only login)
- change: added `CODER_DISABLE_PASSWORD_AUTH=true` to `deploy/coder/values.yaml`
  (helm release `coder` rev 12). The login UI now shows only "Sign in with
  Keycloak"; `GET /api/v2/users/authmethods` reports `password.enabled=false`
  and `oidc.enabled=true`, and `POST /api/v2/users/login` returns HTTP 403
  "Password authentication is disabled" for all users including owners (v2.34.1
  `coderd/userauth.go` blocks with no owner exception).
- decision: the former bootstrap `admin` owner now signs in via Keycloak SSO;
  automation uses a long-lived Coder API token (token auth is unaffected by the
  flag). Break-glass if Keycloak/OIDC is unavailable:
  exec into the `coder` pod and run `coder server create-admin-user`, or set
  `CODER_DISABLE_PASSWORD_AUTH="false"` and `helm upgrade`.

### 2026-06-10: add Claude Fable 5 and 1M context to the Coder Agents picker
- change: added Fable 5 (Anthropic Direct, `claude-fable-5`, $10/M in, $50/M
  out, effort high) to the curated picker, taking it from four to five enabled
  models.
- change: bumped the three Anthropic-direct models (Sonnet 4.6, Opus 4.8, Fable
  5) from a 200,000-token to a 1,000,000-token context window, verified against
  the Anthropic Models API `max_input_tokens`.
- decision: GPT 5.5 stays at 400,000 and the GovCloud Bedrock Sonnet 4.5 stays
  at 200,000, because a 1M window is not confirmed on GovCloud Bedrock.

### 2026-06-10: bump the datastore MCP image to 0.1.1 (security deps)
- change: rebuilt and redeployed the datastore MCP server from 0.1.0 to 0.1.1
  (digest `sha256:ad955f8361716785a30e4f516d4818cc5ea3c22130e3a8fe52987e433a78faf1`),
  folding three Dependabot security bumps: github.com/jackc/pgx/v5 5.7.6 to
  5.9.2 (SQL-injection fix GHSA-j88v-2chj-qfwx), github.com/buger/jsonparser
  1.1.1 to 1.1.2, and golang.org/x/crypto 0.37.0 to 0.45.0. Pushed to ECR
  `usgov/datastore-mcp:0.1.1`, manifest tag bumped, rolled out live in namespace
  `coder-demo-mcp`; verified `list_tables`/`describe_table`/`query`.
- decision: the server remains read-only with `auth_type none`; adding auth
  (recommended `user_oidc`/Keycloak) is tracked in issue #45.

### 2026-06-10: redact the AWS account ID from docs/
- change: replaced every occurrence of the live AWS account ID under `docs/`
  with the placeholder `<AWS_ACCOUNT_ID>` (prose, ECR image URIs, and IAM role
  ARNs).
- decision: docs-only redaction; the real account ID stays in `deploy/`,
  `terraform/`, `coder-templates/`, `scripts/`, and `STATUS.md`, where it is
  functionally required.
