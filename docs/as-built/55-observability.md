# 55. Observability (as-built)

In-boundary, in-cluster metrics, logs, and dashboards for the GovCloud demo: the
`prometheus-community/kube-prometheus-stack` Helm release `kps` (Prometheus +
Grafana + the Prometheus operator) in the `monitoring` namespace, scraping the
Coder control plane's Prometheus metrics and rendering Coder's prebuilt Grafana
dashboards with live data at `https://grafana.usgov.coderdemo.io`. Alongside it,
hand-rolled manifests add an in-cluster Grafana Loki and a Promtail DaemonSet
that collects pod logs from every node, queried in Grafana through a `loki`
datasource. Grafana signs in through the same Keycloak realm (`coder`) as the
rest of the stack, so the demo is one SSO. Coder audit logging is entitled and
on; structured JSON server logs make it SIEM-ready and are shipped to Loki.

This is the reliable in-cluster implementation. The AWS-native managed variant
(Amazon Managed Prometheus / Grafana, Security Lake) is planned separately and
is intentionally not built here.

Source of truth for the manifests and the reproduce/verify steps:
`deploy/observability/` and `deploy/observability/README.md`. Coder server
changes are in `deploy/coder/values.yaml`; the Grafana admin ExternalSecret is
in `deploy/platform/external-secrets/secretstore-and-externalsecrets.yaml`.

## Verification method

Mutating steps (helm install/upgrade, kubectl apply, one ASM
`create-secret`) were performed during this build against `./kubeconfig` and the
`us-gov-west-1` account `430737322961`. Live checks used read-only `kubectl get`,
the Prometheus HTTP API over a `port-forward`, and authenticated calls to the
public Grafana host. The Grafana admin password was read from the synced
Kubernetes Secret and never printed. Always target
`https://grafana.usgov.coderdemo.io` explicitly.

## Coder server changes (deploy/coder/values.yaml)

Four env vars were ADDED (the existing AI-provider seed env vars were left
untouched so the coderd drift guard does not trip):

| Env var | Value | Purpose |
|---|---|---|
| `CODER_PROMETHEUS_ENABLE` | `true` | Serve Prometheus metrics. |
| `CODER_PROMETHEUS_ADDRESS` | `0.0.0.0:2112` | Bind the metrics endpoint to the pod network (the default `127.0.0.1` is not scrapeable). |
| `CODER_PROMETHEUS_COLLECT_AGENT_STATS` | `true` | Emit per-workspace agent stats used by the workspace dashboards. |
| `CODER_LOGGING_JSON` | `/dev/stderr` | Emit structured JSON logs to stderr. |
| `CODER_LOGGING_HUMAN` | `/dev/null` | Silence the duplicate human stream so stderr carries JSON only. |

Note on logging: Coder has no single `CODER_LOG_FORMAT` flag. JSON output is
selected by pointing `--log-json` / `CODER_LOGGING_JSON` at a sink, and the
human stream (default `/dev/stderr`) is redirected to `/dev/null` to avoid
duplicate lines. Verified live: the coder pod's stderr is single-stream JSON
(for example `{"ts":...,"level":"INFO","msg":"serving connection",...}`).

Helm release `coder` went to revision 5; the Deployment rolled out 1/1. The
metrics endpoint returns `coderd_*` series: exec into the coder pod and run
`wget -qO- http://localhost:2112/metrics` to see
`coderd_api_requests_processed_total` and the `coderd_agentapi_*` family.

## The stack (Helm release kps, ns monitoring)

| Component | Live object | Storage |
|---|---|---|
| Prometheus | `prometheus-kps-kube-prometheus-stack-prometheus-0` (2/2), Service `kps-kube-prometheus-stack-prometheus:9090` | 20Gi gp3 PVC, 7d retention |
| Grafana | `kps-grafana` (3/3: grafana + dashboard sidecar + datasource sidecar), Service `kps-grafana:80` | 5Gi gp3 PVC |
| Operator | `kps-kube-prometheus-stack-operator` (1/1) | n/a |

Chart `kube-prometheus-stack-86.2.0` (operator `v0.91.0`). To keep the demo lean
and cut image mirroring, Alertmanager, node-exporter, kube-state-metrics, the
bundled alert rules, and the managed EKS control-plane ServiceMonitors are
disabled. The kubelet ServiceMonitor is kept so cAdvisor container CPU/memory
metrics power the dashboards' resource panels (9 kubelet targets are up).

### Images (ECR mirror, no pull-through in GovCloud)

Mirrored via `scripts/images.txt` + `scripts/mirror-images.sh`; chart values
override the image repos to the mirror:

