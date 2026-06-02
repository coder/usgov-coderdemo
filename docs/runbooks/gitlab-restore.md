# GitLab restore from S3

GitLab EC2 is SPOF. Data should be in S3 + EBS snapshots.

## When

- EC2 instance lost or AZ failure

## Steps

1. Launch new Omnibus instance from `terraform/platform-ec2/`
2. Restore from latest EBS snapshot or S3 backup per Omnibus restore docs
3. Re-point ALB target group
4. Validate C11
5. Re-run GitLab OIDC portion of WS-12 if clients changed

## Handoff reference

- `docs/swarm/handoffs/WS-03-handoff.md` → `s3_gitlab_bucket`
- `docs/swarm/handoffs/WS-10-handoff.md` → instance/alb details
