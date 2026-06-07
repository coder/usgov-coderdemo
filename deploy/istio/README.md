# deploy/istio

Apply-ready Istio manifests for the GovCloud Coder demo. These are the design
artifacts for issue #30. NOTHING here is applied to the live cluster by this
workstream; the orchestrator runs the live mutations in the sequenced rollout
described in [docs/plans/istio-implementation.md](../../docs/plans/istio-implementation.md).

## What is here

| Path | Purpose |
|------|---------|
| `istio-operator.yaml` | istioctl install config. Pins Istio 1.30.1, points hub/tag at the ECR mirror, and defines the ingress gateway Service with the NLB + ACM annotations. |
| `gateway/gateway.yaml` | The single L7 `Gateway` (HTTP :80) for all four hosts plus the Coder wildcard. |
| `gateway/virtualservice-*.yaml` | Per-host routing. Each sets `x-forwarded-proto: https`. `virtualservice-keycloak.yaml` is the cookie fix. |
| `gateway/envoyfilter-xforwarded-proto.yaml` | OPTIONAL gateway-wide scheme override; alternative to the per-host header set. Not applied by default. |
| `security/peerauthentication-permissive.yaml` | Mesh-wide PERMISSIVE (the rollout default). |
| `security/peerauthentication-strict.yaml` | Mesh-wide STRICT (the FINAL state). Do not apply until injection is complete. |
| `security/peerauthentication-keycloak-mgmt.yaml` | Optional port-9000 exception for Keycloak probes. |
| `security/serviceentry-rds.yaml`, `security/destinationrule-rds.yaml` | Mesh-external RDS (app-originated TLS; sidecar TLS DISABLE). |
| `namespace-injection.md` | Which namespaces to inject, in what order, and what to exclude. |

## Version and air gap (locked)

- Istio **1.30.1**. Istio 1.30 is the only currently supported release line that
  certifies Kubernetes 1.36 (1.30 supports 1.32 to 1.36; 1.29 stops at 1.35).
- Images are mirrored to ECR via `scripts/images.txt` + `scripts/mirror-images.sh`
  using the `docker.io/istio/*` source, so the existing `docker.io -> docker-hub/`
  mapping applies and no `gcr.io` mapping change was needed.
  - `430737322961.dkr.ecr.us-gov-west-1.amazonaws.com/docker-hub/istio/pilot:1.30.1`
  - `430737322961.dkr.ecr.us-gov-west-1.amazonaws.com/docker-hub/istio/proxyv2:1.30.1`
  - `430737322961.dkr.ecr.us-gov-west-1.amazonaws.com/docker-hub/istio/install-cni:1.30.1`
- `istioctl` 1.30.1 is required on the operator host and is NOT yet installed in
  this workspace; download it on a connected host and copy the binary in
  (air-gapped), matching the control-plane version.

## Apply order (run by the orchestrator, not here)

1. `istioctl install -f istio-operator.yaml` (control plane + gateway, PERMISSIVE default)
2. `kubectl apply -f security/peerauthentication-permissive.yaml`
3. `kubectl apply -f security/serviceentry-rds.yaml -f security/destinationrule-rds.yaml`
4. `kubectl apply -f gateway/` (Gateway + VirtualServices) while nginx still serves traffic
5. DNS cutover host by host (see runbook), Grafana first
6. Label namespaces from `namespace-injection.md`, roll pods
7. Swap PERMISSIVE for `security/peerauthentication-strict.yaml`
8. Decommission ingress-nginx

Each step has validation and rollback in the runbook.
