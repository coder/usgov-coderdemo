# 65. Coder Agents control plane (as-built)

Coder Agents is the control-plane agentic chat (the in-dashboard chat at
`/chat`, distinct from the in-workspace Claude Code path in
`70-workspace-templates.md`). This document records what is configured for the
demo on **v2.34.1**: the curated model picker, the read-only datastore MCP
server, and the chat spend-limit tiers.

## Two AI paths, one provider store

The demo exposes two separate AI surfaces that share the same `ai_providers`
table (`60-ai-gateway.md`):

1. **In-workspace AI Gateway (aibridge).** Claude Code in a workspace pod calls
   `POST /api/v2/aibridge/<provider-name>/v1/...` with the owner session token.
   Covered in `60-ai-gateway.md` and `70-workspace-templates.md`.
2. **Coder Agents control-plane chat (this document).** The dashboard chat reads
   its model list from `GET /api/experimental/chats/models`, which is backed by
   the same enabled `ai_providers` rows plus the `chat_model_configs` model
   presets. The legacy separate chat-provider API now returns HTTP 410.

Provider enablement and keys are documented in `60-ai-gateway.md`. This file
covers the Coder Agents specifics layered on top.

## Verification method

Read-only. Session token via `POST /api/v2/users/login`, then `GET` against
`https://dev.usgov.coderdemo.io`. Verified live 2026-06-09:
`GET /api/v2/buildinfo` reports `v2.34.1+2e8d80a`; `GET /api/v2/ai/providers`
returns three enabled providers (`anthropic`, `openai`, `anthropic-bedrock`);
`GET /api/experimental/mcp/servers` returns the `datastore` server enabled. The
desired-state source of truth is `deploy/coder/ai-providers.yaml` (providers and
model presets) and `scripts/demo-chat-spend-limits.py` (spend limits).

## Curated model picker (4 enabled models)

The picker is curated to exactly four enabled models, each with reasoning effort
`high` and an estimated per-model cost (USD per 1M tokens, input / output). The
costs are representative public list prices for the matching tier; these are
demo model names and are not billed. They feed the spend-limit accounting below
(`chat_messages.total_cost_micros` is computed from `chat_model_configs`
pricing). Source of truth: `deploy/coder/ai-providers.yaml`, reconciled via
`scripts/reconcile-ai-providers.py`.

| Picker name | Provider | Model id | Effort | In / Out |
|---|---|---|---|---|
| Opus 4.8 (Anthropic Direct) | `anthropic` (direct) | `claude-opus-4-8` | high | 15 / 75 |
| Sonnet 4.6 (Anthropic Direct) **default** | `anthropic` (direct) | `claude-sonnet-4-6` | high | 3 / 15 |
| GPT 5.5 (OpenAI Direct) | `openai` (direct) | `gpt-5.5` | high | 1.25 / 10 |
| Sonnet 4.5 (GovCloud Bedrock) | `anthropic-bedrock` (IRSA) | `us-gov.anthropic.claude-sonnet-4-5-20250929-v1:0` | high | 3 / 15 |

All other model presets in `ai-providers.yaml` are disabled, so re-enabling any
of them is a one-line flip. Sonnet 4.6 (Anthropic Direct) is the demo default.
Provider rows carry no model list (only the Bedrock provider's settings carry
`model` + `small_fast_model`); the picker is populated from `chat_model_configs`
and the reconciler now sends and diffs `model_config` (cost plus
`provider_options` reasoning effort).

## Datastore MCP server (supported path)

A read-only MCP server registered with Coder Agents demonstrates federated data
access from the control-plane chat.

- **Registration (supported path).** `POST /api/experimental/mcp/servers` with
  slug `datastore`, `auth_type none`, `transport streamable_http`,
  `availability default_on`, `enabled true`. Verified live via
  `GET /api/experimental/mcp/servers` (display name "Demo Data Store", url
  `http://datastore-mcp.coder-demo-mcp.svc.cluster.local:8000/mcp`).
- **Server.** A small Go Streamable-HTTP MCP server (`deploy/datastore-mcp`,
  `mark3labs/mcp-go`) over an ephemeral, synthetic, UNCLASSIFIED demo Postgres
  in namespace `coder-demo-mcp`. It connects as a least-privilege role, permits
  a single `SELECT`/`WITH` per `query` in a read-only transaction, and exposes
  `list_tables`, `describe_table`, and `query`. Image built into private ECR
  (`usgov/datastore-mcp`), not an upstream mirror.
- **Deprecated path removed.** The earlier gateway-injected MCP mechanism
  (`CODER_AI_GATEWAY_INJECT_CODER_MCP_TOOLS` plus a `datastore` External Auth
  provider) was removed from `deploy/coder/values.yaml`. The supported Coder
  Agents MCP path is the only one in use.

### GitLab MCP evaluated and dropped (CODAGT-570)

A GitLab MCP server was investigated (GitLab CE 19.0.1 ships an official
`/api/v4/mcp` that works standalone) but **dropped** for the demo due to a
Coder-to-GitLab interop bug: GitLab returns HTTP 204 on
`notifications/initialized` while the `mark3labs/mcp-go` client accepts only
200/202, and its RFC 9728 resource-array response breaks oauth2 auto-DCR. No
GitLab MCP is deployed. Tracked in Linear CODAGT-570.

## Chat spend limits (tiered caps, HTTP 409 enforcement)

Coder Agents chats meter spend per message into
`chat_messages.total_cost_micros` (computed from the per-model
`chat_model_configs` pricing above). A deployment-level usage-limit config plus
per-group and per-user overrides cap spend per UTC calendar period. This is the
enforcing system; the separate AI Bridge `/ai/budget` system is non-functional
scaffolding in v2.34.1 and is not used. Admin-only endpoints under
`/api/experimental/chats/usage-limits` (note the plural). Control script:
`scripts/demo-chat-spend-limits.py`; design doc: `docs/plans/chat-spend-limits.md`.

Applied tiers (period `month`, master switch ON):

| Scope | Target | Cap / month |
|---|---|---|
| Global default | deployment-wide | $500 |
| Group override | `alpha` / `developers` | $100 |
| Group override | `bravo` "Everyone" (org-wide) | $250 |
| User override | `patrickplatform` | $50 |

- **Precedence (tightest wins):** user override > MIN(group overrides) > global
  default. Group membership is scanned across all organizations, so a Coder
  "Everyone" group override behaves org-wide.
- **Master switch.** The global config is enabled only when
  `spend_limit_micros` is a positive integer; with it disabled the resolver
  returns no limit for everyone and overrides are ignored. The generous global
  default keeps the system ON so the tighter group/user caps take effect.
- **Enforcement.** When `current_spend >= effective_limit`, a new chat message
  is hard-blocked with **HTTP 409** (`ChatUsageLimitExceededResponse`).
- **Accounting caveat.** `current_spend` is the sum over the active UTC period,
  scoped to the user. Messages sent before pricing was configured carry `NULL`
  cost and are excluded, so applying limits does not retroactively bill historic
  chats.

## Notes

- Provider keys and the IRSA Bedrock credential chain are in `60-ai-gateway.md`;
  the Anthropic-direct provider still carries a placeholder key while Bedrock
  (IRSA, no key) is enabled and verified.
- The model picker, MCP registration, and spend limits are all DB-managed and
  applied imperatively through the supported APIs; see the ledger in
  `80-iac-vs-imperative.md`.
