# WS-05 — Coder core (Phase 1 milestone)

| Field | Value |
|---|---|
| **State key** | `eks-apps/terraform.tfstate` |
| **Phase** | 1 |
| **Model** | **Opus** |
| **Depends on** | WS-04, WS-03 |
| **Blocks** | WS-07, WS-09 |
| **May parallel** | WS-06 (different state key) |

## Goal

Coder Helm HA + **direct NLB ingress**. Phase 1 milestone.

## Read handoffs

- WS-03 (RDS), WS-04 (kubeconfig)

## Tasks

1. External Secrets (if not on cluster)
2. Coder Helm: 3 replicas, RDS coder DB
3. **NLB + ACM → coderd Service** (`ingress_mode=direct`)
4. DNS `dev.usgov.coderdemo.io`
5. Observability stack: **optional defer to Track B** if time-constrained

## Reference

- `reference/coder-eks-deployment/02-apps`

## Do NOT

- Install Istio
- Set ingress_mode=istio

## Apply

```bash
./scripts/tf-apply.sh terraform/eks-apps
```

## Parallel authoring

| SA | Component |
|---|---|
| SA-5-CODER | Coder Helm + NLB |
| SA-5-ES | External Secrets |
| SA-5-OBS | Grafana stack (optional defer) |

One apply agent merges → single apply.

## Handoff outputs

| Key | Description |
|---|---|
| `coder_url` | https://dev.usgov.coderdemo.io |
| `nlb_arn` | direct NLB for rollback |
| `coder_helm_release` | |

## Validation

- [ ] **C1** HTTPS UI loads
- [ ] coderd pods Running

## Notes

Orchestrator waits for WS-05 PASS before WS-07.
