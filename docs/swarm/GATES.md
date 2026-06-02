# Phase 0 hard gates (GATE-0)

Run `make gate-0` or `scripts/gate-0-check.sh` before fan-out. **Exit non-zero blocks all WS.**

## Gates

| ID | Check | Pass | Fail action |
|---|---|---|---|
| G0.1 | GovCloud IAM | `aws sts get-caller-identity --region us-gov-west-1` | STOP |
| G0.2 | Quotas | EKS, EC2, VPC, EIP, RDS sufficient | shrink or request increase |
| G0.3 | NS delegation | NS on commercial `coderdemo.io` → GovCloud zone | WS-01 only until done |
| G0.4 | ACM/TLS | Cert for `*.usgov.coderdemo.io` in GovCloud | block HTTPS WS |
| G0.5 | EKS compute | Auto Mode OK or `auto_mode=false` path confirmed | set MNG in TF |
| G0.6 | RDS PG17 | Instance class available | pick alternate |
| G0.7 | Coder version | Pinned in `versions.lock.yaml` | orchestrator pins first |
| G0.8 | OCP feasibility | RHCOS AMI + IPI params OK | skip WS-11, warn |
| G0.9 | Bedrock models | `aws bedrock list-foundation-models` | skip WS-13, warn |
| G0.10 | ECR pull-through | DH rule works; note UBI/RH path | UBI → ECR copy fallback |
| G0.11 | Network | Separate VPCs + peering documented | lock in decisions.md |
| G0.12 | Repo layout | usgov-coderdemo + 4 reference clones | WS-00 first; human: `preflight-readiness.sh --clone` |

## Parallel gate probes

Orchestrator may launch read-only subagents in parallel for G0.1–G0.6, G0.8–G0.10, G0.12.

**Model for gate probe subagents:** **Haiku** (see [MODELS.md](MODELS.md)).

G0.3 may need `$AWS_COMMERCIAL_PROFILE`. G0.7 is a file write by orchestrator (**Sonnet**).

## Soft fails (warn, continue)

- **G0.8 FAIL** → skip WS-11 entirely
- **G0.9 FAIL** → skip WS-13 entirely

## gate-0-check.sh behavior

- Implement all checks
- Soft fails print WARN and set skip flags file: `docs/swarm/gate-0-skips.yaml`
- Hard fails exit 1
