# As-built documentation

This directory is the engineering "as-built" record of the GovCloud Coder demo:
what was deployed, how it is configured and architected, and which parts are
declarative (Terraform) versus imperative (CLI, Helm, kubectl, SQL, API).

Live status and the credentials map live in the repo-root `STATUS.md`. These
docs explain the *how* and *why* behind that status.

## Read in this order

| Doc | Scope |
|---|---|
| [00-overview.md](00-overview.md) | Executive + architecture overview, component map, topology diagram, and the three core flows (SSO login, workspace create + GitLab auth, Claude Code through the AI Gateway). Start here. |
| [10-infrastructure.md](10-infrastructure.md) | AWS GovCloud substrate: account/region/partition, VPC, EKS (standard, not Auto Mode, and why), node group, IRSA roles, RDS, ECR, Route53, ACM, NLB. |
| [20-platform-kubernetes.md](20-platform-kubernetes.md) | Kubernetes platform layer: namespaces, ingress-nginx + load-balancer-controller, `gp3` StorageClass, workspace RBAC, platform-owned Secrets. |
| [25-istio-service-mesh.md](25-istio-service-mesh.md) | Istio service mesh: the ingress gateway L7 edge (own NLB + ACM cert), mesh-wide STRICT mTLS, sidecar injection scope (`coder`, `keycloak`, `gitlab`; `coder-workspaces` excluded), the RDS ServiceEntry, and Kiali. ingress-nginx is retained out of the DNS path for rollback (issue #34). |
| [30-coder-control-plane.md](30-coder-control-plane.md) | Coder v2.34.0 control plane: a section-by-section walkthrough of `deploy/coder/values.yaml`, OIDC SSO, auth-boundary hardening, licensing, appearance. |
| [40-identity-keycloak.md](40-identity-keycloak.md) | Keycloak realm `coder`, the OIDC client, the SSO wiring, and IdP sync status. |
| [45-idp-sync-personas.md](45-idp-sync-personas.md) | Multi-tenant org/group/role hierarchy, the persona users, and the verified Keycloak-to-Coder IdP sync (org + group + role). |
| [50-gitlab-scm.md](50-gitlab-scm.md) | In-boundary GitLab SCM, the instance-wide OAuth app, how every workspace authenticates git against it, and the GitLab CI runners plus the gateway-fronted Container Registry (`registry.usgov.coderdemo.io`). |
| [55-observability.md](55-observability.md) | In-cluster observability: kube-prometheus-stack (Prometheus + Grafana) in the `monitoring` namespace, Coder Prometheus metrics, the six Coder Grafana dashboards at `grafana.usgov.coderdemo.io`, in-cluster logging (Loki + Promtail), the Istio mesh dashboards and the Kiali console, the AI Governance dashboard, structured JSON logs, and audit logging. The AWS-native managed variant is planned in `docs/plans/`. |
| [60-ai-gateway.md](60-ai-gateway.md) | AI Gateway / AI Bridge: DB-managed providers (`anthropic` direct + `anthropic-bedrock` IRSA), name-based routing, the end-to-end request flow, and the remaining action to make AI respond. |
| [70-workspace-templates.md](70-workspace-templates.md) | The `claude-code` workspace template: pod/PVC, the claude-code module (4.7.3), Coder Tasks, parameters, and the required GitLab external auth. |
| [80-iac-vs-imperative.md](80-iac-vs-imperative.md) | The declarative-versus-imperative ledger and the Terraform reconciliation backlog. |
| [85-secrets-management.md](85-secrets-management.md) | Runtime secrets via External Secrets Operator + AWS Secrets Manager (IRSA): ASM layout, migration, verification, and the EKS CMK backlog. |
| [90-operations-runbook.md](90-operations-runbook.md) | Day-2 operations: env/kubeconfig, API/CLI login, Helm upgrade, template push, image mirroring, banner, health checks, known gaps. |

## One thing to know before reading

The AI path is fully wired but the `anthropic` provider holds a **placeholder**
key. Pasting a real Anthropic key into that provider at `/ai/settings` is the
only step left before live AI responses work. See
[60-ai-gateway.md](60-ai-gateway.md) and `STATUS.md`.