- `quay/prometheus/prometheus:v3.12.0-distroless`
- `quay/prometheus-operator/prometheus-operator:v0.91.0`
- `quay/prometheus-operator/prometheus-config-reloader:v0.91.0`
- `docker-hub/grafana/grafana:13.0.1-security-01`
- `quay/kiwigrid/k8s-sidecar:2.7.3`

## Scrape path (Coder)

`coderd` serves metrics on `:2112`. The Coder chart Service exposes only the app
port, so `deploy/observability/coder-metrics.yaml` adds:

- a headless Service `coder-metrics` (ns `coder`, port 2112) selecting only the
  control-plane pod (`app.kubernetes.io/name=coder`, `instance=coder`); the
  external provisioner pods do not match and are excluded, and
- `ServiceMonitor/coder` (ns `coder`) selecting that Service.

Prometheus is set with `serviceMonitorSelectorNilUsesHelmValues: false`, so it
discovers the ServiceMonitor without a release label and adds `namespace` and
`pod` target labels. Verified live (Prometheus `/api/v1/targets`): job
`coder-metrics` is `up`, target
`http://10.0.x.x:2112/metrics`, labels `namespace="coder"`,
`pod="coder-...."`, `lastError` empty. PromQL spot checks:
`up{job="coder-metrics"}` is `1`, `sum(coderd_api_requests_processed_total)`
returns a live counter, and `container_cpu_usage_seconds_total{namespace="coder"}`
has series (cAdvisor).

## Grafana

- Datasource: the chart auto-provisions `Prometheus` (uid `prometheus`,
  default), URL `http://kps-kube-prometheus-stack-prometheus.monitoring:9090`.
  Verified via `GET /api/datasources`.
- Dashboards: six Prometheus-backed Coder dashboards from
  `github.com/coder/observability` are shipped as ConfigMaps
  (`dashboards-coder.yaml`) labelled `grafana_dashboard: "1"` and imported by
  the Grafana sidecar (`NAMESPACE=ALL`). Verified via
  `GET /api/search?type=dash-db`: Coder Control Plane (`coderd`), Coder Status,
  Coder Prebuilds, Coder Provisioners, Coder Workspaces, Coder Workspace Detail.
  Every panel targets datasource uid `prometheus`; the dashboard selectors are
  already scoped to `namespace="coder"`, `pod=~"coder.*"`, which match the
  scraped series.
- Live data: through Grafana's datasource proxy, the main Coder Control Plane
  dashboard query
  `sum by(pod) (rate(coderd_api_requests_processed_total{...}[5m]))` returns a
  series, and `up{job="coder-metrics"}` returns `1`. So the main dashboard
  renders live data end to end (Grafana to Prometheus to coderd).
- The purely log-based `agent-boundaries` dashboard is omitted. The log panels in
  the workspaces / provisionerd / workspace-detail dashboards target datasource
  uid `loki`, which the in-cluster Loki + Promtail stack backs through
  `loki-datasource.yaml` (see "Logging" below), so they resolve and query live
  log data instead of erroring.

### Single sign-on (Keycloak OIDC)

Grafana logs in through the same Keycloak realm (`coder`) as Coder, so the demo
is one SSO. A confidential OIDC client `grafana` is registered in the realm by
`scripts/setup-grafana-oidc.py` (idempotent): standard authorization-code flow
with PKCE (S256), redirect URI
`https://grafana.usgov.coderdemo.io/login/generic_oauth`, and the same full-path
`groups` group-membership mapper the `coder` client uses. The script reads the
client secret and stores it in AWS Secrets Manager at
`usgov-coderdemo/observability/grafana-oauth` (`{"client-secret"}`); ESO syncs it
into the Kubernetes Secret `grafana-oauth`, and Grafana consumes it through the
env var `GF_AUTH_GENERIC_OAUTH_CLIENT_SECRET` (set via `grafana.envValueFrom`),
so no secret is in git.

Grafana's `[auth.generic_oauth]` (in `kube-prometheus-stack-values.yaml`) points
at the realm's auth/token/userinfo endpoints with scopes `openid email profile`
and maps Keycloak group membership to a Grafana org role:

```
role_attribute_path: contains(groups[*], '/platform') && 'Admin' || 'Viewer'
```

so Platform Engineering (group path `/platform`) administers Grafana and every
other authenticated realm user gets read-only `Viewer`. `allow_sign_up: true`
auto-provisions users on first login; `allow_assign_grafana_admin: false` keeps
the Grafana server-admin flag with the local account. The local admin login form
is intentionally left enabled (`disable_login_form: false`) as break-glass.

Verified live with a headless authorization-code login per persona: the login
page shows "Sign in with Keycloak"; `/login/generic_oauth` redirects to the realm
with `client_id=grafana` and PKCE; `austen.platform` (`/platform`) lands as org
role `Admin` (the admin-only `/api/org/users` returns 200) while `dana.dev`
(`/alpha`) lands as `Viewer` (same endpoint returns 403). Both arrive
`authLabels: ["Generic OAuth"]`, `isExternallySynced: true`.

