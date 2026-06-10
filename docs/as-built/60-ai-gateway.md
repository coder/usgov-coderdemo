# 60. AI Gateway / AI Bridge (as-built)

How the Coder AI Gateway (formerly "AI Bridge") is wired for the GovCloud demo:
three providers, routing by provider name, the Bedrock IRSA credential chain, and
the verified end-to-end routing proof. The product is the AI Gateway; the API
paths still use `/api/v2/aibridge/...` (`deploy/coder/README.md:80-82`).

Two surfaces share these providers: the **in-workspace** AI Gateway path that
Claude Code calls (`POST /api/v2/aibridge/<name>/v1/...`, this document and
`70-workspace-templates.md`), and the **Coder Agents control-plane chat** model
picker that reads the same enabled `ai_providers` rows
(`65-coder-agents.md`).

## Verification method

Read-only. Session token obtained via `POST /api/v2/users/login`, then `GET`
requests against `https://dev.usgov.coderdemo.io` with the
`Coder-Session-Token` header. AWS facts came from read-only `aws iam get-role`
and `aws iam get-role-policy`. The routing probe is a `POST` to the gateway, so
it was not re-executed here (read-only, GET-only); the 502 proof below is cited
from `STATUS.md` and the facts sheet, and the live providers/config it depends
on were independently re-verified.

Re-verified live this session (read-only): `GET /api/v2/buildinfo` reports
`v2.34.1+2e8d80a`; the AI Governance dashboard ConfigMap
`coder-dashboard-ai-governance` (ns `monitoring`) holds 42 panel entries (four
row headers plus 38 data panels) and references datasource uids `prometheus`,
`loki`, and `aibridge-postgres`; the `aibridge-postgres-datasource` ConfigMap is
present in ns `monitoring`; and the seeded provider env vars in
`deploy/coder/values.yaml` are unchanged at the cited line ranges.

## Enabled by default in v2.34

AI Gateway is enabled by default in v2.34 and is set explicitly in Helm
(`CODER_AI_GATEWAY_ENABLED=true`, `deploy/coder/values.yaml:159-166`). It
requires the AI Governance Add-On entitlement.

Verified live:

- `GET /api/v2/deployment/config` reports `ai.bridge.enabled=true` and
  `chat.ai_gateway_routing_enabled=true`.
- `GET /api/v2/entitlements` reports `aibridge` entitled and enabled, and
  `ai_governance_user_limit` entitled and enabled (limit 30, actual 1).

## Providers are database-managed (seed-once)

Since v2.34, AI Gateway providers live in the database and are managed at
`https://dev.usgov.coderdemo.io/ai/settings` or the AI Providers API. The
`CODER_AI_GATEWAY_PROVIDER_*` env vars are deprecated and only seed the DB on
first startup; afterward the database is authoritative. Changing a seeded env
var later makes `coderd` fail to start (the drift guard). Source:
`deploy/coder/README.md:123-140`, `deploy/coder/values.yaml:13-16, 159-164`.
See `30-coder-control-plane.md` for the Helm-side seed/drift detail.

Verified live: `GET /api/v2/ai/providers` returns three providers (below): the
env-seeded `anthropic` and `anthropic-bedrock`, plus `openai`, which was added
through the reconciler (`scripts/reconcile-ai-providers.py`) against the API and
is not env-seeded. Source of truth for the desired provider and model state is
`deploy/coder/ai-providers.yaml`.

### Provider `anthropic` (direct, primary)

```json
{
  "type": "anthropic",
  "name": "anthropic",
  "display_name": "Anthropic (direct)",
  "enabled": true,
  "base_url": "https://api.anthropic.com",
  "api_keys": [{ "masked": "sk-a...ings", ... }],
  "settings": null
}
```

Direct provider; egress to `api.anthropic.com` leaves the VPC via the NAT
gateway (`deploy/coder/values.yaml:168-186`, `deploy/CONVENTIONS.md:76-78`).
The key is seeded from Secret `coder-ai` key `ANTHROPIC_API_KEY` on first boot
and is then managed in the DB.

