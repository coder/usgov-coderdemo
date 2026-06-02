# WS-01 — Bootstrap

| Field | Value |
|---|---|
| **State key** | `bootstrap/terraform.tfstate` |
| **Phase** | 1 |
| **Model** | **Sonnet** |
| **Depends on** | WS-00, GATE-0 |
| **Blocks** | WS-02 |

## Goal

TF backend, DNS zone, ECR, pull-through cache.

## Read handoffs

- WS-00-scaffold (if any)

## Tasks

1. S3 + DynamoDB for TF state (if not exists)
2. GovCloud R53 zone `usgov.coderdemo.io`
3. NS delegation on commercial `coderdemo.io` via `$AWS_COMMERCIAL_PROFILE`
4. ECR repos + pull-through (Docker Hub, GHCR, quay)
5. Wire `terraform/modules/partition/`

## Reference

- `reference/coder-eks-deployment/` prereqs if present
- `reference/demo-aigov-rhsummit-2026/terraform/prereqs`

## Apply

```bash
./scripts/tf-apply.sh terraform/bootstrap
```

## Handoff outputs (required)

| Key | Description |
|---|---|
| `tf_state_bucket` | |
| `tf_lock_table` | |
| `r53_zone_id` | |
| `ecr_registry` | e.g. 123456789.dkr.ecr.us-gov-west-1.amazonaws.com |
| `domain` | usgov.coderdemo.io |

## Validation

- [ ] G0.3 NS delegation resolves
- [ ] ECR login works: `aws ecr get-login-password --region us-gov-west-1`

## Parallel authoring

SA-1-ECR and SA-1-NS scripts can author in parallel; **one apply agent**.
