# Brief: Observability and Audit Readiness for the Thursday Demo

Execution-ready verification brief. Read-only. Another agent will execute it.

Authoritative context (verified this session):

- Deployment: https://dev.usgov.coderdemo.io, Coder v2.34.1 enterprise, GovCloud
  EKS, namespace `coder`. AI Governance add-on entitled (AI Bridge + Boundary).
- Coder Boundary (Agent Firewall) is enabled on a "firewalled" template. A live
  jailed workspace `austenplatform/firewall-test` is running. coderd now emits
  structured `boundary_request` audit lines (msg=boundary_request), visible via
  `kubectl -n coder logs deploy/coder`. Source:
  `/home/coder/coder/coderd/agentapi/boundary_logs.go`.
- Observability assets base path (this is where the files actually live; the
  repo-relative form `deploy/observability/*` is used below):
  `/home/coder/demoenv-workspace/usgov-phase2/deploy/observability/`.
- Dashboards present: `dashboards-boundary.yaml` (uid `agent-firewall`),
  `dashboards-aibridge.yaml` (uid `ai-gateway`), `dashboards-coder.yaml`.
  Datasources: `loki` (Loki), `prometheus` (Prometheus), `aibridge-postgres`
  (Coder RDS Postgres, read-only role `grafana_ro`).

## 1. Objective

Confirm that the audit and observability surfaces show live data for the
Thursday demo flow:

1. Agent Firewall egress allow/deny (Boundary), via the `agent-firewall`
   Grafana dashboard backed by Loki `boundary_request` events.
2. AI Gateway usage (AI Bridge): providers, interceptions, tokens, and cost,
   via the `ai-gateway` dashboard backed by the `aibridge-postgres` datasource.
3. Coder audit log: template pushes, workspace builds, and governance changes
   (MCP/spend limits), via the Coder UI `/audit` and API `/api/v2/audit`.

The deliverable for the executing agent is a pass/fail check against each
surface, plus the one concrete fix in section 7.

## 2. Boundary (Agent Firewall) dashboard verification

Dashboard: `dashboards-boundary.yaml`, uid `agent-firewall`, title
"Agent Firewall". Row "Coder Agent Firewall" holds the audit panels; row
"Agent Firewall Operations" holds Prometheus and proxy-log panels.

### 2a. Confirm Loki ingests coderd logs

Promtail scrapes all namespaces with no namespace filter (see
`promtail.yaml`, it maps `__meta_kubernetes_namespace` to label `namespace`),
so coderd logs in namespace `coder` are ingested. The audit panels select
`{namespace=~`(coder|coder-workspaces)`}`, which covers coderd.

Verify ingestion (Grafana Explore, datasource Loki, or LogCLI):

```
{namespace=~"(coder|coder-workspaces)"} |= "boundary_request" | logfmt | decision=~"deny|allow"
```

Expect non-empty results. Boundary is jailing Claude Code in
`firewall-test`, which produces continuous deny events (for example
`api.anthropic.com` and `raw.githubusercontent.com`), and allowed events for
gateway traffic to `dev.usgov.coderdemo.io`.

### 2b. Panels to check (exact panel titles and queries)

- "Egress Audit (allow / deny)" (Loki, uid `loki`):

```
sum by (decision) (count_over_time({namespace=~`(coder|coder-workspaces)`} |= `boundary_request` | logfmt | decision=~`deny|allow` | owner=~`$owner` | domain=~`$domain` | template_id=~`$template_id` | template_version_id=~`$template_version_id` [$__range]))
```

- "Top Allowed Domains" and "Top Denied Domains" (Loki) parse the domain from
  `http_url` with `regexp` and `topk(20, sum by (domain) (...))`.
- "Most recent allowed requests" and "Most recent denied requests" (Loki) use
  `decision=`allow`` / `decision=`deny`` and `line_format` over fields
  `event_time`, `http_method`, `domain`, `path`, `owner`, `workspace_name`,
  `template_id`, `template_version_id`.

Dashboard variables (`domain`, `owner`, `template_id`, `template_version_id`)
are textbox type, default empty. Empty regex matches all, so the allow/deny
panels populate with no variables set. Leave them blank for the demo unless
filtering to `austenplatform`.

