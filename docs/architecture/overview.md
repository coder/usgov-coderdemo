# Architecture overview

## Goal

Durable US-Government Coder demo on **AWS GovCloud (`us-gov-west-1`, 3 AZs)** for ISV integration, templates, identity, Istio, observability, and (later) Bedrock.

## Hostnames

| Service | Hostname | Placement |
|---|---|---|
| Coder | `dev.usgov.coderdemo.io` | EKS |
| Keycloak | `auth.usgov.coderdemo.io` | EKS |
| Grafana | `metrics.usgov.coderdemo.io` | EKS |
| GitLab | `gitlab.usgov.coderdemo.io` | EC2 |
| EKS proxy | `aws.usgov.coderdemo.io` | EKS |
| OCP proxy | `ocp.usgov.coderdemo.io` | OCP |
| Registry | `*.dkr.ecr.us-gov-west-1.amazonaws.com` | ECR |

## Phasing

| Phase | Delivers |
|---|---|
| **1** | EKS platform + Coder + Keycloak min + EKS provisioner/proxy + EKS template |
| **2** | Istio, GitLab, full identity, observability polish |
| **3** | OCP IPI + provisioner/proxy + OCP template |
| **4** | Bedrock IRSA + AI template |

Phase 1 is the overnight success line.

## Why EKS hosts the control plane

- Coder CP is stateless Go + Postgres; durability is RDS
- OCP IPI rebuild ~75 min; wrong host for users/templates/audit
- OCP still satisfies "Coder on OpenShift" via external provisioner + OCP workspaces

## Durable state

| Asset | Store |
|---|---|
| Coder + Keycloak DB | RDS Multi-AZ |
| Loki | S3 |
| GitLab backups/LFS | S3 + EBS snapshots |
| Images | ECR + pull-through |
| TF state | S3 + DynamoDB lock |

See also: [target-architecture.md](target-architecture.md), [ingress.md](ingress.md), [istio.md](istio.md), [identity.md](identity.md)
