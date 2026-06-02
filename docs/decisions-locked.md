# Locked decisions

Do not re-litigate these during the swarm. Escalate to orchestrator only if a gate proves a decision impossible.

## Architecture

1. **Single Coder control plane** at `dev.usgov.coderdemo.io`.
2. **Two workspace fabrics**, each with external provisioner + workspace proxy:
   - EKS: `aws.usgov.coderdemo.io` (or configured EKS proxy host)
   - OCP: `ocp.usgov.coderdemo.io`
3. **Control plane home = EKS + RDS** (Postgres 17 Multi-AZ). Not on OpenShift.
4. **OCP = rebuildable fabric only** (~75 min IPI rebuild acceptable; no in-cluster CP).

## Platform placement

| Service | Where | Notes |
|---|---|---|
| Coder CP | EKS | HA 3 replicas |
| Keycloak | EKS | RDS backend |
| Grafana/Prom/Loki | EKS | observability stack |
| GitLab | EC2 | SPOF accepted; S3 + EBS snapshots |
| Registry | ECR | Harbor dropped |

## Ingress

- **Phase 1:** `ingress_mode=direct` — NLB + ACM → coderd Service
- **Phase 2:** Istio cutover; **keep direct NLB** for DNS rollback
- Istio is **not** on the Phase 1 critical path

## Mesh

- Istio covers **EKS Tier 0 platform** namespaces only in Phase 2
- **`coder-workspaces` namespace: istio-injection=disabled** in v1
- mTLS: PERMISSIVE → validate → STRICT

## DNS/TLS

- GovCloud Route 53 zone `usgov.coderdemo.io`
- NS-delegated from commercial `coderdemo.io`
- ACM + cert-manager DNS-01 in-partition (no cross-partition creds for validation)

## Registry

- ECR only; pull-through cache for Docker Hub / GHCR / quay
- Workspace creds: IRSA → `aws ecr get-login-password`
- Per-human ECR scoping: optional via Keycloak group → IAM role

## Identity

- Keycloak realm `usgov` at `auth.usgov.coderdemo.io`
- Provisioner tag routing: `platform=eks|ocp` plus homelab `runtime/gpu/class`
- Full org/group/role sync: Phase 2 (WS-12), minimal OIDC in Phase 1 (WS-06)

## Network

- **Separate VPCs + peering:** EKS VPC `10.0.0.0/16`, OCP VPC separate CIDR (e.g. `10.1.0.0/16`)

## Out of scope v1

See [out-of-scope.md](out-of-scope.md).