The live masked key `sk-a...ings` is consistent with the placeholder
`sk-ant-REPLACE_ME_set_real_key_via_ai_settings` (it ends in `ings`). No real
Anthropic key exists anywhere in this environment.

Remaining user action: sign in as the owner, open Admin settings > AI >
Providers (`/ai/settings`), edit the provider named `anthropic`, and paste the
real `sk-ant-...` key. Do this in the UI, not by editing the `coder-ai` k8s
secret, because the provider config now lives in the database. Source:
`STATUS.md:61-74`, facts sheet "Remaining action".

### Provider `openai` (direct, secondary)

```json
{
  "type": "openai",
  "name": "openai",
  "display_name": "OpenAI (direct)",
  "enabled": true,
  "base_url": "https://api.openai.com/v1/",
  "api_keys": [{ "masked": "..." }],
  "settings": null
}
```

Direct OpenAI provider added through the reconciler (not env-seeded); the
aibridge route is `POST /api/v2/aibridge/openai/v1/chat/completions` and egress
to `api.openai.com` leaves the VPC via the NAT gateway. The key is referenced by
env var name in `deploy/coder/ai-providers.yaml` (`key_from_env: OPENAI_KEY`),
never stored in the file. Verified live via `GET /api/v2/ai/providers`.

### Provider `anthropic-bedrock` (Bedrock via IRSA, enabled and verified)

```json
{
  "type": "bedrock",
  "name": "anthropic-bedrock",
  "display_name": "Anthropic on Bedrock (GovCloud, IRSA)",
  "enabled": true,
  "base_url": "",
  "api_keys": [],
  "settings": {
    "_type": "bedrock",
    "model": "us-gov.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "region": "us-gov-west-1",
    "small_fast_model": "amazon.nova-pro-v1:0"
  }
}
```

In-boundary provider with no static key (`api_keys` is empty); it authenticates
through IRSA. The primary model is the GovCloud Claude Sonnet 4.5 inference
profile; the small fast model (the Haiku-class background model Claude Code
uses) is `amazon.nova-pro-v1:0`. Source: `deploy/coder/values.yaml:188-205`,
`deploy/coder/ai-providers.yaml`, verified live via `GET /api/v2/ai/providers`.