Field dependency to confirm on a real line: the `line_format` and the
domain `topk` panels assume the live `boundary_request` line contains
`owner`, `workspace_name`, and a parseable `http_url`. The emitter in
`boundary_logs.go` writes `decision`, `workspace_id`, `template_id`,
`template_version_id`, `http_method`, `http_url`, `event_time`, and
`matched_rule` (allow only); `owner`/`workspace_name`/`agent_name` are added by
the parent logger. Inspect one real line and confirm those fields are present:

```
kubectl -n coder logs deploy/coder --since=15m | grep boundary_request | head -3
```

If `owner` or `workspace_name` are absent, the allow/deny counts still work
(missing label matches the empty regex), but the recent-request tables show
blank owner/workspace columns. Record this as an observation, not a blocker.

### 2c. Generate fresh allow/deny events on demand

From a workspace terminal on the firewalled template:

- Deny: `boundary --proxy-port 8091 -- curl https://example.com`
- Allow: `curl https://dev.usgov.coderdemo.io`

The firewalled template's Claude Code already emits continuous deny events, so
fresh generation is optional for the demo.

## 3. Prometheus metric-name reconciliation

Dashboard `dashboards-boundary.yaml` uses
`agent_boundary_log_proxy_batches_forwarded_total` in panels "Total Batches
Forwarded", "Active Firewall Agents", and "Forwarded Batches by Workspace".

Source of truth (`/home/coder/coder/agent/boundarylogproxy/metrics.go`):

```
Namespace: "agent"
Subsystem: "boundary_log_proxy"
Name:      "batches_forwarded_total"
```

Prometheus joins these as `agent_boundary_log_proxy_batches_forwarded_total`.
Therefore the dashboard name is correct, and the prefix-less spelling
`boundary_log_proxy_batches_forwarded_total` cited in two phase2 docs is wrong.

Confirm the exported name against the live stack (any one):

```
# Prometheus label values
curl -s http://<prometheus>/api/v1/label/__name__/values | jq -r '.data[]' | grep -i boundary

# coderd aggregated agent metrics (this metric is an agent metric aggregated by coderd)
kubectl -n coder exec deploy/coder -- wget -qO- http://localhost:2112/metrics | grep -i boundary
```

Expect `agent_boundary_log_proxy_batches_forwarded_total` (plus
`agent_boundary_log_proxy_batches_dropped_total` and
`agent_boundary_log_proxy_logs_dropped_total`). The metric carries labels
`username`, `workspace_name`, `agent_name` from the coderd aggregator, which
the "Forwarded Batches by Workspace" panel groups by (`workspace_name`,
`username`).

If the live label name turns out to differ from the source, prefer fixing the
dashboard to match the live name. Based on source, no dashboard change is
expected; the fix belongs in the docs (section 7).

## 4. AI Bridge (AI Gateway) dashboard verification

Dashboard: `dashboards-aibridge.yaml`, uid `ai-gateway`, title "AI Gateway".

### 4a. Confirm the Postgres datasource is connected

Datasource `aibridge-postgres` (`datasource-aibridge-postgres.yaml`) points to
`usgov-coderdemo-pg...rds.amazonaws.com:5432`, database `coder`, user
`grafana_ro`, password from env `${AIGOV_DB_PASSWORD}` (Secret
`aigov-grafana-db` in namespace `monitoring`). Verify in Grafana:
Connections, Data sources, "AI Gateway DB", Save & test, expect success.

### 4b. Panels showing live data (Postgres)

- "Total Interceptions": `SELECT count(*) AS value FROM aibridge_interceptions WHERE $__timeFilter(started_at)`
- "Active Sessions": `count(DISTINCT session_id)` over `aibridge_interceptions`
- "Unique Users": `count(DISTINCT initiator_id)` over `aibridge_interceptions`
- "Interceptions by Provider/Model/User", "Recent Interceptions", "Sessions".

Usage and cost panels ("Input/Output/Cache/Total Tokens", "Estimated Cost",
"Tokens Over Time", "Estimated Cost Over Time", "Top Users by Usage & Cost",
"Token Usage Detail") read from `aibridge_token_usages` joined to
`ai_model_prices` (71 rows, includes `claude-sonnet-4-5`). Confirm whether
token rows exist; if the Anthropic key in use is a placeholder, these can be
zero by design. Because the gateway has been used this session, confirm live
token/cost data is present and call it out if still zero.

Provider-health stats ("Configured Providers", "Provider Reload Status",
"Last Successful Reload", "Provider Inventory") come from Prometheus
`coder_aibridged_*`; the "AI Gateway Log Stream" and event-rate panels come
from Loki (namespace `coder`). Confirm each row renders without datasource
errors.

