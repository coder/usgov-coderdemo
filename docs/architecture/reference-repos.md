# Reference repos

**Read-only.** Path: `$REFERENCE_ROOT` (default `../reference/`).

| Clone | Upstream | Clone URL |
|---|---|---|
| `coder-eks-deployment/` | `ausbru87/coder-eks-deployment` | `https://github.com/ausbru87/coder-eks-deployment.git` |
| `demo-aigov-rhsummit-2026/` | `coder/demo-aigov-rhaiis-rhsummit-2026` | `https://github.com/coder/demo-aigov-rhaiis-rhsummit-2026.git` |
| `homelab/` | `ausbru87/homelab` | `https://github.com/ausbru87/homelab.git` |
| `openshift-servicemesh-inventory-demo/` | `ausbru87/openshift-servicemesh-inventory-demo` | `https://github.com/ausbru87/openshift-servicemesh-inventory-demo.git` |

Clone via [PRE-REQUISITES.md](../PRE-REQUISITES.md) or `scripts/preflight-readiness.sh --clone`.

| Clone | Copy into usgov-coderdemo |
|---|---|
| `coder-eks-deployment/` | `terraform/eks`, `eks-apps`, `eks-day2`, observability modules |
| `demo-aigov-rhsummit-2026/` | `terraform/ocp`, `platform-ec2`, `gitops/`, Bedrock IRSA |
| `homelab/` | Keycloak TF, Coder idp-sync, provisioner tags |
| `openshift-servicemesh-inventory-demo/` | `terraform/istio` patterns |

## Rules

1. **Never commit changes** to reference clones.
2. **Copy and adapt** — do not submodule or symlink into TF.
3. Record in `docs/decisions.md`: source repo, commit SHA, files copied, GovCloud adaptations.
4. **Partition fix (R6):** replace hardcoded `arn:aws:` with `data.aws_partition.current.partition`.

## Adaptation checklist (every copy)

- [ ] `region = us-gov-west-1`
- [ ] `partition = aws-us-gov`
- [ ] Domain → `usgov.coderdemo.io`
- [ ] Drop GPU/RHAIIS/in-cluster Coder from OCP material
- [ ] Coder version from `versions.lock.yaml`
