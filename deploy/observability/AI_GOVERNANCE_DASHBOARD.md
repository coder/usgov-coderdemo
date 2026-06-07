# AI Governance dashboard

The `AI Governance` Grafana dashboard (uid `ai-governance`,
`deploy/observability/dashboards-ai-governance.yaml`) is the customer-facing view
of the Coder AI Governance add-on. It shows what both halves of the add-on
intercept, meter, and log:

- **AI Gateway**, implemented in Coder as AI Bridge (`aibridged`).
- **Agent Firewall**, implemented in Coder as Boundary.

The display terminology is deliberately product-facing: panels, rows, and prose
say "AI Gateway" and "Agent Firewall". The underlying identifiers are unchanged,
so PromQL still references `coder_aibridged_*` and `agent_boundary_*`, LogQL
still matches the literal log text `aibridged` and `boundary`, and the Coder
database tables keep their `aibridge_*` and `boundary_*` names.

## Data sources

| Source | uid | Powers |
|---|---|---|
| Prometheus | `prometheus` | Provider health and reload status (`coder_aibridged_*`); Agent Firewall forwarded-batch counters (`agent_boundary_log_proxy_batches_forwarded_total`). |
| Loki | `loki` | AI Gateway log stream (namespace `coder`) and Agent Firewall log stream (namespace `coder-workspaces`), plus their event-rate panels. |
| AI Gateway DB (Postgres) | `aibridge-postgres` | Usage, cost, intercept, session, prompt, and tool drill-downs from the Coder database. Read-only role `grafana_ro`. |

Why a Postgres datasource is required: the deployed Coder (v2.34.0) exposes only
provider-health gauges for the AI Gateway to Prometheus, and the latest
`coder/coder` adds no token, request, or cost metrics either. The per-interception,
per-session, token, and cost data lives exclusively in the Coder database
(`aibridge_interceptions`, `aibridge_token_usages`, `aibridge_user_prompts`,
`aibridge_tool_usages`, `aibridge_model_thoughts`, `boundary_sessions`,
`ai_model_prices`). Prometheus and Loki are used wherever they suffice; Postgres
is used only for the drill-downs that have no metric or log equivalent.

## Panels by row

### AI Gateway Overview

- **Configured Providers** (stat) -> Prometheus
- **Provider Reload Status** (stat) -> Prometheus
- **Last Successful Reload** (stat) -> Prometheus
- **Total Interceptions** (stat) -> Postgres
- **Active Sessions** (stat) -> Postgres
- **Unique Users** (stat) -> Postgres
- **Provider Inventory** (table) -> Prometheus
- **Interceptions by Provider** (pie) -> Postgres
- **Interception Activity** (timeseries) -> Postgres
- **AI Gateway Log Stream** (logs) -> Loki
- **AI Gateway Log Event Rate** (timeseries) -> Loki

### Usage & Cost

- **Input Tokens** (stat) -> Postgres
- **Output Tokens** (stat) -> Postgres
- **Cache Tokens** (stat) -> Postgres
- **Total Tokens** (stat) -> Postgres
- **Estimated Cost** (stat) -> Postgres
- **Cost / Interception** (stat) -> Postgres
- **Tokens Over Time** (timeseries) -> Postgres
- **Estimated Cost Over Time** (timeseries) -> Postgres
- **Top Users by Usage & Cost** (table) -> Postgres
- **Usage & Cost by Model** (table) -> Postgres
- **Token Split** (pie) -> Postgres
- **Interceptions by Model** (pie) -> Postgres
- **Interceptions by User** (bar gauge) -> Postgres

### Intercepts & Sessions

- **Recent Interceptions** (table) -> Postgres
- **Sessions** (table) -> Postgres
- **Recent User Prompts** (table) -> Postgres
- **Recent Tool Calls** (table) -> Postgres
- **Token Usage Detail** (table) -> Postgres

### Agent Firewall

