# Plans (design proposals)

Forward-looking design documents for the GovCloud Coder demo. Most are
**proposals for LATER adoption** that have not been applied to the live
cluster, AWS, Coder, Keycloak, or GitLab. The exception is
[chat-spend-limits.md](chat-spend-limits.md), which is **applied live**: the
demo spend tiers are configured on `dev.usgov.coderdemo.io` (reversible via
`scripts/demo-chat-spend-limits.py --teardown`). Each forward-looking plan has
companion GitHub issues that track the implementation work.

The engineering record of what is actually deployed lives in
[`../as-built/`](../as-built/README.md); this directory describes where parts of
that deployment are intended to evolve.

| Plan | Scope | Issues |
|---|---|---|
| [observability-aws-native.md](observability-aws-native.md) | The production, AWS-native observability + audit target the in-cluster Prometheus/Grafana stack should evolve into: Amazon Managed Prometheus + Grafana for metrics, and CloudWatch -> Firehose -> S3 -> Athena with an optional Amazon Security Lake (OCSF) path for audit/SIEM. | #13-#20 |
| [gitops-control-plane.md](gitops-control-plane.md) | The GitOps control plane and bootstrap: Argo CD installed in-cluster, sourcing from the in-cluster GitLab, with an app-of-apps over the existing `deploy/` paths and a non-disruptive adopt-in-place strategy. | #6-#12 |
| [gitops-adoption.md](gitops-adoption.md) | Per-workload GitOps adoption details and the application state a GitOps controller cannot natively reconcile (Coder API config via Argo Jobs, Keycloak realm via keycloak-config-cli, AWS substrate stays Terraform). | #21-#29 |
| [istio-implementation.md](istio-implementation.md) | Istio 1.30.1 service mesh adoption on EKS k8s 1.36: ECR-mirrored install via istioctl, an Istio ingress gateway replacing ingress-nginx behind the NLB+ACM, the Keycloak X-Forwarded-Proto cookie fix, and mesh-wide mTLS rolled PERMISSIVE then STRICT. Apply-ready manifests live in `deploy/istio/`. | #30 |
| [chat-spend-limits.md](chat-spend-limits.md) | The Coder Agents chat usage-limit (spend cap) system and the demo tiers: a global default with group and user overrides, tightest-wins precedence, and hard HTTP 409 enforcement metered from per-model costs. **APPLIED LIVE** (global $500/month, with group and user overrides below it), unlike the other forward-looking plans. | applied (CODAGT) |
| [v2-declarative-platform.md](v2-declarative-platform.md) | Umbrella convergence plan toward a fully declarative platform: one authoritative writer per domain, sequencing the GitOps, observability, and Istio plans behind the `verify-drift.py` CI gate. | Section 7 backlog |

## Relationship between the plans

- The two GitOps plans are siblings: **gitops-control-plane** decides and
  bootstraps the controller (the "where it syncs from" and "how it is
  installed"), while **gitops-adoption** designs, per workload, how each live
  resource is adopted without disruption. They deliberately do not duplicate
  each other.
- **observability-aws-native** is independent of GitOps: it is the managed-AWS
  target for the observability stack documented as-built in
  [`../as-built/55-observability.md`](../as-built/55-observability.md). Its
  Phase 0 (enable Coder Prometheus metrics + JSON audit logging) is already done
  by the in-cluster build; the remaining phases are the AWS-native migration.
