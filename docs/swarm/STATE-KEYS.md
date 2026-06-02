# Terraform state keys

One apply agent per key. Backend: S3 + DynamoDB from WS-01.

| State key | Module path | Owner WS | Phase |
|---|---|---|---|
| `bootstrap/terraform.tfstate` | `terraform/bootstrap/` | WS-01 | 1 |
| `network/terraform.tfstate` | `terraform/network/` | WS-02 | 1 |
| `data/terraform.tfstate` | `terraform/data/` | WS-03 | 1 |
| `eks/terraform.tfstate` | `terraform/eks/` | WS-04 | 1 |
| `eks-apps/terraform.tfstate` | `terraform/eks-apps/` | WS-05 | 1 |
| `platform-eks/terraform.tfstate` | `terraform/platform-eks/` | WS-06 | 1 |
| `eks-day2/terraform.tfstate` | `terraform/eks-day2/` | WS-07 | 1 |
| `istio/terraform.tfstate` | `terraform/istio/` | WS-09 | 2 |
| `platform-ec2/terraform.tfstate` | `terraform/platform-ec2/` | WS-10 | 2 |
| `ocp/terraform.tfstate` | `terraform/ocp/` | WS-11a | 3 |
| `identity/terraform.tfstate` | `terraform/identity/` | WS-12 | 2 |
| `ai/terraform.tfstate` | `terraform/ai/` | WS-13 | 4 |

## Lock discipline

- Wait up to 10 min on lock contention
- FAIL with lock ID in handoff
- No `force-unlock` without orchestrator approval

## Apply wrapper

Use `scripts/tf-apply.sh terraform/<module>` — plan, check destroys, apply, output.

## Remote state consumption

Downstream modules read outputs via `terraform_remote_state` or handoff doc values. Prefer remote state when WS-01 backend supports it.

## Typical output chain

```
WS-01 → bucket, zone_id, ecr
WS-02 → vpc_id, subnets
WS-03 → rds_endpoint, s3 buckets
WS-04 → cluster_name, oidc_arn, kubeconfig
WS-05 → coder_url, nlb_arn
WS-06 → keycloak_url
WS-07 → provisioner_name, proxy_url
```

Handoff docs must duplicate critical outputs for agents without remote state wired yet.
