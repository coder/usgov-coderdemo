# Documentation index

## Start here

| Audience | File |
|---|---|
| **As-built (what was actually deployed)** | **[as-built/README.md](as-built/README.md)** |
| Human setup | [PRE-REQUISITES.md](PRE-REQUISITES.md) |
| Orchestrator | [swarm/ORCHESTRATOR.md](swarm/ORCHESTRATOR.md) |
| **All agents** | **[AGENT-PRD.md](AGENT-PRD.md)** |
| Subagents | [swarm/RULES.md](swarm/RULES.md) + [swarm/workstreams/](swarm/workstreams/) |

## As-built (current deployment)

The engineering record of what is deployed and how it is configured. The swarm
and workstream docs below describe the planned build; `as-built/` describes the
live result.

- [as-built/README.md](as-built/README.md) (index)
- [as-built/00-overview.md](as-built/00-overview.md): architecture + flows
- [as-built/10-infrastructure.md](as-built/10-infrastructure.md): AWS GovCloud substrate (VPC, EKS, RDS, ECR, Route53, ACM, NLB)
- [as-built/20-platform-kubernetes.md](as-built/20-platform-kubernetes.md): Kubernetes platform layer (namespaces, ingress, StorageClass, RBAC)
- [as-built/25-istio-service-mesh.md](as-built/25-istio-service-mesh.md): Istio service mesh edge + mesh-wide mTLS
- [as-built/30-coder-control-plane.md](as-built/30-coder-control-plane.md): Coder v2.34.0 control plane + OIDC SSO
- [as-built/40-identity-keycloak.md](as-built/40-identity-keycloak.md): Keycloak realm `coder` + OIDC client
- [as-built/45-idp-sync-personas.md](as-built/45-idp-sync-personas.md): IdP org/group/role sync + demo personas
- [as-built/50-gitlab-scm.md](as-built/50-gitlab-scm.md): in-boundary GitLab SCM + CI runners + Container Registry
- [as-built/55-observability.md](as-built/55-observability.md): in-cluster Prometheus + Grafana observability
- [as-built/60-ai-gateway.md](as-built/60-ai-gateway.md): AI Gateway providers + name-based routing
- [as-built/70-workspace-templates.md](as-built/70-workspace-templates.md): the `claude-code` workspace template
- [as-built/80-iac-vs-imperative.md](as-built/80-iac-vs-imperative.md): declarative vs imperative ledger
- [as-built/85-secrets-management.md](as-built/85-secrets-management.md): secrets via ESO + AWS Secrets Manager
- [as-built/90-operations-runbook.md](as-built/90-operations-runbook.md): day-2 ops

## Plans (design proposals, not yet applied)

Forward-looking designs with companion GitHub issues. Nothing in these plans is
applied to the live environment.

- [plans/README.md](plans/README.md) (index)
- [plans/observability-aws-native.md](plans/observability-aws-native.md): AWS-native metrics + audit pipeline (AMP/AMG, CloudWatch/Firehose/S3/Athena, optional Security Lake)
- [plans/gitops-control-plane.md](plans/gitops-control-plane.md): Argo CD control plane sourced from the in-cluster GitLab
- [plans/gitops-adoption.md](plans/gitops-adoption.md): per-workload GitOps adoption + non-Kubernetes app state

## Architecture

- [architecture/overview.md](architecture/overview.md)
- [architecture/target-architecture.md](architecture/target-architecture.md)
- [architecture/reference-repos.md](architecture/reference-repos.md)
- [architecture/ingress.md](architecture/ingress.md)
- [architecture/istio.md](architecture/istio.md)
- [architecture/identity.md](architecture/identity.md)

## Swarm operations

- [decisions-locked.md](decisions-locked.md)
- [swarm/GATES.md](swarm/GATES.md)
- [swarm/PARALLELISM.md](swarm/PARALLELISM.md)
- [swarm/STATE-KEYS.md](swarm/STATE-KEYS.md)
- [swarm/CONNECTIVITY.md](swarm/CONNECTIVITY.md)
- [PRE-REQUISITES.md](PRE-REQUISITES.md)
- [swarm/CREDENTIALS.md](swarm/CREDENTIALS.md)
- [swarm/PHASE-1-SUCCESS.md](swarm/PHASE-1-SUCCESS.md)
- [swarm/MODELS.md](swarm/MODELS.md)

## Workstreams (WS-00 … WS-13)

| WS | File | Phase | Model / Effort |
|---|---|---|---|
| 00 | [WS-00-scaffold.md](swarm/workstreams/WS-00-scaffold.md) | 0 | Sonnet / high |
| 01 | [WS-01-bootstrap.md](swarm/workstreams/WS-01-bootstrap.md) | 1 | Sonnet / high |
| 02 | [WS-02-network.md](swarm/workstreams/WS-02-network.md) | 1 | Sonnet / high |
| 03 | [WS-03-data.md](swarm/workstreams/WS-03-data.md) | 1 | Sonnet / high |
| 04 | [WS-04-eks.md](swarm/workstreams/WS-04-eks.md) | 1 | **Opus 4.8 / xhigh** |
| 05 | [WS-05-coder.md](swarm/workstreams/WS-05-coder.md) | 1 | **Opus 4.8 / xhigh** |
| 06 | [WS-06-keycloak.md](swarm/workstreams/WS-06-keycloak.md) | 1 | Sonnet / high |
| 07 | [WS-07-eks-day2.md](swarm/workstreams/WS-07-eks-day2.md) | 1 | **Opus 4.8 / xhigh** |
| 08 | [WS-08-templates-eks.md](swarm/workstreams/WS-08-templates-eks.md) | 1 | Sonnet / high |
| 09 | [WS-09-istio.md](swarm/workstreams/WS-09-istio.md) | 2 | **Opus 4.8 / xhigh** |
| 10 | [WS-10-gitlab.md](swarm/workstreams/WS-10-gitlab.md) | 2 | Sonnet / high |
| 11 | [WS-11-ocp.md](swarm/workstreams/WS-11-ocp.md) | 3 | Opus/Sonnet† |
| 12 | [WS-12-identity.md](swarm/workstreams/WS-12-identity.md) | 2 | Sonnet / high |
| 13 | [WS-13-bedrock.md](swarm/workstreams/WS-13-bedrock.md) | 4 | Sonnet / high |

† WS-11 sub-streams: see [MODELS.md](swarm/MODELS.md) for model + effort per SA

## Runtime artifacts (created by agents)

- [swarm/handoffs/](swarm/handoffs/): per-WS outputs
- [swarm/SWARM-STATUS.md](swarm/SWARM-STATUS.md): orchestrator dashboard

## Templates

- [templates/handoff-template.md](templates/handoff-template.md)
- [templates/swarm-status-template.md](templates/swarm-status-template.md)

## Other

- [repo-layout.md](repo-layout.md)
- [risks.md](risks.md)
- [out-of-scope.md](out-of-scope.md)
- [runbooks/](runbooks/)
