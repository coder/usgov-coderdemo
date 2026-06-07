# deploy/istio/observability

Istio mesh observability UIs for the GovCloud Coder demo: **Kiali** (the mesh
service-graph console with mTLS padlock badges) and the standard **Istio Grafana
dashboards**, wired into the existing in-cluster kube-prometheus-stack
(Prometheus + Grafana in ns `monitoring`). Everything is air-gapped: the only
container image is mirrored to ECR.

These manifests have been applied to the live demo cluster and verified (see
[Verification](#verification)). They add to the existing Istio install
(`deploy/istio/`) and observability stack (`deploy/observability/`) without
modifying either.

## What is here

| Path | Purpose |
|------|---------|
| `servicemonitor-istiod.yaml` | ServiceMonitor scraping istiod control-plane metrics on the `istiod` Service port `http-monitoring` (15014). Excludes the `istiod-revision-tag-default` Service so istiod is scraped once. |
| `podmonitor-istio-proxies.yaml` | PodMonitor scraping every Istio proxy's merged telemetry at `:15020/stats/prometheus` (the ingress gateway now; app sidecars once injected). Official Istio "Prometheus with Operator" relabeling. |
| `dashboards-istio.yaml` | The five standard Istio dashboards as Grafana ConfigMaps (`grafana_dashboard: "1"`), sourced from the istio `release-1.30` tree. |
| `kiali-server-values.yaml` | Helm values for the `kiali-server` chart 2.26.0 (image overridden to the ECR mirror, Prometheus/Grafana URLs, anonymous auth, web_root `/kiali`). |
| `kiali.yaml` | GENERATED rendered Kiali server manifest (from the chart + values). Server only, no operator. |
| `virtualservice-kiali.yaml` | Routes `kiali.usgov.coderdemo.io` through `istio-system/public-gateway` to the `kiali` Service (20001). Manifest only; no DNS change. |

Apply everything with `scripts/setup-istio-observability.sh`
(`--verify` runs post-apply checks; `--render-kiali` regenerates `kiali.yaml`).

## Versions and air gap

- **Kiali v2.26.0** (chart `kiali-server` 2.26.0). v2.26 is the Kiali line Istio
  1.30 certifies: the istio-1.30.1 Kiali addon ships `quay.io/kiali/kiali:v2.26`
  and labels it v2.26.0.
- Image mirrored to ECR via `scripts/images.txt` + `scripts/mirror-images.sh`:
  `430737322961.dkr.ecr.us-gov-west-1.amazonaws.com/quay/kiali/kiali:v2.26.0`
  (digest `sha256:59cce98a9811ce53ff3da771225d1df00f0ca4ae0819311291ae7316349a13e9`).
- Dashboards are plain JSON ConfigMaps; no image needed. Helm renders Kiali
  client-side, so the cluster only ever pulls the ECR image.

## Metrics path

```
istiod        :15014/metrics            --[ServiceMonitor istio-component-monitor]--+
istio-proxy   :15020/stats/prometheus   --[PodMonitor envoy-stats-monitor]----------+--> kps Prometheus
                                                                                     |        (ns monitoring)
                                                                                     v
                                                              Istio Grafana dashboards + Kiali
```

- The kps Prometheus operator selects ServiceMonitors/PodMonitors cluster-wide
  (`*SelectorNilUsesHelmValues: false` with empty selectors), so the `release:
  kps` label on these monitors is belt-and-suspenders, matching
  `deploy/observability/coder-metrics.yaml`.
- The proxy PodMonitor is annotation-driven: each proxy pod carries
  `prometheus.io/scrape=true`, `prometheus.io/path=/stats/prometheus`,
  `prometheus.io/port=15020`, and the relabeling rewrites the scrape target to
  the merged port. This is why app sidecars are picked up automatically once
  their namespaces are injected, with no manifest change.
- Kiali reads Prometheus at
  `http://kps-kube-prometheus-stack-prometheus.monitoring.svc:9090` and links to
  Grafana at `http://kps-grafana.monitoring.svc:80` (browser links use
  `https://grafana.usgov.coderdemo.io`).

## Reaching Kiali

- **Now (no DNS change):** port-forward.
  ```sh
  kubectl -n istio-system port-forward svc/kiali 20001:20001
  # open http://localhost:20001/kiali
  ```
- **Through the gateway:** the VirtualService is live and `kiali.usgov.coderdemo.io`
  already matches the gateway's `*.usgov.coderdemo.io` server. Once the
  orchestrator adds an additive Route53 record pointing
  `kiali.usgov.coderdemo.io` at the Istio gateway NLB, Kiali is reachable at
  **https://kiali.usgov.coderdemo.io/kiali**. Validate routing before the DNS cut
  with `--resolve` against a gateway NLB public IP:
  ```sh
  GIP=$(aws ec2 describe-network-interfaces \
    --filters "Name=description,Values=ELB net/k8s-istiosys-istioing-bf7bdca8c8/*" \
    --query 'NetworkInterfaces[0].Association.PublicIp' --output text)
  curl -sSk --resolve kiali.usgov.coderdemo.io:443:$GIP \
    https://kiali.usgov.coderdemo.io/kiali/   # expect HTTP 200
  ```

## Auth

Kiali uses `auth.strategy: anonymous` for the demo. **Production follow-up:**
switch to `openid` against the same Keycloak realm (`coder`) that fronts Grafana
and Coder (see `scripts/setup-grafana-oidc.py` for the pattern). This is not a
demo blocker and is intentionally deferred.

## What to show in the demo

- **Istio Control Plane dashboard** (Grafana): works immediately. It renders
  istiod data (`pilot_xds`, proxy convergence, push counts) the moment
  Prometheus scrapes istiod.
- **Kiali mesh graph**: the infrastructure view already shows istiod, the ingress
  gateway, Prometheus, Grafana, and Kiali. The traffic graph shows live edges for
  whatever flows through the gateway.
- **mTLS padlocks**: Kiali draws a padlock on edges carrying sidecar-to-sidecar
  mTLS, and the Istio Service/Workload dashboards include `(🔐mTLS)` legend
  series. These appear once application namespaces are **sidecar-injected** and
  generate traffic. With no injected namespaces yet, there is no
  sidecar-to-sidecar traffic, so the Mesh/Service/Workload dashboards and the
  padlocked Kiali edges are sparse by design. This is mesh traffic, not AI
  traffic, so the placeholder-Anthropic / sparse-AI-traffic situation elsewhere
  in the demo is irrelevant here.

## Verification

Captured against the live cluster after apply:

- Prometheus targets `up=1`: istiod (`:15014`) and both ingress gateway proxies
  (`:15020`). `istio_requests_total` is populated from the gateway
  (`source_workload=istio-ingressgateway`); istiod metrics (`pilot_xds`,
  `pilot_proxy_convergence_time_bucket`, `galley_validation_passed`) are present.
- Grafana lists all five Istio dashboards; the Control Plane dashboard's
  `pilot_xds` query returns data through Grafana's Prometheus datasource.
- Kiali v2.26.0 pod is `Running`; `/kiali/api/istio/status` reports istiod,
  istio-ingressgateway, Prometheus, Grafana, and custom dashboards all `Healthy`;
  the graph API returns the mesh.
- `https://kiali.usgov.coderdemo.io/kiali/` returns HTTP 200 through every
  gateway NLB IP (validated with `--resolve`); `/` 302-redirects to the `https`
  `/kiali/` URL.
