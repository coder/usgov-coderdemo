# Ingress strategy

## Phase 1 — direct (locked default)

```
Internet → NLB (ACM) → coderd Service
           dev.usgov.coderdemo.io
```

- `ingress_mode=direct` in `versions.lock.yaml`
- Reuse NLB + ACM pattern from `reference/coder-eks-deployment`
- Keycloak: own NLB/Service at `auth.usgov` — not through Istio yet
- **Do not install Istio in Phase 1**

## Phase 2 — Istio cutover

```
Internet → NLB → istio-ingressgateway → VirtualService → coderd ClusterIP
```

### Cutover steps

1. Install Istio; inject platform namespaces only
2. Gateway + VS for dev, auth, metrics, `*.dev.usgov`
3. Validate connectivity on Istio NLB **before** DNS flip
4. Flip R53 `dev.usgov` to Istio NLB
5. **Keep direct NLB** — rollback = DNS flip back

### Terraform

```hcl
variable "ingress_mode" {
  type    = string
  default = "direct" # "direct" | "istio"
}
```

## Rollback runbook

See [../runbooks/ingress-rollback.md](../runbooks/ingress-rollback.md).
