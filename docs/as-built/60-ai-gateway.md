# 60. AI Gateway / AI Bridge (as-built)

How the Coder AI Gateway (formerly "AI Bridge") is wired for the GovCloud demo:
two providers, routing by provider name, the Bedrock IRSA credential chain, and
the verified end-to-end routing proof. The product is the AI Gateway; the API
paths still use `/api/v2/aibridge/...` (`deploy/coder/README.md:80-82`).

## Verification method

Read-only. Session token obtained via `POST /api/v2/users/login`, then `GET`
requests against `https://dev.usgov.coderdemo.io` with the
`Coder-Session-Token` header. AWS facts came from read-only `aws iam get-role`
and `aws iam get-role-policy`. The routing probe is a `POST` to the gateway, so
it was not re-executed here (read-only, GET-only); the 502 proof below is cited
from `STATUS.md` and the facts sheet, and the live providers/config it depends
on were independently re-verified.

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

Verified live: `GET /api/v2/ai/providers` returns two providers (below). These
match the seeded `ai.bridge.providers` array in `deployment/config`.

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

### Provider `anthropic-bedrock` (Bedrock via IRSA, secondary)

```json
{
  "type": "bedrock",
  "name": "anthropic-bedrock",
  "display_name": "anthropic-bedrock",
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
verified live via `GET /api/v2/ai/providers`.

Claude Sonnet 4.5 access on Bedrock is still gated; it needs an Anthropic
agreement via the account paired with GovCloud. `amazon.nova-pro-v1:0` is the
proven fallback that invokes in GovCloud today. Source: `STATUS.md:29-31`,
`deploy/coder/README.md:165-169`.

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
   `eks.amazonaws.com/role-arn = arn:aws-us-gov:iam::430737322961:role/usgov-coderdemo-coder-bedrock`.
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
     (us-gov-west-1, account `430737322961`)

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
- Bedrock (in-boundary alternative): enable Claude Sonnet 4.5 model access in
  the GovCloud console, then route Claude Code at the `anthropic-bedrock`
  provider (rename it to `anthropic` or set the workspace model). Bedrock access
  is still gated; Nova Pro is the proven fallback. Source: `STATUS.md:76-79`.

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

The Postgres datasource is new in this redesign. The deployed Coder (v2.34.0)
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

The demo Anthropic key is a placeholder (see above), so AI calls fail before any
tokens are metered and no real AI traffic is recorded. The token and cost stats,
Tokens Over Time, Estimated Cost Over Time, Token Usage Detail, Recent User
Prompts, Recent Tool Calls, and the Firewall Sessions panels therefore read `0`
or stay empty by design; this is expected, not an error. Panels that already have
data include provider health and inventory, total interceptions, active sessions,
unique users, interceptions by provider / model / user, Recent Interceptions,
Sessions, and the Agent Firewall log stream.

## Known issues

- **Bedrock model access gated.** `InvokeModel` on
  `us-gov.anthropic.claude-sonnet-4-5-...` returns AccessDenied until model
  access is enabled; the provider is wired but may be disabled at demo time.
  Source: `deploy/coder/README.md:165-169`, `STATUS.md:29-31`.
- **Claude Code Bedrock beta header in GovCloud.** Known issue
  `coder/aibridge#221`: Claude Code sends an `anthropic-beta` flag that GovCloud
  Bedrock rejects (`invalid beta flag`), which can break the
  Bedrock-through-gateway path for Claude Code specifically. Anthropic-direct is
  unaffected. Source: `deploy/coder/README.md:170-174`.
