# Identity model

## Keycloak

- URL: `https://auth.usgov.coderdemo.io`
- Realm: `usgov`
- Groups: `admins`, `developers`, `auditors`, `template-admins`

## Phase 1 (WS-06)

- Deploy Keycloak on EKS, RDS backend
- Minimal realm bootstrap
- Coder OIDC client only (from `reference/homelab/terraform/keycloak`)

## Phase 2 (WS-12)

- Keycloak clients: Coder, GitLab, Grafana
- Coder org/group/role idp-sync (`reference/homelab/terraform/coder`)
- GitLab + Grafana OIDC
- Optional: Keycloak group → IAM role for per-human ECR

## Provisioner routing

Provisioner keys tagged:

- `platform=eks` | `platform=ocp`
- Plus homelab tags: `runtime`, `gpu`, `class`

Templates declare matching `platform` parameter.

## ECR auth

ECR uses IAM/IRSA, not OIDC. Workspace IRSA for `aws ecr get-login-password`.