### Admin credentials (ESO + AWS Secrets Manager)

The admin password is generated once and stored as JSON
`{"admin-user","admin-password"}` in AWS Secrets Manager at
`usgov-coderdemo/observability/grafana`. The ESO `ClusterSecretStore`
`aws-secretsmanager` syncs it into the Kubernetes Secret `grafana-admin`
(ns `monitoring`) through the ExternalSecret added to
`deploy/platform/external-secrets/secretstore-and-externalsecrets.yaml`; Grafana
reads it via `admin.existingSecret`. The ESO IAM role only allows reading
`usgov-coderdemo/*`, so this path is in policy, and no password is in git.
Verified live: ExternalSecret `grafana-admin` is `Ready=True` reason
`SecretSynced`; the Secret carries keys `admin-user` and `admin-password`; and
logging in to the public Grafana with that password succeeds.

## Logging (Loki + Promtail)

Hand-rolled manifests in `deploy/observability/` add an in-cluster log store and
collector next to the metrics stack. They are plain Kubernetes objects (not part
of the `kps` Helm release) and use ECR-mirrored images.

| Component | Live object | Storage |
|---|---|---|
| Loki | Deployment `loki` (single binary, `-target=all`), Service `loki:3100` | 10Gi gp3 PVC `loki-data` |
| Promtail | DaemonSet `promtail` (one pod per node) | host `/var/log` read-only + host `/var/lib/promtail` positions |

Images (mirrored via `scripts/images.txt` + `scripts/mirror-images.sh`):

- `docker-hub/grafana/loki:3.5.9`
- `docker-hub/grafana/promtail:3.5.9`

Loki (`loki.yaml`) runs monolithic: `auth_enabled: false`, an in-memory ring with
`replication_factor: 1`, filesystem object storage, and a tsdb shipper with
schema `v13`. The compactor enforces ~168h (7d) retention. Everything lives under
`/loki` on the PVC. The container runs as the image's nonroot user (uid 10001),
and the Deployment uses the `Recreate` strategy because the data sits on a single
ReadWriteOnce volume.

Promtail (`promtail.yaml`) runs as a DaemonSet under a ServiceAccount with a
ClusterRole granting read access to pods/nodes/services/endpoints for Kubernetes
service discovery. It tails the real container log files under `/var/log/pods`
(containerd on EKS) with the `pod` SD role, attaches `namespace`, `pod`,
`container`, `app`, and `node_name` labels, and pushes to
`http://loki.monitoring.svc:3100/loki/api/v1/push`. There is no namespace filter,
so every workload namespace is captured. Verified live: Loki's
`/loki/api/v1/labels` returns `app`, `container`, `namespace`, `node_name`,
`pod`, ...; `/loki/api/v1/label/namespace/values` lists `coder`,
`coder-workspaces`, `gitlab`, `keycloak`, `monitoring`, and `external-secrets`
(plus `ingress-nginx` and `kube-system`); and a `{namespace="coder"}`
`query_range` returns coderd JSON log lines (including `msg:"audit_log"`).

### Grafana Loki datasource (how the log panels are powered)

The kube-prometheus-stack Grafana runs the kiwigrid sidecar with
`sidecar.datasources.enabled: true`, which provisions any ConfigMap labelled
`grafana_datasource: "1"` as a datasource. `loki-datasource.yaml` is that
ConfigMap: it defines a Loki datasource with `access: proxy`, URL
`http://loki.monitoring.svc:3100`, `isDefault: false`, and uid EXACTLY `loki`. No
Helm upgrade is needed.

That uid is a contract: the generated Coder dashboards (`dashboards-coder.yaml`)
reference datasource uid `loki` on their log panels, the workspace-detail "Logs"
panel and the provisionerd / workspaces "Logs" panels. Before this datasource
existed those panels errored ("datasource loki not found"); creating it with the
matching uid resolves them. Verified live: `GET /api/datasources` lists `Loki`
(type `loki`, uid `loki`, default false); a labels call and a `{namespace="coder"}`
`query_range` through the Grafana datasource proxy
(`/api/datasources/proxy/uid/loki/...`) both return `success` with log lines; and
`POST /api/ds/query` for the workspace-detail `{namespace="coder-workspaces"}`
query returns HTTP 200 with log frames.

The workspaces / provisionerd "Logs" panels additionally filter on a `logger`
label that Promtail does not emit, so they resolve but are legitimately empty;
the workspace-detail panel that matches `coder-workspaces` pods returns live
workspace logs.

### Prometheus scraping of Loki and Promtail

