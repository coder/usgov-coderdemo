# 25. Istio service mesh (as-built)

The live edge and east-west security layer for the GovCloud demo: an Istio
service mesh (control plane `istiod`, an ingress gateway on its own NLB, and
sidecar proxies in the platform namespaces). The Istio ingress gateway is now
the single L7 hop in front of every public host, one `Gateway` plus per-host
`VirtualService` objects route `dev`/workspace apps to Coder and `auth`,
`gitlab`, `grafana`, `kiali`, and the GitLab Container Registry (`registry`) to
their backends, and mesh-wide STRICT mutual TLS
encrypts traffic between the meshed control-plane workloads. The gateway also
fixes the Keycloak Account Console cookie bug by presenting a trustworthy
`x-forwarded-proto: https` to every backend. Kiali is the mesh console, behind
Keycloak SSO.

This replaces ingress-nginx as the live L7 edge. nginx still runs but is out of
the DNS path, held only for rollback; its decommission is tracked in issue #34.
Istio adoption is PR #31 / issue #30.

Source of truth for the manifests and the reproduce/verify steps:
`deploy/istio/` and `deploy/istio/README.md` (control plane, gateway, security),
`deploy/istio/observability/` and its `README.md` (Kiali + Istio dashboards),
and `deploy/istio/namespace-injection.md` (which namespaces join the mesh).

## Verification method

Mutating steps (`istioctl install`, `kubectl apply`, namespace labeling and
pod rollouts, the DNS cutover, and the PERMISSIVE-to-STRICT flip) were performed
during this build against `./kubeconfig` and the `us-gov-west-1` account
`430737322961`. Live checks here used read-only `istioctl proxy-status`,
`kubectl get`, and authenticated/anonymous `curl` against the public hosts.
Always target the demo hosts explicitly (`https://dev.usgov.coderdemo.io` and
friends), never the ambient `CODER_URL`.

## Version and air gap

- Istio **1.30.1**. Istio 1.30 is the only currently supported release line that
  certifies Kubernetes 1.36 (1.30 supports 1.32 to 1.36; 1.29 stops at 1.35), so
  the version is locked to the cluster's k8s 1.36.
- Air-gapped: every image is pulled from the ECR mirror, no internet egress. The
  `docker.io/istio/*` source maps through the existing `docker-hub/` prefix, so
  no `gcr.io` mapping change was needed. Mirrored via `scripts/images.txt` +
  `scripts/mirror-images.sh`:
  - `430737322961.dkr.ecr.us-gov-west-1.amazonaws.com/docker-hub/istio/pilot:1.30.1` (istiod)
  - `430737322961.dkr.ecr.us-gov-west-1.amazonaws.com/docker-hub/istio/proxyv2:1.30.1` (ingress gateway + sidecars)
  - `430737322961.dkr.ecr.us-gov-west-1.amazonaws.com/docker-hub/istio/install-cni:1.30.1` (mirrored for a later CNI hardening pass; not enabled yet)
- `istioctl` 1.30.1 is installed in this workspace at `~/.local/bin/istioctl`,
  matching the control-plane version. Verified live: `istioctl version` reports
  client, control plane, and data plane all `1.30.1`.

## Control plane install (istioctl + IstioOperator)

Installed with `istioctl install -f deploy/istio/istio-operator.yaml`. The
file-based `IstioOperator` API is still the supported install input in Istio
1.30; only the in-cluster operator controller was removed. The
`IstioOperator` (`profile: default`, name `usgov-coderdemo`, ns `istio-system`)
pins `hub`/`tag` at the ECR mirror and sets:

- `meshConfig.accessLogFile: /dev/stdout`, so Envoy and istiod access logs land
  on stdout and the existing Promtail DaemonSet ships them to Loki like every
  other pod.
- `meshConfig.outboundTrafficPolicy.mode: ALLOW_ANY`, keeping egress open during
  rollout. Tightening to `REGISTRY_ONLY` is a documented future hardening step,
  not part of this adoption.
