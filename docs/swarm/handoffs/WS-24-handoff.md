# WS-24 handoff: swap to upstream observability dashboards

| Field | Value |
|---|---|
| **Workstream** | WS-24 |
| **Status** | APPLIED + VERIFIED (2026-06-08). `AI Gateway` (uid `ai-gateway`) gained a holistic intercept row (tools, MCP, prompts; 9 new panels, 42 total) wired to `aibridge-postgres`. The old combined `coder-dashboard-ai-governance` is now DELETED live (ConfigMap) and on disk (`dashboards-ai-governance.yaml` removed from the worktree). Grafana provisioned cleanly with no errors. |
| **Author scope** | Authoring + read-only inspection only. No cluster apply, no delete, no git. |
| **Upstream SHA** | `863d498843f86d5ac07cf9b3eb2bb27ecdda706a` (tag `v0.7.1`, repo `coder/observability`) |
| **Upstream boundary file** | `coder-observability/templates/dashboards/_dashboards_boundary.json.tpl` |

## What changed

Two new sidecar-loaded dashboard ConfigMaps, authored in the worktree, not yet
applied:

- `deploy/observability/dashboards-aibridge.yaml` -> ConfigMap
  `coder-dashboard-aibridge`, dashboard uid `ai-gateway`, title `AI Gateway`
  (42 panels: AI Gateway Overview, Usage & Cost, Intercepts & Sessions, and
  the new `Intercepts: Tools, MCP & Prompts` row added 2026-06-08; see the
  intercept-panels section below).
- `deploy/observability/dashboards-boundary.yaml` -> ConfigMap
  `coder-dashboard-boundary`, dashboard uid `agent-firewall`, title
  `Agent Firewall` (16 panels: adapted upstream egress audit + in-repo
  operations).

Both replace the single combined dashboard `coder-dashboard-ai-governance`
(uid `ai-governance`). That dashboard has now been removed: the live ConfigMap
`coder-dashboard-ai-governance` was deleted from the `monitoring` namespace and
the source file `deploy/observability/dashboards-ai-governance.yaml` was deleted
from the worktree, so it is not re-applied.

Full panel-to-datasource mapping: `docs/swarm/workstreams/WS-24-dashboards.md`.

## Applied result (root, 2026-06-08)

`kubectl apply -f deploy/observability/dashboards-aibridge.yaml -f
deploy/observability/dashboards-boundary.yaml` created both ConfigMaps. The
Grafana sidecar wrote `/tmp/dashboards/ai-gateway.json` and
`/tmp/dashboards/agent-firewall.json`; the grafana container logged `starting to
provision dashboards` then `finished to provision dashboards` with no errors.
Datasources `prometheus`, `loki`, and `aibridge-postgres` are all present, so the
panels resolve. The old combined `coder-dashboard-ai-governance` (uid
`ai-governance`) has since been deleted live and on disk, and the `ai-gateway`
dashboard was extended with the intercept panels; see the two sections below.

## Intercept panels added (2026-06-08, `ai-gateway`)

New row `Intercepts: Tools, MCP & Prompts` (panel id 34) plus 8 panels, all on
the read-only `aibridge-postgres` SQL datasource. Prometheus exposes only
provider-health gauges and Loki only lifecycle log lines, so tool / MCP / prompt
detail comes exclusively from the Coder database. Panels key on STABLE
identifiers (`model` id, `tool` name, `server_url`, `provider_name`), never on
model display names, because display names are being renamed concurrently.

Data model verified against the reference clone (`reference/coder`, commit
`47a8c9572f`) and confirmed live read-only via the `aibridge-postgres` datasource:

- `aibridge_tool_usages` columns `tool`, `server_url`, `injected`,
  `invocation_error`, `interception_id`, `created_at`:
  `coderd/database/migrations/000370_aibridge.up.sql:47-66`
  (`server_url` is the MCP server name and is NULL for client/built-in tools;
  `injected` true means Bridge injected and invoked the tool, per the column
  comments at `000370_aibridge.up.sql:62-64`).
