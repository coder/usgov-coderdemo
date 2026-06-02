# Ingress rollback (direct NLB)

Use when Istio cutover (WS-09) breaks connectivity.

## Preconditions

- Direct NLB TF resources still exist (`ingress_mode=direct` module not destroyed)
- `docs/swarm/handoffs/WS-05-handoff.md` has `nlb_arn`

## Steps

1. Flip Route 53 `dev.usgov.coderdemo.io` ALIAS to **direct NLB** (WS-05)
2. Optionally flip `auth.usgov` and `metrics.usgov` if moved to Istio
3. Set `ingress_mode=direct` in `versions.lock.yaml`
4. Run `make validate-track-a`
5. Document in SWARM-STATUS

## Do not

- Destroy istio-ingressgateway NLB until root cause found
- force-unlock TF without orchestrator approval
