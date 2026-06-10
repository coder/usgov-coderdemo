# AI Gateway

The Coder AI Gateway (formerly "AI Bridge") is the governed egress for all model
traffic. The product is the AI Gateway; the API paths still use
`/api/v2/aibridge/...`. It requires the AI Governance Add-On entitlement and is
enabled by default in v2.34.

Source of truth: `docs/as-built/60-ai-gateway.md`, `deploy/coder/values.yaml`.

## Two providers, routed by name

The gateway routes by provider **name**:

```text
POST /api/v2/aibridge/<provider-NAME>/v1/messages
```

### `anthropic` (direct, primary)

```yaml
- CODER_AI_GATEWAY_PROVIDER_0_TYPE = "anthropic"
- CODER_AI_GATEWAY_PROVIDER_0_NAME = "anthropic"
- CODER_AI_GATEWAY_PROVIDER_0_BASE_URL = "https://api.anthropic.com"
- CODER_AI_GATEWAY_PROVIDER_0_KEY  # from Secret coder-ai key ANTHROPIC_API_KEY
```

Direct provider; egress to `api.anthropic.com` leaves the VPC via the single NAT
gateway. The provider must be named exactly `anthropic` because the
`claude-code` workspace module hardcodes
`ANTHROPIC_BASE_URL=<access_url>/api/v2/aibridge/anthropic`. A different name
would make that route 404.

### `anthropic-bedrock` (Bedrock via IRSA, secondary)

```yaml
- CODER_AI_GATEWAY_PROVIDER_1_TYPE = "bedrock"
- CODER_AI_GATEWAY_PROVIDER_1_NAME = "anthropic-bedrock"
- CODER_AI_GATEWAY_PROVIDER_1_BEDROCK_REGION = "us-gov-west-1"
- CODER_AI_GATEWAY_PROVIDER_1_BEDROCK_MODEL = "us-gov.anthropic.claude-sonnet-4-5-20250929-v1:0"
- CODER_AI_GATEWAY_PROVIDER_1_BEDROCK_SMALL_FAST_MODEL = "amazon.nova-pro-v1:0"
```

In-boundary provider with no static key; it authenticates through IRSA using the
`coder` ServiceAccount role `usgov-coderdemo-coder-bedrock`. The primary model is
the GovCloud Claude Sonnet 4.5 inference profile; the small fast model is
`amazon.nova-pro-v1:0`.

!!! note "Providers are database-managed (seed-once)"
    Since v2.34, AI Gateway providers live in the database and are managed at
    `/ai/settings`. The `CODER_AI_GATEWAY_PROVIDER_*` env vars are deprecated and
    only seed the DB on first startup. Editing a seeded env var in place later
    makes `coderd` refuse to start (the drift guard). Change providers in the
    dashboard, then reconcile the env vars.

## End-to-end request flow

1. Claude Code in the workspace pod reads `ANTHROPIC_BASE_URL` and a bearer
   token. The token is the workspace owner's Coder session token, not a raw
   Anthropic key.
2. The request hits `POST /api/v2/aibridge/anthropic/v1/messages` on the Coder
   server.
3. The AI Gateway authenticates the session token, applies governance and audit,
   then looks up the provider whose name matches the path segment.
4. The gateway forwards to that provider's upstream:
   `https://api.anthropic.com` via the NAT gateway, or Bedrock in `us-gov-west-1`
   via IRSA.

No Anthropic key is stored in the workspace; the session token is the only
credential and it is scoped to the workspace owner.

## Bedrock IRSA credential chain

1. **ServiceAccount annotation.** SA `coder/coder` is annotated
   `eks.amazonaws.com/role-arn = arn:aws-us-gov:iam::<AWS_ACCOUNT_ID>:role/usgov-coderdemo-coder-bedrock`.
2. **STS AssumeRoleWithWebIdentity.** The role trust policy allows the cluster
   OIDC provider, conditioned on `aud = sts.amazonaws.com` and
   `sub = system:serviceaccount:coder:coder`. The SDK uses the GovCloud regional
   STS endpoint (`AWS_REGION=us-gov-west-1`,
   `AWS_STS_REGIONAL_ENDPOINTS=regional`).
3. **bedrock:InvokeModel.** The inline policy `bedrock-invoke` grants
   `bedrock:InvokeModel` and `bedrock:InvokeModelWithResponseStream` on an
   allowlisted resource set (Claude Sonnet 4.5 foundation model and inference
   profile, plus Nova Pro).

## Current state

The `anthropic` provider currently holds a **placeholder** key, so routing is
verified end to end but returns `502 "all configured keys failed
authentication"`. The 502 (an upstream auth rejection, not a 404) proves the full
path works.

To make AI respond, paste a real `sk-ant-...` key into the `anthropic` provider
at `/ai/settings` (in the UI, not the k8s secret, because provider config lives
in the database). Bedrock Claude Sonnet 4.5 access is still gated;
`amazon.nova-pro-v1:0` is the proven in-GovCloud fallback.

## AI Governance dashboard

The AI Gateway is surfaced in Grafana by the AI Governance dashboard (uid
`ai-governance`, ConfigMap `coder-dashboard-ai-governance` in ns `monitoring`),
which spans AI Gateway Overview, Usage and Cost, Intercepts and Sessions, and
Agent Firewall rows. It reads from Prometheus (`coder_aibridged_*`), Loki (AI
Gateway and Agent Firewall log streams), and a read-only Postgres datasource
(`aibridge-postgres`) for token, cost, and session drill-downs. Usage panels read
`0` until live AI traffic occurs. See [Observability](observability.md).