- `aibridge_user_prompts` columns `prompt`, `interception_id`, `created_at`:
  `coderd/database/migrations/000370_aibridge.up.sql:31-45`.
- `aibridge_interceptions` columns `model`, `provider`, `started_at`,
  `initiator_id`: `coderd/database/migrations/000370_aibridge.up.sql:1-12`;
  `provider_name`: `coderd/database/migrations/000458_aibridge_provider_name.up.sql:1`.
- `users.username` join (already used by the existing intercept panels; the
  `grafana_ro` role has SELECT on `users`).

Panels (id, title, type, datasource, query):

1. **34 `Intercepts: Tools, MCP & Prompts`** (row) layout only.
2. **35 `Tool Calls Over Time`** (timeseries, `aibridge-postgres`): per-tool
   call volume per bucket.
   ```sql
   SELECT $__timeGroupAlias(tcu.created_at, $__interval), tcu.tool AS metric, count(*) AS "Calls"
   FROM aibridge_tool_usages tcu
   WHERE $__timeFilter(tcu.created_at)
   GROUP BY 1, tcu.tool ORDER BY 1
   ```
3. **36 `Top Intercepted Tools`** (table, `aibridge-postgres`): tool name with
   call, injected, and error counts.
   ```sql
   SELECT tcu.tool AS "Tool", count(*) AS "Calls",
          count(*) FILTER (WHERE tcu.injected) AS "Injected",
          count(*) FILTER (WHERE tcu.invocation_error IS NOT NULL) AS "Errors",
          count(DISTINCT tcu.interception_id) AS "Interceptions"
   FROM aibridge_tool_usages tcu
   WHERE $__timeFilter(tcu.created_at)
   GROUP BY 1 ORDER BY "Calls" DESC LIMIT 100
   ```
4. **37 `Tool Calls by User & Model`** (table, `aibridge-postgres`): keyed on the
   stable `i.model` id and `provider_name`.
   ```sql
   SELECT u.username AS "User", i.provider_name AS "Provider", i.model AS "Model",
          tcu.tool AS "Tool", count(*) AS "Calls"
   FROM aibridge_tool_usages tcu
   JOIN aibridge_interceptions i ON i.id = tcu.interception_id
   LEFT JOIN users u ON u.id = i.initiator_id
   WHERE $__timeFilter(tcu.created_at)
   GROUP BY 1,2,3,4 ORDER BY "Calls" DESC LIMIT 100
   ```
5. **38 `MCP Servers & Tool Sources`** (table, `aibridge-postgres`): groups by
   `server_url` (the MCP server) and `injected`; NULL `server_url` shown as
   `client/builtin`.
   ```sql
   SELECT COALESCE(tcu.server_url, 'client/builtin') AS "Tool Source (MCP server_url)",
          tcu.injected AS "Injected (MCP)", count(*) AS "Calls",
          count(DISTINCT tcu.tool) AS "Distinct Tools",
          count(*) FILTER (WHERE tcu.invocation_error IS NOT NULL) AS "Errors"
   FROM aibridge_tool_usages tcu
   WHERE $__timeFilter(tcu.created_at)
   GROUP BY 1,2 ORDER BY "Calls" DESC LIMIT 100
   ```
6. **39 `Injected vs Client Tool Calls`** (piechart, `aibridge-postgres`):
   share of MCP-injected versus client/built-in tool calls.
   ```sql
   SELECT CASE WHEN tcu.injected THEN 'Injected (MCP, Bridge-invoked)'
               ELSE 'Client/Built-in' END AS source, count(*) AS calls
   FROM aibridge_tool_usages tcu
   WHERE $__timeFilter(tcu.created_at)
   GROUP BY 1 ORDER BY 2 DESC
   ```
