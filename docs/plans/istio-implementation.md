# Plan: Istio service mesh adoption (mTLS + ingress rationalization)

Status: PLAN plus PREP. Design only for the live cluster. No Istio is installed
and no ingress, DNS, or PeerAuthentication change has been applied. The only
side effects produced while writing this plan were read-only cluster inspection
and mirroring three Istio images into ECR (additive; pull-only artifacts). The
orchestrator runs every live mutation below in the sequenced order given here.

Companion: issue [#30](https://github.com/coder/usgov-coderdemo/issues/30).
Apply-ready manifests: [`deploy/istio/`](../../deploy/istio/README.md).

Facts grounded in read-only checks run on 2026-06-07 against cluster
`usgov-coderdemo` (account `<AWS_ACCOUNT_ID>`, `aws-us-gov`, `us-gov-west-1`):

| Fact | Value | Source |
|---|---|---|
| Kubernetes | `v1.36.1-eks-0247562` | live `kubectl version` |
| istio-system | absent (clean slate) | live `kubectl get ns` |
| Namespaces | `coder`, `coder-workspaces`, `keycloak`, `gitlab`, `monitoring`, `external-secrets`, `ingress-nginx`, plus system ns | live `kubectl get ns` |
| Injection labels | none set on any namespace | live `kubectl get ns -L istio-injection` |
| Coder Service | `coder.coder.svc:80` | live `kubectl -n coder get svc` |
| Keycloak Service | `keycloak.keycloak.svc:8080` (mgmt 9000 not in Service) | live `kubectl -n keycloak get svc` |
| GitLab Service | `gitlab.gitlab.svc:80` | live `kubectl -n gitlab get svc` |
| Grafana Service | `kps-grafana.monitoring.svc:80` | live `kubectl -n monitoring get svc` |
| Ingress NLB | `ingress-nginx-controller` LoadBalancer -> `k8s-ingressn-ingressn-e16fe3cd33-c002102481951644.elb.us-gov-west-1.amazonaws.com` | live `kubectl -n ingress-nginx get svc` |
| RDS endpoint | `usgov-coderdemo-pg.crhk7w9eko3r.us-gov-west-1.rds.amazonaws.com:5432`, `sslmode=require` | live Keycloak `KC_DB_URL` |
| Route53 zone | `Z06701704WFETYIRU5C8` (`usgov.coderdemo.io`) | `versions.lock.yaml` |

## 1. Locked decisions (with evidence)

### 1.1 Istio version: 1.30.1 (hard gating item, resolved)

The cluster runs Kubernetes 1.36. The newest supported Istio line that certifies
1.36 is **1.30**, and the current patch is **1.30.1**.

- Istio 1.30 platform support: Kubernetes 1.32, 1.33, 1.34, 1.35, 1.36
  (https://istio.io/latest/docs/setup/platform-setup/ and the 1.30 announcement,
  "Istio 1.30.0 is officially supported on Kubernetes versions 1.32 to 1.36").
- Istio 1.29: Kubernetes 1.31 to 1.35 (does not cover 1.36).
- Istio 1.28: Kubernetes 1.29 to 1.34.

So 1.30 is not merely the newest line; it is the ONLY currently supported line
that includes 1.36. Pin 1.30.1 (latest patch as of 2026-06-07). Run
`istioctl x precheck` before install; the kubeconfig client is already 1.36.

Risk note: if a future cluster upgrade outruns Istio again, this same gating
check repeats. There is no released Istio that supports a hypothetical 1.37 yet,
so do not upgrade EKS past 1.36 until Istio 1.31+ certifies it.

### 1.2 Install method: istioctl with an IstioOperator config

Recommend **istioctl** driven by [`deploy/istio/istio-operator.yaml`](../../deploy/istio/istio-operator.yaml).
GitOps (Argo CD) is not live here yet, so istioctl gives the cleanest first
install on a new k8s minor: `istioctl x precheck`, `istioctl install`, and
`istioctl verify-install`. The file-based IstioOperator API is still the
supported install input in 1.30 (only the in-cluster operator controller was
removed). If the GitOps control plane (issues #6 to #12) lands first, the same
settings port to the official Helm charts (`base`, `istiod`, `gateway`) one for
one; the hub/tag and gateway Service annotations are identical.

`istioctl` 1.30.1 is not yet present in the workspace. Download it on a connected
host and copy the binary in (air gap); it must match the control-plane version.

### 1.3 Ingress: keep NLB L4 + ACM, replace nginx with the Istio gateway (option A)

The NLB keeps terminating TLS with the ACM cert and forwards decrypted HTTP to
the Istio ingress gateway, which becomes the single L7 hop in place of
ingress-nginx. The gateway Service carries the same AWS LB annotations the
nginx controller Service carries today (confirmed live), so the AWS Load Balancer
Controller provisions an equivalent internet-facing NLB. Both the 80 and 443
Service ports target the gateway pod's plain-HTTP listener (8080), mirroring the
nginx `targetPorts {http: http, https: http}` trick.

Per-host expression:

| Host | Gateway server | VirtualService | Backend |
|------|----------------|----------------|---------|
| `dev.usgov.coderdemo.io` + `*.usgov.coderdemo.io` | `public-gateway` :80 HTTP | `coder` (coder ns) | `coder.coder.svc:80` |
| `auth.usgov.coderdemo.io` | same | `keycloak` (keycloak ns) | `keycloak.keycloak.svc:8080` |
| `gitlab.usgov.coderdemo.io` | same | `gitlab` (gitlab ns) | `gitlab.gitlab.svc:80` |
| `grafana.usgov.coderdemo.io` | same | `grafana` (monitoring ns) | `kps-grafana.monitoring.svc:80` |

One `Gateway` lists all hosts including the wildcard; exact-host VirtualServices
win over the wildcard, so auth/gitlab/grafana never fall into the Coder route.

Host-by-host cutover is done with DNS, because an L4 NLB cannot route by Host
header and therefore cannot be split per host at the load balancer. Stand up the
gateway's own NLB alongside nginx, then move one hostname at a time in Route53
(details in Phase 4). End state is still exactly one NLB; there are transiently
two during cutover.

### 1.4 Keycloak cookie fix (X-Forwarded-Proto: https)

The gateway forces `x-forwarded-proto: https` toward Keycloak via
[`deploy/istio/gateway/virtualservice-keycloak.yaml`](../../deploy/istio/gateway/virtualservice-keycloak.yaml)
(`http[].headers.request.set`). `set` overwrites, so a value forged by a direct
caller is replaced. Combined with the pod's existing `KC_PROXY_HEADERS=xforwarded`,
Keycloak treats the request as secure and emits `AUTH_SESSION_ID` / `KC_RESTART`
with `Secure; SameSite=None`, which is what the Account Console silent-SSO iframe
needs. `KC_HOSTNAME=https://auth.usgov.coderdemo.io` stays (issuer/redirect URL
pinning); the two settings are independent and both required.

Determinism caveat: because the L4 NLB collapses its 80 and 443 listeners into
one plain-HTTP stream to the gateway, the gateway cannot distinguish an original
http request from an https one. Forcing https is correct here since the only real
client entry is the 443 NLB listener; enforcing an http-to-https redirect would
require separate NLB listener handling and is out of scope.

A gateway-wide alternative,
[`deploy/istio/gateway/envoyfilter-xforwarded-proto.yaml`](../../deploy/istio/gateway/envoyfilter-xforwarded-proto.yaml)
(`scheme_header_transformation.scheme_to_overwrite: https`), is provided but not
applied by default; the per-host header set is the primary, more targeted fix.

Acceptance: `curl -D - https://auth.usgov.coderdemo.io/realms/coder/...` through
the gateway shows session cookies with `Secure` and `SameSite=None`, and the
Account Console loads.

### 1.5 mTLS: PERMISSIVE first, then mesh-wide STRICT, with enumerated exceptions

Apply `peerauthentication-permissive.yaml` before any injection, inject
namespaces incrementally, then replace it with `peerauthentication-strict.yaml`.

Required exceptions:

| Exception | Treatment |
|-----------|-----------|
| RDS PostgreSQL (mesh-external, app TLS `rds.force_ssl=1`/`sslmode=require`) | `ServiceEntry` + `DestinationRule` TLS mode DISABLE (sidecar passes app-originated TLS through). Not governed by PeerAuthentication. |
| Kubelet health/readiness probes | Istio probe rewrite (default on) reroutes kubelet HTTP probes through pilot-agent:15020 over plain text. Keycloak mgmt port 9000 also covered; optional port-level PERMISSIVE in `peerauthentication-keycloak-mgmt.yaml`. |
| Non-injected namespaces | `kube-system`, `kube-node-lease`, `kube-public`, `default`, `external-secrets`, and initially `monitoring`. STRICT only governs injected workloads, so these keep working; any in-mesh caller reaching them does so over plain text, which PERMISSIVE-by-omission allows. |
| Prometheus scraping under STRICT | `monitoring` stays non-injected during the core rollout so scraping continues over plain text. Mesh-aware scraping (Istio metrics merge / ServiceMonitor changes) is owned by the observability workstream as a later coordinated step. |
| Coder workspace pods (`coder-workspaces`) | HIGHEST RISK. Created dynamically by Coder; run the agent's tunnel networking. Recommend EXCLUDE from injection initially. Workspace-to-Coder traffic transits the ingress gateway, so exclusion leaves no east-west gap STRICT would otherwise close. See `deploy/istio/namespace-injection.md`. |
| GitLab omnibus | Most ports are intra-pod on localhost (not intercepted). Inject LAST and validate git-over-http, websockets, registry. |

### 1.6 Certificates

ACM stays at the NLB (FIPS-validated edge termination; no public server cert in
the cluster). istiod is the mesh CA and issues/rotates per-workload SPIFFE mTLS
certs automatically; these are internal and unrelated to the ACM cert.
cert-manager is NOT required for option A. It would only enter if option C
(gateway-terminated TLS) were chosen or if a compliance rule required backing the
mesh CA with an external intermediate (cert-manager `istio-csr`); both deferred.
Document the mesh trust domain and istiod root-rotation runbook before STRICT.

## 2. Phased, reversible rollout

Each phase is independently revertible. Do not start a phase until the previous
phase's validation passes. Commands assume:

```sh
. ~/.config/usgov-coderdemo/env
export KUBECONFIG=/home/coder/demoenv-workspace/usgov-coderdemo/kubeconfig
```

### Phase 0: Prep and approvals

- Approve the scope change (STATUS.md lists Istio under "Out of scope (demo)").
- Install `istioctl` 1.30.1 on the operator host (air-gapped copy).
- `istioctl x precheck` against the cluster; fix any error before proceeding.
- Confirm ELB/NLB quota headroom for a second internet-facing NLB
  (`scripts/govcloud-quota-check.sh`).
- Validation: `istioctl x precheck` reports no errors.
- Rollback: none (no cluster change).

### Phase 1: Mirror images and install the control plane (PERMISSIVE)

Images are already mirrored (this workstream). Verify, then install.

```sh
aws ecr describe-images --repository-name docker-hub/istio/pilot   --image-ids imageTag=1.30.1
aws ecr describe-images --repository-name docker-hub/istio/proxyv2 --image-ids imageTag=1.30.1
istioctl install -f deploy/istio/istio-operator.yaml
kubectl apply -f deploy/istio/security/peerauthentication-permissive.yaml
kubectl apply -f deploy/istio/security/serviceentry-rds.yaml \
              -f deploy/istio/security/destinationrule-rds.yaml
```

- Validation: `istioctl verify-install`; istiod Ready; the gateway pod Running;
  the gateway Service gets a second NLB address (`kubectl -n istio-system get svc istio-ingressgateway`).
- Rollback: `istioctl uninstall -y --purge` (no app traffic touches the mesh yet,
  so this is safe), then delete the second NLB Service.

### Phase 2: Stand up the gateway alongside nginx (no traffic yet)

The gateway and its NLB now exist but no DNS points at it. nginx still serves all
four hosts.

```sh
kubectl apply -f deploy/istio/gateway/gateway.yaml
kubectl apply -f deploy/istio/gateway/virtualservice-grafana.yaml \
              -f deploy/istio/gateway/virtualservice-coder.yaml \
              -f deploy/istio/gateway/virtualservice-keycloak.yaml \
              -f deploy/istio/gateway/virtualservice-gitlab.yaml
```

- Validation (no DNS change needed): resolve the gateway NLB DNS to an IP and
  curl with an explicit Host header and TLS SNI, for example
  `curl -sk -H 'Host: grafana.usgov.coderdemo.io' --resolve grafana.usgov.coderdemo.io:443:<gw-nlb-ip> https://grafana.usgov.coderdemo.io/login`
  returns the Grafana login. Repeat per host. Confirm Keycloak responses already
  carry `Secure; SameSite=None` via this path.
- Rollback: `kubectl delete -f deploy/istio/gateway/`; nginx is unaffected.

### Phase 3: Canary Grafana via DNS

Grafana has no dedicated Route53 record today; it resolves through the wildcard.
Adding a specific `grafana` alias to the gateway NLB cleanly moves only Grafana
(a more-specific record overrides the wildcard) without disturbing workspace apps.

```sh
# Create A-alias grafana.usgov.coderdemo.io -> gateway NLB (zone Z06701704WFETYIRU5C8).
# Needs the gateway NLB's CanonicalHostedZoneId (aws elbv2 describe-load-balancers).
aws route53 change-resource-record-sets --hosted-zone-id Z06701704WFETYIRU5C8 \
  --change-batch '{"Changes":[{"Action":"UPSERT","ResourceRecordSet":{
    "Name":"grafana.usgov.coderdemo.io","Type":"A",
    "AliasTarget":{"HostedZoneId":"<GW_NLB_ZONE_ID>","DNSName":"<GW_NLB_DNS>","EvaluateTargetHealth":true}}}]}'
```

- Validation: real browser to `https://grafana.usgov.coderdemo.io`; OIDC login;
  confirm served by the gateway (Envoy `server` header / istiod proxy logs).
- Rollback (instant): delete the `grafana` record; it falls back to the wildcard,
  which still points at nginx.

### Phase 4: Cut over dev, gitlab, then keycloak (one at a time)

For each existing record, repoint the alias from the nginx NLB to the gateway NLB.
Do `dev` and `gitlab` first, then `keycloak` deliberately (it is both the cookie
fix and the highest SSO blast radius).

```sh
# Per host: UPSERT the existing alias (dev / gitlab / auth) to the gateway NLB.
aws route53 change-resource-record-sets --hosted-zone-id Z06701704WFETYIRU5C8 \
  --change-batch '{"Changes":[{"Action":"UPSERT","ResourceRecordSet":{
    "Name":"<host>.usgov.coderdemo.io","Type":"A",
    "AliasTarget":{"HostedZoneId":"<GW_NLB_ZONE_ID>","DNSName":"<GW_NLB_DNS>","EvaluateTargetHealth":true}}}]}'
```

- Validation per host: app loads; for `auth`, `curl -D -` shows `Secure;
  SameSite=None`, the Account Console loads, and Coder/GitLab/Grafana SSO still
  works (all depend on the realm). Allow DNS TTL to settle between hosts.
- Rollback per host (instant): repoint that one alias back to the nginx NLB.

### Phase 5: Cut the wildcard, then decommission nginx

```sh
# Move the wildcard last; it carries all workspace-app subdomains.
aws route53 change-resource-record-sets --hosted-zone-id Z06701704WFETYIRU5C8 \
  --change-batch '{"Changes":[{"Action":"UPSERT","ResourceRecordSet":{
    "Name":"*.usgov.coderdemo.io","Type":"A",
    "AliasTarget":{"HostedZoneId":"<GW_NLB_ZONE_ID>","DNSName":"<GW_NLB_DNS>","EvaluateTargetHealth":true}}}]}'
```

- Validation: build/open a workspace, exercise a wildcard app subdomain, a web
  terminal, and an agent reconnect through the gateway.
- Then remove nginx and the legacy Ingress objects (owned by platform/orchestrator):
  uninstall the `ingress-nginx` Helm release and delete the four `Ingress`
  resources in `deploy/{coder,keycloak,gitlab,observability}`.
- Rollback: before deleting nginx, repoint any/all records back to the nginx NLB.
  Keep the nginx release until all hosts are verified for at least one soak window.

### Phase 6: Inject sidecars namespace by namespace (still PERMISSIVE)

Follow [`deploy/istio/namespace-injection.md`](../../deploy/istio/namespace-injection.md):
`keycloak`, then `coder`, then `gitlab`. Leave `coder-workspaces`, `monitoring`,
and `external-secrets` out.

```sh
kubectl label namespace keycloak istio-injection=enabled --overwrite
kubectl rollout restart deployment -n keycloak
istioctl proxy-status     # SYNCED; then validate before the next namespace
# optional: kubectl apply -f deploy/istio/security/peerauthentication-keycloak-mgmt.yaml
```

- Validation per namespace: app healthy, probes green, `istioctl proxy-config`
  shows the sidecar, traffic flows. For coder, a workspace build still succeeds.
  For gitlab, git over https and a CI job succeed.
- Rollback per namespace: remove the label and `kubectl rollout restart` to drop
  sidecars; PERMISSIVE means callers never broke.

### Phase 7: Flip to STRICT

```sh
kubectl apply -f deploy/istio/security/peerauthentication-strict.yaml
```

- Validation: all app traffic healthy; `istioctl proxy-config` / mesh telemetry
  show mTLS on injected edges; RDS connections still work (DestinationRule
  DISABLE); probes green.
- Rollback (instant): `kubectl apply -f deploy/istio/security/peerauthentication-permissive.yaml`.
- Decide on `coder-workspaces` separately (recommended: stay excluded).

### Phase 8: Observability wiring (separate workstream)

Owned by the observability workstream (deploy/observability): ServiceMonitor /
PodMonitor for istiod and sidecars accounting for STRICT scrape paths, the Istio
Grafana dashboards, Envoy access logs already flow to Loki via Promtail, and
optional Kiali behind Keycloak SSO. Not in this workstream's file ownership.

## 3. Lift estimate (how big is the lift)

Focused engineering hours per phase, plus realistic elapsed time including soak
windows between phases. Image mirroring (Phase 1 prep) is already done.

| Phase | Work | Eng hours |
|------|------|-----------|
| 0 | Approvals, istioctl install, precheck, quota | 2 to 4 |
| 1 | Verify images, install control plane, RDS ServiceEntry, verify | 2 to 3 |
| 2 | Gateway + VirtualServices alongside nginx, Host-header validation | 2 to 4 |
| 3 | Grafana DNS canary + validate | 2 to 3 |
| 4 | Cut dev, gitlab, keycloak (keycloak careful, cookie validation) | 4 to 6 |
| 5 | Cut wildcard, soak, decommission nginx | 2 to 3 |
| 6 | Inject keycloak, coder, gitlab under PERMISSIVE, validate each | 4 to 6 |
| 7 | Flip STRICT, validate, decide on workspaces | 2 to 4 |
| Subtotal (core, phases 0 to 7) | | 20 to 33 |
| 8 | Observability wiring (separate workstream) | 3 to 5 |
| Contingency (~20%) | k8s 1.36 newness, GitLab/agent edge cases | 5 to 8 |
| Total (with observability + contingency) | | 28 to 46 |

Realistic elapsed time: roughly 4 to 6 working days for the core, because each
DNS cutover and the STRICT flip want a soak/validation window rather than being
done back to back. Highest-variance items: the Keycloak cutover (Phase 4) and
GitLab injection (Phase 6). The version gate is already retired.

## 4. Independent workstreams for fan-out (file ownership)

Designed so parallel implementation agents do not collide. WS-A is the only hard
prerequisite for the rest; within the dependents, B/D/E/F can proceed in parallel
once A is in.

| ID | Workstream | Owns (files) | Depends on |
|----|-----------|--------------|------------|
| WS-A | Control-plane install | `deploy/istio/istio-operator.yaml`; image mirror (`scripts/images.txt`, `scripts/mirror-images.sh`) | none |
| WS-B | Ingress gateway + cutover | `deploy/istio/gateway/*` (Gateway, VirtualServices, EnvoyFilter); Route53 cutover execution | WS-A |
| WS-C | Keycloak cookie fix | `deploy/istio/gateway/virtualservice-keycloak.yaml` (with WS-B); coordinated `traffic.sidecar.istio.io/excludeInboundPorts` annotation in `deploy/keycloak/deployment.yaml` (keycloak workstream) | WS-A, WS-B |
| WS-D | mTLS security policy | `deploy/istio/security/*` (PeerAuthentication, RDS ServiceEntry/DestinationRule) | WS-A; STRICT flip waits on WS-E |
| WS-E | Namespace injection | `deploy/istio/namespace-injection.md`; labels + rollout on app namespaces (coordinate restarts with app owners) | WS-A; ingress cutover (WS-B) first |
| WS-F | Observability wiring | `deploy/observability/*` (istiod/sidecar monitors, Istio dashboards, optional Kiali) | WS-A |
| WS-G | nginx decommission | `deploy/platform/ingress-nginx-values.yaml`; legacy `Ingress` in `deploy/{coder,keycloak,gitlab,observability}` | WS-B cutover complete |

Conflict avoidance: each directory has exactly one owner. The only cross-owner
touch points are explicit and coordinated: WS-C's optional one-line annotation in
`deploy/keycloak/` (alternatively handled entirely on the Istio side by WS-D's
`peerauthentication-keycloak-mgmt.yaml`), and WS-G's removal of the legacy
per-app `Ingress` objects after WS-B confirms the gateway serves every host.
