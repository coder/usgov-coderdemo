# WS-03 — Data

| Field | Value |
|---|---|
| **State key** | `data/terraform.tfstate` |
| **Phase** | 1 |
| **Model** | **Sonnet** |
| **Depends on** | WS-02 |
| **Blocks** | WS-04, WS-06, WS-10 |

## Goal

RDS PostgreSQL 17 + S3 buckets.

## Read handoffs

- WS-01, WS-02

## Tasks

1. RDS Multi-AZ (class from G0.6)
2. DBs/users: `coder`, `keycloak`
3. S3: Loki chunks, GitLab artifacts/backups/LFS
4. SG: allow EKS → RDS

## Reference

- `reference/coder-eks-deployment/` RDS modules

## Apply

```bash
./scripts/tf-apply.sh terraform/data
```

## Handoff outputs

| Key | Description |
|---|---|
| `rds_endpoint` | host:port |
| `rds_coder_db` | |
| `rds_keycloak_db` | |
| `s3_loki_bucket` | |
| `s3_gitlab_bucket` | |

## Validation

- [ ] RDS reachable from EKS VPC (after WS-04, or SG plan review)
