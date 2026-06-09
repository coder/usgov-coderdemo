# WS-24: Swap to upstream Coder observability dashboards

| Field | Value |
|---|---|
| **Workstream** | WS-24 |
| **Phase** | 2 |
| **Status** | PARTIAL (authoring done; root applies) |
| **Track** | Observability |
| **Touches** | `deploy/observability/dashboards-aibridge.yaml` (new), `deploy/observability/dashboards-boundary.yaml` (new), this doc, `docs/swarm/handoffs/WS-24-handoff.md` |
| **Does not touch** | `deploy/observability/dashboards-ai-governance.yaml` (root deletes the live ConfigMap at apply time) |

## Goal

Replace the single bespoke `AI Governance` dashboard with two dashboards that
track the upstream `coder/observability` layout, while keeping every panel wired
to a datasource that actually holds the data in this stack. Display terminology
stays product-facing: "AI Bridge" / "aibridge" reads as **AI Gateway**, and
"Boundary" reads as **Agent Firewall**. Underlying identifiers are unchanged:
PromQL still uses `coder_aibridged_*` and `agent_boundary_*`, LogQL still matches
the literal log text `aibridged`, `boundary`, and `boundary_request`, and the
Coder database keeps its `aibridge_*` and `boundary_*` table names.

## Upstream provenance

| Item | Value |
|---|---|
| Repo | `coder/observability` |
| Reference clone | `/home/coder/demoenv-workspace/reference/observability` (read-only) |
| SHA | `863d498843f86d5ac07cf9b3eb2bb27ecdda706a` |
| Tag | `v0.7.1` |
| Boundary source | `coder-observability/templates/dashboards/_dashboards_boundary.json.tpl` (uid `agent-boundaries`, title `Coder Agent Boundaries`) |

### Critical finding: upstream has no AI Bridge dashboard

The pinned reference ships **no aibridge dashboard** at any tag or branch. The
only AI-governance-adjacent prebuilt dashboard upstream is the boundary one. So
there is nothing upstream to "swap to" for the AI Gateway half.