- `defaultConfig.holdApplicationUntilProxyStarts: true`, so an app container does
  not start before its sidecar is ready and is never briefly unable to reach the
  mesh.
- `pilot` HPA 1 to 3; the ingress gateway HPA 2 to 4.
- Istio CNI intentionally disabled for the first install; sidecar networking is
  set up by the per-pod `istio-init` container on standard EKS nodes.
  `install-cni` is mirrored so the CNI DaemonSet can be enabled later without a
  new mirror pass.

Live: `istio-system` runs `istiod` (1/1), two `istio-ingressgateway` replicas
(1/1), and `kiali` (1/1). `istioctl proxy-status` lists seven proxies all on
`1.30.1` and SYNCED: the two gateway pods plus sidecars in `coder` (control
plane + both provisioners), `gitlab`, and `keycloak`.

## Ingress gateway, NLB, and TLS

The ingress gateway Service is `type: LoadBalancer` with its OWN internet-facing
NLB, provisioned by the AWS Load Balancer Controller (the same controller that
fronts nginx). TLS is terminated at the NLB with the shared ACM wildcard cert
(`...7f4fc566...`), exactly as the nginx edge did. The gateway itself serves only
plain HTTP, so it is the single L7 hop:

| NLB / Service port | Gateway container port | Role |
|---|---|---|
| `15021` | `15021` | gateway status / health |
| `80` | `8080` | plain HTTP |
| `443` (TLS terminated at NLB) | `8443` | decrypted HTTP |

Both the `80` listener and the decrypted `443` listener reach the gateway's
plain-HTTP servers (container ports 8080 and 8443), so a request routes the same
way regardless of which listener delivered it. 443 maps to a distinct container
port (8443) only to avoid duplicate `containerPort` generation on the gateway
Deployment; there is no second TLS hop. Key Service annotations (set in the
`IstioOperator`): `aws-load-balancer-type: external`,
`aws-load-balancer-scheme: internet-facing`,
`aws-load-balancer-nlb-target-type: ip`,
`aws-load-balancer-backend-protocol: tcp`,
`aws-load-balancer-ssl-cert: <ACM ARN ...7f4fc566...>`,
`aws-load-balancer-ssl-ports: "443"`, and cross-zone load balancing enabled.

This is "option A" from issue #30: TLS at the NLB, plain HTTP at the gateway. The
consequence (the L4 NLB cannot tell the gateway the real client scheme) is what
the per-host `x-forwarded-proto` normalization below handles.

## L7 routing: one Gateway, per-host VirtualServices

A single `Gateway` (`public-gateway`, ns `istio-system`) selects
`istio: ingressgateway` and declares two HTTP servers, port 80 (`http`) and port
443 (`https-decrypted`), both `protocol: HTTP` (no TLS block, since TLS lives at
the NLB). Both servers list the same hosts: `dev`, `auth`, `gitlab`, `grafana`,
and the Coder wildcard `*.usgov.coderdemo.io`.

Per-host `VirtualService` objects bind to that Gateway and route each hostname to
its in-cluster Service. Every one sets `x-forwarded-proto: https` with header
`set` (not `add`), so it overwrites any client-supplied value and a forged header
from a direct caller is replaced:

| Host | VirtualService (ns) | Backend Service |
|---|---|---|
| `*.usgov.coderdemo.io` (dev + workspace apps) | `coder` (`coder`) | `coder.coder.svc:80` |
| `auth.usgov.coderdemo.io` | `keycloak` (`keycloak`) | `keycloak.keycloak.svc:8080` |
| `gitlab.usgov.coderdemo.io` | `gitlab` (`gitlab`) | `gitlab.gitlab.svc:80` |
| `grafana.usgov.coderdemo.io` | `grafana` (`monitoring`) | `kps-grafana.monitoring.svc:80` |
| `kiali.usgov.coderdemo.io` | `kiali` (`istio-system`) | `kiali.istio-system.svc:20001` |
| `registry.usgov.coderdemo.io` (GitLab Container Registry) | `gitlab-registry` (`gitlab`) | `gitlab.gitlab.svc:5050` |

