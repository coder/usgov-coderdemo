# WS-10 — GitLab EC2

| Field | Value |
|---|---|
| **State key** | `platform-ec2/terraform.tfstate` |
| **Phase** | 2 |
| **Model** | **Sonnet** |
| **Depends on** | WS-02, WS-03 (S3) |
| **May start** | After WS-02 (apply after S3 exists) |
| **Track** | B |

## Goal

GitLab Omnibus on EC2, SPOF accepted.

## Read handoffs

- WS-02, WS-03

## Tasks

1. Adapt demo-aigov gitlab TF
2. EC2 + ALB + ACM → `gitlab.usgov.coderdemo.io`
3. LFS/artifacts/backups → S3
4. EBS snapshot schedule

## Reference

- `reference/demo-aigov-rhsummit-2026/terraform/gitlab`

## Apply

```bash
./scripts/tf-apply.sh terraform/platform-ec2
```

## Handoff outputs

| Key | Description |
|---|---|
| `gitlab_url` | |
| `gitlab_instance_id` | |
| `alb_arn` | |

## Validation

- [ ] **C11** clone/push

## Note

Does not block Phase 1. May run parallel with WS-03/04 if lock discipline holds.