Resolution: the new `dashboards-aibridge.yaml` retains the in-repo AI Gateway
panels (already mapped to this stack's datasources) split out of the combined
`dashboards-ai-governance.yaml`. The new `dashboards-boundary.yaml` is the
upstream boundary dashboard adapted to this stack, with the in-repo Agent
Firewall operations panels folded in so the view has populated data today. This
deviation is flagged for root in the handoff.

## Datasources (all already provisioned for the kube-prometheus-stack Grafana)

| Datasource | uid | Holds |
|---|---|---|
| Prometheus | `prometheus` | Provider health gauges (`coder_aibridged_*`); Agent Firewall forwarded-batch counters (`agent_boundary_log_proxy_batches_forwarded_total`). |
| Loki | `loki` | AI Gateway log stream (namespace `coder`), Agent Firewall proxy log stream (namespace `coder-workspaces`), and the `boundary_request` egress audit events once emitted. |
| AI Gateway DB (Postgres) | `aibridge-postgres` | Token, cost, interception, session, prompt, and tool drill-downs from the Coder database via the read-only `grafana_ro` role. |

Why Postgres is required: the deployed Coder exposes only provider-health gauges
for the AI Gateway to Prometheus. Per-interception, per-session, token, and cost
data lives only in the Coder database (`aibridge_interceptions`,
`aibridge_token_usages`, `aibridge_user_prompts`, `aibridge_tool_usages`,
`boundary_sessions`, `ai_model_prices`). The Prometheus and Loki datasources are
used wherever they suffice.

## AI Gateway dashboard (`dashboards-aibridge.yaml`, uid `ai-gateway`)

33 panels across three rows, unchanged queries from the combined dashboard.

| Panel | Type | Datasource | Populated now? | Note |
|---|---|---|---|---|
| Configured Providers | stat | Prometheus | Yes | `count(coder_aibridged_provider_info)` |
| Provider Reload Status | stat | Prometheus | Yes | reload-timestamp compare |
| Last Successful Reload | stat | Prometheus | Yes | |
| Total Interceptions | stat | Postgres | Yes | `aibridge_interceptions` |
| Active Sessions | stat | Postgres | Yes | |
| Unique Users | stat | Postgres | Yes | |
| Provider Inventory | table | Prometheus | Yes | |
| Interceptions by Provider | pie | Postgres | Yes | |
| Interception Activity | timeseries | Postgres | Yes | |
| AI Gateway Log Stream | logs | Loki | Yes | `{namespace="coder"} \|~ "aibridged"` lifecycle lines |
| AI Gateway Log Event Rate | timeseries | Loki | Yes | |
| Input / Output / Cache / Total Tokens | stat | Postgres | No (live traffic) | `aibridge_token_usages` empty until AI calls succeed |
| Estimated Cost, Cost / Interception | stat | Postgres | No (live traffic) | priced against `ai_model_prices` |
| Tokens Over Time, Estimated Cost Over Time | timeseries | Postgres | No (live traffic) | |
| Top Users by Usage & Cost, Usage & Cost by Model | table | Postgres | No (live traffic) | |
| Token Split | pie | Postgres | No (live traffic) | |
| Interceptions by Model, Interceptions by User | pie / bargauge | Postgres | Yes | interception rows exist |
| Recent Interceptions | table | Postgres | Yes | |
| Sessions | table | Postgres | Yes | |
| Recent User Prompts | table | Postgres | No (live traffic) | `aibridge_user_prompts` empty |
| Recent Tool Calls | table | Postgres | No (live traffic) | `aibridge_tool_usages` empty |
| Token Usage Detail | table | Postgres | No (live traffic) | |

## Agent Firewall dashboard (`dashboards-boundary.yaml`, uid `agent-firewall`)

16 panels in two rows: the adapted upstream egress-audit panels, then the
in-repo operations panels.

| Panel | Type | Datasource | Populated now? | Source | Note |
|---|---|---|---|---|---|
| Request Totals | stat | Loki | No (live traffic) | upstream | allow/deny counts from `boundary_request` |
| Top Allowed Domains | table | Loki | No (live traffic) | upstream | topk(20) domain on `decision=allow` |
| Top Denied Domains | table | Loki | No (live traffic) | upstream | topk(20) domain on `decision=deny` |
| Most recent allowed requests | table | Loki | No (live traffic) | upstream | logfmt + regexp + line_format |
| Most recent denied requests | table | Loki | No (live traffic) | upstream | |
| Total Batches Forwarded | stat | Prometheus | Yes | in-repo | `sum(agent_boundary_log_proxy_batches_forwarded_total)` |
| Active Firewall Agents | stat | Prometheus | Yes | in-repo | `count(agent_boundary_log_proxy_batches_forwarded_total)` |
| Firewall Sessions | stat | Postgres | No (live traffic) | in-repo | `boundary_sessions` empty until sessions recorded |
| Forwarded Batches by Workspace | timeseries | Prometheus | Yes | in-repo | |
| Active Firewall Agents | table | Prometheus | Yes | in-repo | |
| Firewall Sessions | table | Postgres | No (live traffic) | in-repo | |
| Agent Firewall Log Stream | logs | Loki | Yes | in-repo | `{namespace="coder-workspaces"} \|= "boundary"` proxy lifecycle lines |
| Agent Firewall Log Event Rate | timeseries | Loki | Yes | in-repo | |

## Adaptations applied to the upstream boundary dashboard

- **Loki stream selector**: upstream selects
  `{ <non-workspace-selector>, logger=`coderd.agentrpc` }`. In this stack
  promtail exposes only `app`, `namespace`, `pod`, `container`, and `node_name`
  stream labels (see `deploy/observability/promtail.yaml`); there is no `logger`
  stream label, so the upstream selector would match nothing. Replaced with
  `{namespace=~`(coder|coder-workspaces)`}` plus the `boundary_request` line
  filter, mirroring the proven in-repo Agent Firewall log panels. The `logger`
  value is carried inside the log line, not as a stream label, so the
  `boundary_request` line filter is the reliable narrow.
- **Helm includes resolved to literals**: this artifact is rendered JSON, not a
  chart template, so `non-workspace-selector`, `dashboard-range`, and
  `dashboard-refresh` are inlined. The `line_format` Helm escaping
  (`{{ "{{" }}.event_time{{ "}}" }}`) is written as the literal Loki form
  `{{ .event_time }}`.
- **Display renames only**: title `Coder Agent Boundaries` reads as
  `Agent Firewall`; prose reworded. No PromQL metric, LogQL literal, datasource
  uid, or DB table renamed.
- **Built-in annotation dropped**: upstream carries a `-- Grafana --` built-in
  annotation; this dashboard sets `annotations.list` to empty like the in-repo
  dashboards, which also keeps the file free of the spaced double hyphen token.
- **Template variables**: the four upstream textbox filters (`domain`, `owner`,
  `template_id`, `template_version_id`) are ported so `$owner`, `$domain`, etc.
  resolve.

## Populated vs. needs-live-traffic vs. broken

- **Populated today**: provider health and inventory, interception / session /
  user counts, interceptions by provider / model / user, recent interceptions,
  sessions, AI Gateway and Agent Firewall log streams and their event rates,
  forwarded-batch counters, active firewall agents.
- **Correct but needs live traffic** (zeros/empty are expected, not errors):
  all token and cost panels, recent prompts, recent tool calls, token usage
  detail, `boundary_sessions` stat and table, and every egress-audit panel
  (allow/deny). The demo Anthropic key is a placeholder, so AI calls fail before
  metering tokens, and `boundary_request` audit events are not emitted until
  Boundary audits real egress.
- **Genuinely broken**: none. Every panel targets a real series, log query, or
  table in this stack.

## Conventions

- Dash-scan clean: no emdash (U+2014), no endash (U+2013), no spaced double
  hyphen. Files end with a newline; no tabs.
- Sidecar pickup: both ConfigMaps carry `grafana_dashboard: "1"` in namespace
  `monitoring`, matching `dashboards-ai-governance.yaml`.
