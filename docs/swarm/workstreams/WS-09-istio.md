# WS-09 — Istio

| Field | Value |
|---|---|
| **State key** | `istio/terraform.tfstate` |
| **Phase** | 2 |
| **Model** | **Opus** |
| **Depends on** | Phase 1 PASS, WS-05 |
| **Track** | B |

## Goal

Service mesh + ingress cutover. Keep direct NLB for rollback.

## Read handoffs

- WS-05 (nlb_arn, coder_url)
- [CONNECTIVITY.md](../CONNECTIVITY.md)

## Tasks

1. Install Istio; inject platform NS only
2. NLB → istio-ingressgateway
3. Gateway/VS: dev, auth, metrics, `*.dev.usgov`
4. WebSocket config (R12)
5. PeerAuthentication PERMISSIVE → validate → STRICT
6. Bedrock ServiceEntry for coderd (C12 prep)
7. Flip `ingress_mode=istio` in versions.lock.yaml after validation

## Reference

- `reference/openshift-servicemesh-inventory-demo/`
- [ingress.md](../../architecture/ingress.md), [istio.md](../../architecture/istio.md)

## Apply

```bash
./scripts/tf-apply.sh terraform/istio
```

## Parallel authoring

SA-9-INSTALL, SA-9-ROUTES, SA-9-MTLS — serial apply order.

## Validation

- [ ] Full matrix C1–C8 before DNS cutover
- [ ] Rollback doc tested mentally against WS-05 nlb_arn

## Do NOT

- Inject `coder-workspaces` namespace