`loki.yaml` and `promtail.yaml` each ship a `ServiceMonitor` (selected because
`serviceMonitorSelectorNilUsesHelmValues: false`), so Prometheus scrapes their
`/metrics`. Verified live: `up{job="loki"}` is `1` and `min(up{job="promtail"})`
is `1` (one target per node). These drive the `coder-status` dashboard's Loki and
Promtail panels below.

## coder-status dashboard adaptation

The `coder-status` dashboard (`coder-dashboard-status` in `dashboards-coder.yaml`,
uid `coder-status`) shipped an "Observability Tools" row copied from the upstream
coder/observability LGTM reference. That row probed components this demo does not
run, so most tiles were permanently red or empty. It was rebuilt to reflect this
stack, and two unrelated broken panels were repointed at metrics that exist here:

| Panel | Before | After |
|---|---|---|
| Observability Tools row | Loki Write/Read/Backend/Canary, Grafana Agent, Prometheus/Loki/Grafana-Agent config reload, Prometheus Storage, CPU, RAM | Three `up` stat panels: Prometheus (`up{job="kps-kube-prometheus-stack-prometheus"}`), Loki (`up{job="loki"}`), Promtail (`up{job="promtail"}`) |
| Workspace Builds | `coderd_provisionerd_job_timings_seconds_count` (no series here, so "No data") | `sum by (status) (coderd_workspace_latest_build_status)` |
| Postgres | `pg_up` (no postgres_exporter, so "Down") | `(sum(rate(coderd_db_tx_duration_seconds_count[5m])) > bool 0) or vector(0)` |

Verified live through Grafana `POST /api/ds/query`: all five changed panels return
HTTP 200; the three `up` panels and Postgres each evaluate to `1`, and Workspace
Builds returns `1` for `status="succeeded"`. The header comment in
`dashboards-coder.yaml` documents this adaptation.

## Ingress (HTTPS)

`deploy/observability/grafana-ingress.yaml` follows the platform pattern
(`deploy/keycloak/ingress.yaml`): `ingressClassName: nginx`, host
`grafana.usgov.coderdemo.io`, `nginx.ingress.kubernetes.io/ssl-redirect:
"false"`, no TLS block. One internet-facing NLB terminates TLS with the ACM
wildcard cert and forwards plain HTTP to ingress-nginx, which routes to
`kps-grafana:80`. The Route53 `*` alias already resolves the host. Verified
live: `https://grafana.usgov.coderdemo.io/login` returns HTTP `200` with
`ssl_verify_result=0` (valid TLS, no `-k`), and `/api/health` reports
`database: ok`, version `13.0.1+security-01`.

## Audit logging

Audit logging is a licensed Coder feature and is already entitled and enabled
(`GET /api/v2/entitlements`: `audit_log` and `connection_log` entitled +
enabled, see `30-coder-control-plane.md`). The in-product audit view is the
Coder dashboard's `/audit` page, which records who did what (logins, template
and workspace changes, user and org administration). No env var is required to
turn it on beyond the license.

For SIEM ingestion, `CODER_LOGGING_JSON=/dev/stderr` makes the coderd server
logs structured JSON on stderr, so the cluster log pipeline can ship them to a
downstream SIEM without parsing free text. The audit records themselves remain
queryable through the Coder API and `/audit` UI, and audit entries are retained
indefinitely by default (`CODER_AUDIT_LOGS_RETENTION` default `0` = keep
forever).

## Reaching Grafana

- URL: `https://grafana.usgov.coderdemo.io` (valid TLS via the ACM wildcard).
- SSO (preferred): click **Sign in with Keycloak** and authenticate against the
  `coder` realm. Platform Engineering personas get Grafana `Admin`; other realm
  users get `Viewer`. See "Single sign-on (Keycloak OIDC)".
- Break-glass: user `admin`, password the value synced into the `grafana-admin`
  Secret from ASM `usgov-coderdemo/observability/grafana`
  (`kubectl -n monitoring get secret grafana-admin -o jsonpath='{.data.admin-password}' | base64 -d`).
- Open the "Coder Control Plane" dashboard for live control-plane metrics.

## Notes and known gaps

- In-cluster logs are present: a single-binary Loki plus a Promtail DaemonSet
  back the `loki` datasource, so the log-based panels resolve. The
  `agent-boundaries` dashboard is still omitted (it is purely log-based and was
  not part of the dashboard set shipped here). The workspaces / provisionerd
  "Logs" panels filter on a `logger` label Promtail does not emit, so they are
  legitimately empty while error-free.
- kube-state-metrics is disabled, so the dashboards' pod resource limit/request
  and restart/terminated-reason panels (which depend on `kube_pod_*`) stay
  empty; container CPU/memory usage panels (cAdvisor via the kubelet) render.
- Alerting is out of scope: Alertmanager and the bundled alert rules are off.
