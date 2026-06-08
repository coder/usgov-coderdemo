# Observability

In-boundary observability runs on EKS in namespace `monitoring`: Prometheus,
Grafana, and Loki, all from ECR-mirrored images. Everything stays inside the
GovCloud boundary.

Source of truth: `docs/as-built/55-observability.md`, `STATUS.md`,
`deploy/observability/`.

## Metrics and dashboards

- The `prometheus-community/kube-prometheus-stack` Helm release `kps` provides
  Prometheus, Grafana, and the operator (all healthy). Alertmanager,
  node-exporter, and kube-state-metrics are disabled to keep the footprint small.
- Coder Prometheus metrics are enabled (`CODER_PROMETHEUS_ENABLE=true`,
  `CODER_PROMETHEUS_ADDRESS=0.0.0.0:2112`). A headless `coder-metrics` Service
  plus ServiceMonitor scrapes the control plane; `up{job="coder-metrics"}` is `1`.
- Six Coder Grafana dashboards (from `github.com/coder/observability`) render
  live at `https://grafana.usgov.coderdemo.io`.

## Logs (Loki + Promtail)

In-cluster logs use single-binary Grafana Loki plus a node-level Promtail
DaemonSet (hand-rolled manifests, ECR-mirrored `grafana/loki:3.5.9` and
`grafana/promtail:3.5.9`). Loki persists on a 10Gi gp3 PVC (filesystem, tsdb
schema v13, 168h retention). Promtail tails `/var/log/pods` on every node and
pushes to `loki.monitoring.svc:3100`, covering namespaces `coder`,
`coder-workspaces`, `gitlab`, `keycloak`, `monitoring`, and `external-secrets`.
A Grafana datasource ConfigMap (uid `loki`) provisions it so the Coder
dashboards' log panels resolve. Prometheus scrapes both
(`up{job="loki"}` and `up{job="promtail"}` are `1`).

## AI Governance dashboard

A merged AI Governance dashboard (uid `ai-governance`, ConfigMap
`coder-dashboard-ai-governance`) covers the AI Gateway and the Agent Firewall in
one view. AI Gateway panels use `coder_aibridged_*` plus AI Bridge Loki logs;
Agent Firewall panels use `agent_boundary_log_proxy_batches_forwarded_total` plus
Boundary Loki logs. A read-only Postgres datasource (`aibridge-postgres`, role
`grafana_ro`, least privilege, `sslmode: require`) backs the token, cost, and
session drill-downs that have no metric or log equivalent. Usage panels read `0`
until live AI traffic occurs (placeholder Anthropic key). See
[AI Gateway](ai-gateway.md).

## Grafana SSO

Grafana signs in via the same realm `coder` through a confidential OIDC client
`grafana` (`scripts/setup-grafana-oidc.py`, PKCE; secret in AWS Secrets Manager
`usgov-coderdemo/observability/grafana-oauth`, ESO-synced). Group membership maps
to org role: `/platform` to Grafana `Admin`, others to `Viewer`. A local admin is
kept as break-glass.

## Kiali (mesh console)

Kiali is the Istio mesh console at `https://kiali.usgov.coderdemo.io`, fronted by
the same realm via OIDC client `kiali` (`scripts/setup-kiali-oidc.py`). Anonymous
access is disabled, so unauthenticated users are redirected to Keycloak; any
authenticated realm user may view the mesh (`disable_rbac: true` with
`view_only_mode: true`).

## SIEM readiness

`coderd` emits structured JSON server logs (`CODER_LOGGING_JSON=/dev/stderr`),
making it SIEM-ready; audit logging is entitled and on (`/audit`). Promtail also
ships these lines to the in-cluster Loki, so they are queryable in Grafana.

!!! note "Production target"
    An AWS-native managed variant (AMP + AMG, CloudWatch to Security Lake) is the
    production target and is planned only. See
    `docs/plans/observability-aws-native.md`.