## 5. Coder audit log verification

UI: open `https://dev.usgov.coderdemo.io/audit` as an admin. API:

```
curl -sS -H "Coder-Session-Token: $CODER_SESSION_TOKEN" \
  "https://dev.usgov.coderdemo.io/api/v2/audit?limit=50" | jq '.audit_logs[] | {action, resource_type, time}'
```

Confirm the log records the demo-relevant actions:

- Template pushes / new template versions (resource_type `template` or
  `template_version`, action `create`/`write`), including the firewalled
  template.
- Workspace builds (resource_type `workspace_build` / `workspace`).
- Governance changes for the demo: MCP server config and spend-limit changes
  (filter the UI by the relevant resource type, or grep the API response for
  the changed fields). Confirm at least one such entry exists; if none, perform
  one change before the demo so it appears.

Note the audit log (Postgres `audit_logs`) is distinct from the
`boundary_request` application logs in Loki. Both must be checked.

## 6. Demo-day checklist (5 minutes)

1. Grafana, dashboard "Agent Firewall": "Egress Audit (allow / deny)" shows
   both allow and deny in the last 15m. If flat, run the deny/allow curls in
   section 2c.
2. Same dashboard: "Top Denied Domains" lists `api.anthropic.com` /
   `raw.githubusercontent.com`; "Most recent denied requests" table populated.
3. Same dashboard: "Total Batches Forwarded" stat is non-zero (Prometheus).
4. Grafana, dashboard "AI Gateway": "Total Interceptions", "Active Sessions",
   "Unique Users" non-zero; "Interceptions by Provider" populated. If tokens
   were generated, confirm "Estimated Cost" non-zero.
5. Coder UI `/audit`: a recent template push and a workspace build are visible.
6. Confirm no panel shows a red datasource error (loki, prometheus,
   aibridge-postgres all healthy under Grafana, Connections, Data sources).

## 7. Concrete fixes found (described only, do not edit)

One fix, in docs (the dashboard is already correct):

- File: `deploy/observability/../docs/architecture/agent-firewall-feasibility.md`
  (absolute: `/home/coder/demoenv-workspace/usgov-phase2/docs/architecture/agent-firewall-feasibility.md`),
  line 101. Replace `boundary_log_proxy_batches_forwarded_total` with
  `agent_boundary_log_proxy_batches_forwarded_total`.
- File:
  `/home/coder/demoenv-workspace/usgov-phase2/aoi/plan-firewall-and-auth-mcp.md`,
  line 131. Same replacement: add the `agent_` prefix so the cited metric
  matches the exported name and the dashboard.

Stale-doc note (optional, lower priority): both
`deploy/observability/AI_GOVERNANCE_DASHBOARD.md` (around lines 138 to 144) and
the header comment of `deploy/observability/dashboards-boundary.yaml` (around
lines 25 to 27) state that `boundary_request` allow/deny events "are not
emitted in this stack yet". That is now false on Coder v2.34.1; coderd emits
them and the `agent-firewall` dashboard's allow/deny panels populate. If time
allows, update that prose to reflect that allow/deny audit is now live. Do not
change any panel JSON; the queries are correct.

No dashboard JSON edits are required.

## 8. Risks and open questions

- Token/cost panels depend on real metered AI traffic. If the Anthropic key is
  a placeholder, `aibridge_token_usages` may be empty and cost reads zero by
  design. Confirm live token rows exist before relying on cost panels in the
  demo.
- `boundary_request` line fields: confirm `owner` and `workspace_name` are on
  the live line (section 2b). If absent, recent-request tables show blank
  owner/workspace columns; allow/deny counts are unaffected.
- Log retention: Loki retention may drop older `boundary_request` lines.
  Use a recent time range (last 15m to 1h) for the demo.
- Prometheus scrape of the aggregated agent metric: section 3 assumes coderd
  exposes `agent_boundary_*` on its `/metrics`. If the live label name differs
  from source, fix the dashboard to match (not expected based on source).
- The datasource doc references Coder v2.34.0 while the live deployment is
  v2.34.1. Cosmetic only; no action required.
- Access: if the executing agent lacks working Grafana/Prometheus/Loki or
  kubectl access, treat sections 2 to 5 as steps to run once access is granted
  rather than completed checks.

Generated by Coder Agents.
