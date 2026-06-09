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
