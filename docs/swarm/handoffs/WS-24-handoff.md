# WS-24 handoff: swap to upstream observability dashboards

| Field | Value |
|---|---|
| **Workstream** | WS-24 |
| **Status** | PARTIAL (authoring complete; awaiting root apply) |
| **Author scope** | Authoring + read-only inspection only. No cluster apply, no delete, no git. |
| **Upstream SHA** | `863d498843f86d5ac07cf9b3eb2bb27ecdda706a` (tag `v0.7.1`, repo `coder/observability`) |
| **Upstream boundary file** | `coder-observability/templates/dashboards/_dashboards_boundary.json.tpl` |

## What changed

Two new sidecar-loaded dashboard ConfigMaps, authored in the worktree, not yet
applied:

- `deploy/observability/dashboards-aibridge.yaml` -> ConfigMap
  `coder-dashboard-aibridge`, dashboard uid `ai-gateway`, title `AI Gateway`
  (33 panels: AI Gateway Overview, Usage & Cost, Intercepts & Sessions).
- `deploy/observability/dashboards-boundary.yaml` -> ConfigMap
  `coder-dashboard-boundary`, dashboard uid `agent-firewall`, title
  `Agent Firewall` (16 panels: adapted upstream egress audit + in-repo
  operations).

Both replace the single combined dashboard `coder-dashboard-ai-governance`
(uid `ai-governance`) from `deploy/observability/dashboards-ai-governance.yaml`,
which is left untouched on disk for root to remove at apply time.

Full panel-to-datasource mapping: `docs/swarm/workstreams/WS-24-dashboards.md`.

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

```sh
kubectl apply -f deploy/observability/dashboards-ai-governance.yaml
kubectl delete configmap coder-dashboard-aibridge coder-dashboard-boundary -n monitoring
```

## Notes for downstream workstreams

- Datasource uids are unchanged (`prometheus`, `loki`, `aibridge-postgres`); the
  read-only `aibridge-postgres` datasource and the Prometheus/Loki datasources
  stay wired exactly as before.
- Once real AI traffic and audited egress flow, the needs-live-traffic panels
  populate with no dashboard change. Emitting `boundary_request` audit events
  (newer Coder that logs them under `coderd.agentrpc`, plus audited egress) is
  what lights up the egress allow/deny panels.