7. **40 `Prompt Volume Over Time`** (timeseries, `aibridge-postgres`): user
   prompt volume per bucket, one series per `provider_name`.
   ```sql
   SELECT $__timeGroupAlias(up.created_at, $__interval), i.provider_name AS metric, count(*) AS "Prompts"
   FROM aibridge_user_prompts up
   JOIN aibridge_interceptions i ON i.id = up.interception_id
   WHERE $__timeFilter(up.created_at)
   GROUP BY 1, i.provider_name ORDER BY 1
   ```
8. **41 `Prompts by User`** (bargauge, `aibridge-postgres`): prompt counts per
   user.
   ```sql
   SELECT u.username AS "User", count(*) AS "Prompts"
   FROM aibridge_user_prompts up
   JOIN aibridge_interceptions i ON i.id = up.interception_id
   LEFT JOIN users u ON u.id = i.initiator_id
   WHERE $__timeFilter(up.created_at)
   GROUP BY 1 ORDER BY "Prompts" DESC LIMIT 25
   ```
9. **42 `Recent Intercepted Prompts`** (table, `aibridge-postgres`): recent
   prompts (truncated) with user, provider, and stable model id.
   ```sql
   SELECT up.created_at AS "Time", u.username AS "User", i.provider_name AS "Provider",
          i.model AS "Model", left(up.prompt, 300) AS "Prompt (truncated)"
   FROM aibridge_user_prompts up
   JOIN aibridge_interceptions i ON i.id = up.interception_id
   LEFT JOIN users u ON u.id = i.initiator_id
   WHERE $__timeFilter(up.created_at)
   ORDER BY up.created_at DESC LIMIT 100
   ```

All 9 queries were validated live through Grafana `POST /api/ds/query` against
`aibridge-postgres` before apply (each returned a frame, no datasource error).
Current demo data is sparse (30 interceptions, 28 prompts, 2 client-defined tool
calls with NULL `server_url`); the MCP-source breakdown populates further once
injected MCP tools are exercised.

## ai-governance removal (live + on disk, 2026-06-08)

- `kubectl delete configmap coder-dashboard-ai-governance -n monitoring` ->
  `configmap "coder-dashboard-ai-governance" deleted`.
- `rm deploy/observability/dashboards-ai-governance.yaml` (removed from worktree).
- `kubectl apply -f deploy/observability/dashboards-aibridge.yaml` ->
  `configmap/coder-dashboard-aibridge configured`.
- Grafana sidecar `/tmp/dashboards`: `ai-gateway.json` rewritten,
  `ai-governance.json` GONE; grafana container logged `starting to provision
  dashboards` then `finished to provision dashboards`, 0 `level=error` lines.
- `kubectl get cm -n monitoring | grep ai-governance` returns nothing;
  `GET /api/dashboards/uid/ai-gateway` reports 42 panels.

## Decision flagged for root / human

Upstream `coder/observability` at the pinned SHA ships **no AI Bridge
dashboard**, only a boundary one. The AI Gateway dashboard here is therefore the
in-repo AI Gateway panels split out of the combined dashboard, not an upstream
swap. The boundary dashboard is a true upstream swap (adapted). Confirm this is
acceptable, or decide whether to wait for an upstream aibridge dashboard.

## Exact apply steps (root only)

Run from the worktree root with cluster env loaded:

```sh
. ~/.config/usgov-coderdemo/env
export KUBECONFIG=/home/coder/demoenv-workspace/usgov-coderdemo/kubeconfig
export PATH="$HOME/.local/bin:$PATH"
cd /home/coder/demoenv-workspace/usgov-phase2

# 1. Apply the two new dashboards first (kiwigrid sidecar auto-imports any
#    ConfigMap labelled grafana_dashboard="1"; no Grafana restart needed).
kubectl apply -f deploy/observability/dashboards-aibridge.yaml
kubectl apply -f deploy/observability/dashboards-boundary.yaml

# 2. Remove the superseded combined dashboard ConfigMap.
kubectl delete configmap coder-dashboard-ai-governance -n monitoring
#   (equivalently: kubectl delete -f deploy/observability/dashboards-ai-governance.yaml)
```

