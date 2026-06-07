# 55. Observability (as-built)

In-boundary, in-cluster metrics and dashboards for the GovCloud demo: the
`prometheus-community/kube-prometheus-stack` Helm release `kps` (Prometheus +
Grafana + the Prometheus operator) in the `monitoring` namespace, scraping the
Coder control plane's Prometheus metrics and rendering Coder's prebuilt Grafana
dashboards with live data at `https://grafana.usgov.coderdemo.io`. Grafana signs
in through the same Keycloak realm (`coder`) as the rest of the stack, so the
demo is one SSO. Coder audit logging is entitled and on; structured JSON server
logs make it SIEM-ready.

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
- The purely log-based `agent-boundaries` dashboard is omitted, and a few log
  panels inside the workspaces / provisionerd / workspace-detail dashboards show
  no data, because this stack ships metrics only (no Loki). Their Prometheus
  panels render live.

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
with `client_id=grafana` and PKCE; `pat.platform` (`/platform`) lands as org
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

- Metrics only: no Loki/logs datasource, so log-based panels and the
  `agent-boundaries` dashboard are inactive by design.
- kube-state-metrics is disabled, so the dashboards' pod resource limit/request
  and restart/terminated-reason panels (which depend on `kube_pod_*`) stay
  empty; container CPU/memory usage panels (cAdvisor via the kubelet) render.
- Alerting is out of scope: Alertmanager and the bundled alert rules are off.