The `registry` host is the GitLab Container Registry route added with the GitLab
CI work (PR #36, `deploy/gitlab/virtualservice-registry.yaml`). It has no
dedicated `Gateway` host entry and no dedicated Route53 record; it resolves
through the `*.usgov.coderdemo.io` wildcard DNS to the gateway NLB and is served
by the Gateway's wildcard server, where the exact-host `gitlab-registry`
VirtualService wins over the Coder wildcard route and lands on the registry
listener `gitlab.gitlab.svc:5050`. Verified live 2026-06-08: an anonymous
`GET https://registry.usgov.coderdemo.io/v2/` returns `401` (the registry auth
challenge) over valid TLS.

Routing precedence: the wildcard server carries Coder's dashboard and the
workspace-app subdomains, while the exact-host VirtualServices (`auth`, `gitlab`,
`grafana`, `kiali`, `registry`) win over the wildcard and land on their own
backends. The
Coder and GitLab routes set no route timeout (Envoy applies none), so long-lived
websockets, streaming terminals, CI log streams, and git-over-HTTP stay open, and
Envoy imposes no fixed request body cap, which covers large uploads and registry
pushes.

## The Keycloak Account Console cookie fix

This is the headline reason the gateway normalizes scheme. Under the L4 NLB,
TLS terminated at the NLB and plain HTTP was forwarded, so Keycloak saw
`X-Forwarded-Proto: http` and issued its session cookies (`AUTH_SESSION_ID`,
`KC_RESTART`, `KC_AUTH_SESSION_HASH`) without `Secure` or `SameSite=None`. The
Account Console's silent-SSO iframe requires `SameSite=None; Secure` cookies, so
the browser dropped them and the Console broke.

The `keycloak` VirtualService now deterministically presents
`x-forwarded-proto: https`. Combined with the pod's existing
`KC_PROXY_HEADERS=xforwarded`, Keycloak treats the request as secure and sets
`Secure; SameSite=None` on its session cookies. `KC_HOSTNAME=https://auth.usgov.coderdemo.io`
still pins the issuer and redirect URLs; the two settings are independent and
both required.

Proven live: a `curl -D -` against the realm authorization endpoint through the
gateway returns `AUTH_SESSION_ID`, `KC_AUTH_SESSION_HASH`, and `KC_RESTART`, each
carrying `Secure` and `SameSite=None`, and the Account Console loads.

## mTLS: PERMISSIVE rollout to mesh-wide STRICT

Mutual TLS was rolled out PERMISSIVE first, then flipped to mesh-wide STRICT. A
mesh-wide `PeerAuthentication` named `default` in `istio-system` is the single
policy that was flipped: PERMISSIVE lets a meshed sidecar accept both mTLS and
plain text (so namespace-by-namespace injection is safe mid-rollout), and STRICT
requires sidecar-to-sidecar traffic to be mTLS. STRICT governs only INBOUND
traffic to injected workloads; it does not affect non-injected namespaces,
kubelet probes (handled by Istio probe rewrite), or mesh-external egress.

Live: the mesh-wide `default` PeerAuthentication reads `STRICT`. The build
validated 100% mTLS through the gateway, and STRICT was proven by showing that a
plain-text connection from a non-meshed pod to a meshed Service is refused
(connection reset) while the gateway mTLS path returns 200, all pods stay Ready,
and Prometheus keeps scraping Coder metrics.

### Injected (meshed) namespaces

Sidecar injection is opt-in per namespace via the `istio-injection=enabled` label
(a pod gets a sidecar only after the namespace is labeled AND the pod is
recreated). Injected, in lowest-blast-radius order:

| Namespace | Meshed workloads | Validated after restart |
|---|---|---|
| `keycloak` | `keycloak` (single pod) | login flow, Account Console cookies still `Secure; SameSite=None`, probes green |
| `coder` | control plane + both provisioners (`coder-provisioner-alpha`, `coder-provisioner-bravo`) | dashboard, OIDC login, a workspace build, `coder-metrics` still scraped |
| `gitlab` | `gitlab-0` | git over HTTPS, a CI job, web terminal, registry push |

### Intentionally not meshed

| Namespace | Why excluded |
|---|---|
| `coder-workspaces` | Highest risk. Workspace pods are created dynamically and run the Coder agent (DERP/tunnel networking, many outbound connections, web terminals); sidecar iptables capture can break agent connectivity. Coder Boundary runs in-process, and workspace-to-Coder traffic transits the ingress gateway (the public URL), not direct pod-to-pod, so excluding this namespace leaves no unencrypted east-west gap that STRICT would otherwise cover. A single-workspace injection pilot is a later, separate experiment. |
| `gitlab-runner` | CI job pods are short-lived and would race an injected sidecar's lifecycle; under STRICT a plain-text hop from a non-meshed pod to a meshed Service is refused, so the runner and its job pods reach GitLab and Coder over their external URLs (`https://gitlab.usgov.coderdemo.io`, `https://dev.usgov.coderdemo.io`) through the gateway, which does the mTLS hop to the meshed backends. Labeled `istio-injection=disabled` (`deploy/gitlab-runner/namespace.yaml`). |
| `monitoring` | Owned by the observability workstream; injecting it needs mesh-aware scraping under STRICT and is a coordinated later step. Leaving it out keeps Prometheus scraping over plain text during the core rollout. |
| `external-secrets` | ESO controllers talk to the k8s API and AWS (IRSA) and run admission webhooks; no in-mesh east-west value, real webhook risk. |
| `kube-system`, `kube-node-lease`, `kube-public`, `default`, `ingress-nginx` | System namespaces and cluster add-ons; never injected. |
| `istio-system` | The control plane and gateway are managed by the `IstioOperator`, not namespace injection. |

### Carve-outs (so STRICT does not break anything)

- **RDS is mesh-external.** A `ServiceEntry` (`rds-postgres`, MESH_EXTERNAL, DNS)
  registers the RDS endpoint, and a paired `DestinationRule` sets TLS mode
  `DISABLE` so the sidecar passes the app-originated TLS straight through (the
  apps already speak `sslmode=require` to an instance with `rds.force_ssl=1`; any
  other mode would double-wrap the libpq/JDBC handshake). Only `coder` and
  `keycloak` use RDS; `gitlab` uses its embedded Postgres. STRICT does not apply
  here because this is mesh-external egress, not sidecar-to-sidecar traffic.
- **Per-workload PERMISSIVE ports.** Two workload `PeerAuthentication` objects
  keep specific ports PERMISSIVE so out-of-mesh callers keep working, while the
  rest of each workload stays STRICT:
  - `coder-metrics` (ns `coder`, selector `app.kubernetes.io/name: coder`) keeps
    the Coder metrics port **2112** PERMISSIVE so the out-of-mesh Prometheus
    keeps scraping the `coder-metrics` ServiceMonitor without joining the mesh.
  - `keycloak-management` (ns `keycloak`) keeps the Keycloak management port
    **9000** PERMISSIVE for kubelet startup/liveness/readiness probes (defense in
    depth on top of Istio probe rewrite).
  Both objects set the workload `mtls.mode` to `STRICT` with a `portLevelMtls`
  carve-out, NOT a workload-wide PERMISSIVE (which would silently exempt the
  entire workload from STRICT). Neither port is exposed by a Service, so this
  does not widen the external surface. Live: both read `STRICT` with the port
  carve-out.

## Production DNS cutover

All Route53 ALIAS records now point at the gateway NLB: `*`, `auth`, `dev`,
`gitlab`, `grafana`, and `kiali` under `usgov.coderdemo.io`. ingress-nginx is no
longer in any DNS path; it is kept only for rollback. Live: each public host
resolves to the gateway NLB's public IPs, and requests succeed with valid TLS
(ACM wildcard). Decommissioning nginx is tracked in issue #34.

## Kiali (mesh console)

Kiali **v2.26.0** (the line Istio 1.30 certifies, ECR-mirrored at
`.../quay/kiali/kiali:v2.26.0`) is the mesh service-graph console with per-edge
mTLS padlock badges, served at `https://kiali.usgov.coderdemo.io/kiali` through
the shared gateway VirtualService. It is the Kiali server only (no operator),
kept out of the mesh data plane (`sidecar.istio.io/inject: "false"`).

Kiali is fronted by Keycloak OpenID Connect SSO in the same realm (`coder`) as
the rest of the stack; **anonymous access is disabled**, so unauthenticated users
are redirected to Keycloak. Because this EKS API server does not trust Keycloak
as an OIDC issuer, per-user Kubernetes RBAC is unavailable, so the install uses
`auth.openid.disable_rbac: true` (any authenticated realm user may view the mesh,
Kiali reads the cluster with its own ServiceAccount) paired with
`deployment.view_only_mode: true` so the console is strictly read-only and nobody
can mutate Istio config through the Kiali wizards. The confidential OIDC client
`kiali` and its ESO-synced secret are described in
[40-identity-keycloak.md](40-identity-keycloak.md); the Istio Grafana dashboards
wired alongside Kiali are covered in [55-observability.md](55-observability.md).
Live: the Kiali host returns HTTP 200 (login page, valid TLS) and the anonymous
API returns HTTP 401.

## Rollback

Instant rollback to the nginx edge is two steps: repoint the Route53 records back
to the nginx NLB, and re-apply `security/peerauthentication-permissive.yaml` (the
same name/namespace as the STRICT policy, so it flips the mesh back to PERMISSIVE
in place). Sidecars can then accept plain text again while nginx serves traffic.
nginx is intentionally still running for exactly this reason.

## Verification (live checks)

- `istioctl version`: client, control plane, data plane all `1.30.1`.
- `istioctl proxy-status`: 7 proxies SYNCED (2 gateway, coder, 2 provisioners,
  gitlab, keycloak).
- `kubectl -n istio-system get svc istio-ingressgateway`: `LoadBalancer` with the
  gateway NLB hostname; ports `15021`, `80`, `443`.
- `kubectl get gateway,virtualservice -A`: one `public-gateway` and the six
  per-host VirtualServices above (including `gitlab-registry`).
- `kubectl get peerauthentication -A`: `default` STRICT (istio-system),
  `coder-metrics` STRICT (coder), `keycloak-management` STRICT (keycloak).
- `kubectl get serviceentry,destinationrule -A`: `rds-postgres` MESH_EXTERNAL +
  its DestinationRule.
- `kubectl get ns -L istio-injection`: `enabled` on `coder`, `gitlab`,
  `keycloak`; blank on `coder-workspaces`, `monitoring`, `external-secrets`;
  `disabled` on `gitlab-runner`.
- Keycloak authorize endpoint through the gateway: session cookies carry
  `Secure; SameSite=None`.
- Public hosts resolve to the gateway NLB and serve valid TLS; Kiali host returns
  200, its anonymous API 401.

Re-verified live 2026-06-08: `istioctl version` reports `1.30.1` for client,
control plane, and data plane (7 proxies); `istioctl proxy-status` shows all 7
SYNCED; `default`, `coder-metrics`, and `keycloak-management` PeerAuthentications
read `STRICT`; the `rds-postgres` ServiceEntry/DestinationRule are present; six
VirtualServices bind `public-gateway`; every public host resolves to the gateway
NLB IPs and all mesh pods are Ready.

## Notes and known gaps

- ingress-nginx still runs but is out of every DNS path, kept only for rollback;
  decommission is issue #34.
- `coder-workspaces` is deliberately unmeshed; namespace-wide workspace injection
  is a future, separately validated experiment, not part of this STRICT cutover.
- `monitoring` is not yet injected; doing so (with mesh-aware scraping) is owned
  by the observability workstream.
- `outboundTrafficPolicy` is `ALLOW_ANY` and Istio CNI is disabled; tightening to
  `REGISTRY_ONLY` and enabling the CNI DaemonSet are documented future hardening
  steps, not part of this adoption.