Apply order matters: create the two new dashboards before deleting the old one
so there is no window without an AI governance view. The sidecar reflects
changes within roughly a minute.

After the live swap is confirmed, root decides separately (git is out of WS-24
scope) whether to `git rm deploy/observability/dashboards-ai-governance.yaml` and
refresh `deploy/observability/AI_GOVERNANCE_DASHBOARD.md`, which still describes
the single combined dashboard.

## PASS check

Grafana is at `https://grafana.usgov.coderdemo.io` (use root's admin or a
Grafana service-account token for the API).

1. **Dashboards loaded**: both UIDs resolve.
   ```sh
   curl -fsS -H "Authorization: Bearer $GRAFANA_TOKEN" \
     https://grafana.usgov.coderdemo.io/api/dashboards/uid/ai-gateway   >/dev/null && echo ai-gateway OK
   curl -fsS -H "Authorization: Bearer $GRAFANA_TOKEN" \
     https://grafana.usgov.coderdemo.io/api/dashboards/uid/agent-firewall >/dev/null && echo agent-firewall OK
   ```
2. **Every panel query returns HTTP 200**: drive each panel target through
   `POST /api/ds/query` against its datasource uid (`prometheus`, `loki`,
   `aibridge-postgres`). No panel should return a datasource error. Walk the
   `targets[].expr` of each panel in both dashboard JSONs and confirm a 200 for
   each. Per-datasource smoke checks:
   ```sh
   # Prometheus
   curl -fsS -H "Authorization: Bearer $GRAFANA_TOKEN" \
     "https://grafana.usgov.coderdemo.io/api/datasources/proxy/uid/prometheus/api/v1/query?query=count(coder_aibridged_provider_info)"
   # Loki
   curl -fsS -G -H "Authorization: Bearer $GRAFANA_TOKEN" \
     "https://grafana.usgov.coderdemo.io/api/datasources/proxy/uid/loki/loki/api/v1/query" \
     --data-urlencode 'query=sum(count_over_time({namespace="coder-workspaces"} |= "boundary" [5m]))'
   # Postgres (aibridge-postgres) via /api/ds/query with the panel SQL
   ```
3. **Populated panels show real data**: provider health and inventory,
   interception / session / user counts, interceptions by provider / model /
   user, recent interceptions, sessions, both log streams and event rates,
   forwarded-batch counters, active firewall agents.
4. **Zeros explained**: the only empty or zero panels must be the
   needs-live-traffic set documented in `WS-24-dashboards.md` (token and cost
   panels, recent prompts, recent tool calls, token usage detail,
   `boundary_sessions`, and all egress allow/deny audit panels). These are
   correct queries waiting on real AI and audited-egress traffic, not errors.

PASS = steps 1 and 2 all green, step 3 shows real data, and every empty panel in
step 4 is on the documented needs-live-traffic list.

## Rollback

The old combined dashboard source was deleted from the worktree, so a rollback
must restore it from git history first (for example
`git show <prev>:deploy/observability/dashboards-ai-governance.yaml`), then:

```sh
kubectl apply -f deploy/observability/dashboards-ai-governance.yaml
kubectl delete configmap coder-dashboard-aibridge coder-dashboard-boundary -n monitoring
```

To only revert the intercept panels (keep the new dashboards), restore the prior
`deploy/observability/dashboards-aibridge.yaml` and re-apply it.

## Notes for downstream workstreams

- Datasource uids are unchanged (`prometheus`, `loki`, `aibridge-postgres`); the
  read-only `aibridge-postgres` datasource and the Prometheus/Loki datasources
  stay wired exactly as before.
- Once real AI traffic and audited egress flow, the needs-live-traffic panels
  populate with no dashboard change. Emitting `boundary_request` audit events
  (newer Coder that logs them under `coderd.agentrpc`, plus audited egress) is
  what lights up the egress allow/deny panels.