- **Total Batches Forwarded** (stat) -> Prometheus
- **Active Firewall Agents** (stat) -> Prometheus
- **Firewall Sessions** (stat) -> Postgres
- **Forwarded Batches by Workspace** (timeseries) -> Prometheus
- **Active Firewall Agents** (table) -> Prometheus
- **Firewall Sessions** (table) -> Postgres
- **Agent Firewall Log Stream** (logs) -> Loki
- **Agent Firewall Log Event Rate** (timeseries) -> Loki

## Cost derivation

`ai_model_prices` stores per-million-token prices in micro-units (1 dollar =
1,000,000 units), with separate input, output, cache-read, and cache-write
columns. Cost panels join metered token rows to that table and compute dollars
as:

```
cost_usd = (input_tokens*input_price + output_tokens*output_price
            + cache_read_input_tokens*cache_read_price
            + cache_write_input_tokens*cache_write_price) / 1e12
```

The live `ai_model_prices` table is populated (71 rows, including the
`claude-sonnet-4-5` family used in the demo), so cost is fully derivable once
token usage is recorded.

## Read-only Postgres datasource and credential handling

- **Role**: `grafana_ro` is a least-privilege Postgres role (LOGIN, no
  superuser, no CREATEROLE) with SELECT on only the AI Gateway / Agent Firewall
  tables plus `users` and `workspace_agents` for joins. The Coder application
  role (`coder`) lacks CREATEROLE, so the role is created as the RDS master user
  (AWS Secrets Manager `usgov-coderdemo/rds/master`). Definition:
  `deploy/observability/sql/aibridge-grafana-ro.sql`.
- **Credential storage**: the `grafana_ro` password is stored only in the
  Kubernetes Secret `aigov-grafana-db` (namespace `monitoring`, key
  `AIGOV_DB_PASSWORD`). It is never committed to git.
- **Datasource provisioning**: `deploy/observability/datasource-aibridge-postgres.yaml`
  is a ConfigMap labelled `grafana_datasource: "1"` (loaded by the Grafana
  sidecar, like `loki-datasource.yaml`). Its `secureJsonData.password` is
  `${AIGOV_DB_PASSWORD}`, which Grafana expands from the env var injected via
  `kube-prometheus-stack-values.yaml` (`grafana.envValueFrom`), mirroring the
  existing OIDC client-secret pattern. `editable: false` and `isDefault: false`.
- **Setup / reproduce**:
  `deploy/observability/scripts/setup-aibridge-db-datasource.sh` is idempotent.
  It resolves (or generates) the password, applies the role SQL as the RDS
  master, publishes the Kubernetes Secret, and applies the datasource ConfigMap.
- **Revoke**: REVOKE the grants and `DROP ROLE grafana_ro`, delete the
  `aigov-grafana-db` Secret, and remove the datasource ConfigMap.

## Sparse and blocked panels

The demo Anthropic key is a placeholder, so AI calls fail before any tokens are
metered. The following are correct but stay near zero or empty until real AI
traffic flows; this is expected, not an error:

- Token and cost stats, **Tokens Over Time**, **Estimated Cost Over Time**, and
  **Token Usage Detail** read 0 (no rows in `aibridge_token_usages` yet).
- **Recent User Prompts** and **Recent Tool Calls** are empty (no rows in
  `aibridge_user_prompts` / `aibridge_tool_usages` yet).
- **Firewall Sessions** (stat and table) read 0 (no rows in `boundary_sessions`
  yet).
- The Agent Firewall log stream currently carries only Boundary proxy lifecycle
  lines. The upstream `coder/observability` boundary dashboard parses
  `boundary_request` allow / deny audit events from the `coderd.agentrpc`
  logger; those events are not emitted in this stack until egress traffic is
  audited, so allow / deny breakdown panels are intentionally not included here
  yet. They become populatable once Boundary audits real egress (and would also
  benefit from a newer Coder that logs `boundary_request`).

Panels that already have data: provider health and inventory, total
interceptions, active sessions, unique users, interceptions by provider / model /
user, **Recent Interceptions**, **Sessions**, and the Agent Firewall log stream.
