# Demo build status

Single source of progress truth for the lean Coder+AI GovCloud demo.
Plan: see chat plan file. Target: `us-gov-west-1`, `usgov.coderdemo.io`.

## Foundations
- [x] GovCloud creds (`demoenv-usgov`, acct 430737322961)
- [x] Service quotas verified healthy
- [x] ACM cert issued + sufficient (`*.usgov.coderdemo.io`)
- [x] Route53 zone `Z06701704WFETYIRU5C8` + NS delegation LIVE
- [ ] Bedrock Claude Sonnet 4.5 model access (needs Anthropic agreement via the account PAIRED with GovCloud) — BLOCKED on identifying paired account
- [x] Bedrock path proven: `amazon.nova-pro-v1:0` invokes in GovCloud (fallback model if Claude slips)

## Build (T0 substrate)
- [x] Terraform backend: S3 (versioned/encrypted) + DynamoDB lock created
- [x] VPC (single, 3 AZ, 1 NAT) — authored + validates
- [x] EKS (Auto Mode, k8s 1.36) + cluster/node IAM + admin access entry — authored + validates
- [x] RDS PostgreSQL 18.4 (Multi-AZ instance) — authored + validates
- [x] IRSA OIDC + Bedrock IAM role (coder/coder SA -> bedrock:InvokeModel allowlist) — authored + validates
- [x] Outputs (cluster, oidc, bedrock role, rds, ecr registry) — authored
- [x] `terraform plan` clean: **39 to add, 0 change, 0 destroy** — awaiting user go-ahead to apply
- [ ] ECR repos + mirrored images (repos auto-created by `scripts/mirror-images.sh`)
- [ ] NLB + ingress controller (cert wired) — post-apply (Helm)

## Apps (T1)
- [ ] Coder (Keycloak OIDC, `dev.`)
- [ ] Keycloak (`auth.`)
- [ ] GitLab single-container (`gitlab.`)
- [ ] AI Gateway -> Bedrock (Claude Sonnet 4.5)
- [ ] Workspace template with Coder Agents + Claude Code
- [ ] Test workspace validated

## Out of scope (demo)
OpenShift, Istio, observability, full identity sync.