**Now enabled and verified on v2.34.1.** Claude Sonnet 4.5 is ACTIVE in
`us-gov-west-1` (the `us-gov.` cross-region inference profile plus the
underlying foundation-model), and the `usgov-coderdemo-coder-bedrock` IRSA role
allowlists both. On v2.34.0 the provider was blocked by a SigV4 `403` ("signature
does not match"): the AI Gateway egress signed requests that still carried
inbound Istio/Envoy proxy headers (`x-forwarded-for`, `x-envoy-*`,
`x-request-id`), so the canonical `SignedHeaders` never matched what Bedrock
recomputed. The fix (coder/coder#26019, strip proxy headers before signing)
shipped in v2.34.1 via backport #26053. Verified live (2026-06-08):
`POST /api/v2/aibridge/anthropic-bedrock/v1/messages` returns HTTP 200 for the
blocking, streaming (SSE), and `anthropic-beta` header paths Claude Code uses
(the earlier `coder/aibridge#221` beta-header rejection no longer reproduces).

## Routing path and why the provider must be named `anthropic`

The gateway routes by provider **name**:

```
POST /api/v2/aibridge/<provider-NAME>/v1/messages
```

The provider must be named `anthropic` because the claude-code workspace module
(4.7.3) hardcodes `ANTHROPIC_BASE_URL=<access_url>/api/v2/aibridge/anthropic`.
With `CODER_ACCESS_URL=https://dev.usgov.coderdemo.io` that resolves to
`https://dev.usgov.coderdemo.io/api/v2/aibridge/anthropic`. A name like
`anthropic-direct` would make that route 404, so Claude Code could not reach the
provider. Source: `deploy/coder/values.yaml:171-179`,
`deploy/coder/README.md:119-121`, `coder-templates/claude-code/main.tf:22-26`.

This is why the Anthropic-direct provider is named exactly `anthropic` and the
Bedrock provider is named `anthropic-bedrock`. To route Claude Code to Bedrock,
you either rename the Bedrock provider to `anthropic` or set the workspace model
to a Bedrock id (`STATUS.md:76-79`).

## Coder Agents control-plane model picker

The same `ai_providers` rows also back the Coder Agents control-plane chat. Its
model picker (`GET /api/experimental/chats/models`) is curated to exactly five
enabled models, each with reasoning effort `high` and an estimated per-model
cost: Sonnet 4.6 (Anthropic Direct, the default), Opus 4.8 (Anthropic Direct),
Fable 5 (Anthropic Direct), GPT 5.5 (OpenAI Direct), and Sonnet 4.5 (GovCloud
Bedrock). The three Anthropic-direct models carry a 1,000,000-token context
window; GPT 5.5 is 400,000 and the GovCloud Bedrock Sonnet 4.5 is 200,000.
Unlike the
in-workspace aibridge path (which Claude Code drives with a fixed
`ANTHROPIC_BASE_URL`), the picker selects among providers and models per chat.
The model presets, costs, and the spend-limit accounting they feed are detailed
in `65-coder-agents.md`; source of truth `deploy/coder/ai-providers.yaml`.

## End-to-end request flow

A request from a workspace's Claude Code to the upstream model:

1. Claude Code in the workspace pod reads `ANTHROPIC_BASE_URL`
   (`<access_url>/api/v2/aibridge/anthropic`) and a bearer token. The token is
   the workspace owner's Coder session token (`CLAUDE_API_KEY` set by the
   module, plus `ANTHROPIC_AUTH_TOKEN` exported by the template), not a raw
   Anthropic key. Source: `coder-templates/claude-code/main.tf:22-28, 269-282`.
2. The request hits `POST /api/v2/aibridge/anthropic/v1/messages` on the Coder
   server.
3. The AI Gateway authenticates the session token, applies governance and
   audit, then looks up the provider whose name matches the path segment
   (`anthropic`).
4. The gateway forwards to that provider's upstream:
   - `anthropic` (direct): `https://api.anthropic.com`, egress via the NAT
     gateway.
   - `anthropic-bedrock`: AWS Bedrock in `us-gov-west-1` using IRSA credentials,
     in-region only.
5. The upstream response streams back through the gateway to Claude Code.

No Anthropic key is stored in the workspace; the session token is the only
credential and it is scoped to the workspace owner. Source:
`coder-templates/claude-code/README.md:31-50`.

## Bedrock IRSA credential chain (verified live)

The Bedrock provider attaches no static key, so the AWS SDK default credential
chain resolves the IRSA web-identity token from the annotated service account.
The chain, verified read-only:

1. **ServiceAccount annotation.** SA `coder/coder` is annotated
   `eks.amazonaws.com/role-arn = arn:aws-us-gov:iam::<AWS_ACCOUNT_ID>:role/usgov-coderdemo-coder-bedrock`.
   Verified: `kubectl -n coder get sa coder -o jsonpath`. Declared at
   `deploy/coder/values.yaml:32-37`.
2. **STS AssumeRoleWithWebIdentity.** The role trust policy allows
   `sts:AssumeRoleWithWebIdentity` from the cluster OIDC provider
   (`oidc-provider/oidc.eks.us-gov-west-1.amazonaws.com/id/E9DB9E591C95ECB91F44EDCF38F146F2`),
   conditioned on `aud = sts.amazonaws.com` and
   `sub = system:serviceaccount:coder:coder`. The SDK uses the GovCloud regional
   STS endpoint because `AWS_REGION=us-gov-west-1` and
   `AWS_STS_REGIONAL_ENDPOINTS=regional` are set
   (`deploy/coder/values.yaml:207-215`). Verified:
   `aws iam get-role --role-name usgov-coderdemo-coder-bedrock`.
3. **bedrock:InvokeModel.** The inline policy `bedrock-invoke` grants
   `bedrock:InvokeModel` and `bedrock:InvokeModelWithResponseStream` on an
   allowlisted resource set:
   - `foundation-model/anthropic.claude-sonnet-4-5-20250929-v1:0`
     (us-gov-west-1 and us-gov-east-1)
   - `foundation-model/amazon.nova-pro-v1:0` (us-gov-west-1)
   - `inference-profile/us-gov.anthropic.claude-sonnet-4-5-20250929-v1:0`
     (us-gov-west-1, account `<AWS_ACCOUNT_ID>`)

   Verified: `aws iam get-role-policy --role-name usgov-coderdemo-coder-bedrock
   --policy-name bedrock-invoke`. This matches the expectation in the facts
   sheet and `deploy/coder/README.md:114-118`.

## Verified 502 routing proof and what 200 requires

Per `STATUS.md:56-57` and the facts sheet, the routing path was verified end to
end: `POST /api/v2/aibridge/anthropic/v1/messages` reaches `api.anthropic.com`
and returns **502 "all configured keys failed authentication"** with the
placeholder key. The 502 (an upstream auth rejection, not a 404) proves the full
path works: client to gateway to upstream Anthropic. The route only resolves
because the provider is named `anthropic`.

This routing probe is a `POST`, so it was not re-run under this read-only task.
The supporting state was independently re-verified live: the `anthropic`
provider exists, is enabled, points at `https://api.anthropic.com`, and still
carries the placeholder key (masked `sk-a...ings`).

A `200` requires a working upstream credential:

- Anthropic-direct: paste a real `sk-ant-...` key into the `anthropic` provider
  at `/ai/settings`, then re-run the routing check. Source: `STATUS.md:63-74`.
- Bedrock (in-boundary alternative): the `anthropic-bedrock` provider is enabled
  and verified on v2.34.1 (HTTP 200 via IRSA, no key). To route Claude Code to
  it, rename the provider to `anthropic` or set the workspace model to its
  Bedrock id. Source: `STATUS.md:76-79`, `deploy/coder/ai-providers.yaml`.

## AI Governance dashboard

The AI Gateway is surfaced in Grafana by the AI Governance dashboard (uid
`ai-governance`, ConfigMap `coder-dashboard-ai-governance` in ns `monitoring`).
This session it was redesigned (usgov-dashboard PR #32) from the earlier two-row
view into 42 panel entries across four collapsible rows: AI Gateway Overview,
Usage & Cost, Intercepts & Sessions, and Agent Firewall (four row headers plus 38
data panels). Source: `deploy/observability/dashboards-ai-governance.yaml` and
`deploy/observability/AI_GOVERNANCE_DASHBOARD.md`. The broader Grafana stack is in
`55-observability.md`.

### Data sources

| Source | uid | Powers |
|---|---|---|
| Prometheus | `prometheus` | Provider health and reload status (`coder_aibridged_*`); Agent Firewall forwarded-batch counters (`agent_boundary_log_proxy_batches_forwarded_total`). |
| Loki | `loki` | AI Gateway log stream (ns `coder`) and Agent Firewall log stream (ns `coder-workspaces`), plus their event-rate panels. |
| AI Gateway DB (Postgres) | `aibridge-postgres` | Token, cost, interception, session, prompt, and tool drill-downs from the Coder database that Prometheus does not expose. |

The Postgres datasource is new in this redesign. The deployed Coder (v2.34.1)
exposes only provider-health gauges for the AI Gateway to Prometheus, and the
latest `coder/coder` adds no token, request, or cost metrics either, so the
per-interception, per-session, token, and cost data lives only in the Coder
database (`aibridge_interceptions`, `aibridge_token_usages`,
`aibridge_user_prompts`, `aibridge_tool_usages`, `boundary_sessions`,
`ai_model_prices`). Prometheus and Loki are used wherever they suffice; Postgres
backs only the drill-downs that have no metric or log equivalent.

### Cost derivation

Cost is derived from `aibridge_token_usages` joined to `ai_model_prices`. The
price table stores per-million-token prices in micro-units (1 dollar = 1,000,000
units) with separate input, output, cache-read, and cache-write columns, so the
cost panels compute dollars as:

```
cost_usd = (input_tokens*input_price + output_tokens*output_price
            + cache_read_input_tokens*cache_read_price
            + cache_write_input_tokens*cache_write_price) / 1e12
```

The live `ai_model_prices` table is populated (71 rows, including the
`claude-sonnet-4-5` family used in the demo), so cost is fully derivable once
token usage is recorded.

### Read-only Postgres datasource (credential handling)

The datasource (`deploy/observability/datasource-aibridge-postgres.yaml`, name
"AI Gateway DB", uid `aibridge-postgres`) authenticates as `grafana_ro`, a
least-privilege Postgres role: `LOGIN`, no superuser, no `CREATEROLE`, with
`SELECT` on only the AI Gateway and Agent Firewall tables plus `users` and
`workspace_agents` for joins (`deploy/observability/sql/aibridge-grafana-ro.sql`).
Because the Coder application role lacks `CREATEROLE`, the role is created as the
RDS master user. The password lives only in the Kubernetes Secret
`aigov-grafana-db` (key `AIGOV_DB_PASSWORD`), synced from AWS Secrets Manager via
ESO; Grafana injects it through `grafana.envValueFrom` and expands
`${AIGOV_DB_PASSWORD}` in the datasource ConfigMap. No password is in git. The
datasource is `editable: false`, `isDefault: false`, and connects with
`sslmode: require`.

### Display-only rename

The dashboards rename terminology in display text only: "AI Bridge"/"aibridge" ->
"AI Gateway", and "Boundary" -> "Agent Firewall". The underlying Prometheus series
names (`coder_aibridged_*`, `agent_boundary_*`), the LogQL literals matched in the
log streams (`aibridged`, `boundary`), the API paths (`/api/v2/aibridge/...`), and
the database table names (`aibridge_*`, `boundary_*`) are unchanged.

### Sparse-data caveat

The demo Anthropic direct key is a placeholder (see above), so direct-path calls
fail before any tokens are metered. The `anthropic-bedrock` provider does respond
(HTTP 200), so Bedrock calls record some token and cost data, but volume stays
low because no sustained AI traffic is generated in the demo. The token and cost
stats, Tokens Over Time, Estimated Cost Over Time, Token Usage Detail, Recent
User Prompts, Recent Tool Calls, and the Firewall Sessions panels therefore read
`0` or near-empty by design; this is expected, not an error. Panels that already
have data include provider health and inventory, total interceptions, active
sessions, unique users, interceptions by provider / model / user, Recent
Interceptions, Sessions, and the Agent Firewall log stream.

## Known issues

- **Bedrock model access (resolved on v2.34.1).** `InvokeModel` on
  `us-gov.anthropic.claude-sonnet-4-5-...` is ACTIVE in `us-gov-west-1` and the
  provider is enabled and verified (HTTP 200). The earlier v2.34.0 SigV4 `403`
  (proxy headers carried into signing) was fixed by coder/coder#26019, shipped
  via backport #26053. Source: `deploy/coder/ai-providers.yaml`, `STATUS.md`.
- **Claude Code Bedrock beta header (no longer reproduces on v2.34.1).** Known
  issue `coder/aibridge#221`: Claude Code sends an `anthropic-beta` flag that
  GovCloud Bedrock historically rejected. On v2.34.1 the blocking, streaming,
  and `anthropic-beta` paths all return HTTP 200 through the gateway. Source:
  `deploy/coder/ai-providers.yaml`, `deploy/coder/README.md:170-174`.
