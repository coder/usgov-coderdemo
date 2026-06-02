# WS-06 — Keycloak minimal

| Field | Value |
|---|---|
| **State key** | `platform-eks/terraform.tfstate` |
| **Phase** | 1 |
| **Model** | **Sonnet** |
| **Depends on** | WS-04, WS-03 |
| **May parallel** | WS-05 |

## Goal

Keycloak on EKS + Coder OIDC client (minimal).

## Read handoffs

- WS-03, WS-04

## Tasks

1. Deploy Keycloak (operator/chart)
2. RDS keycloak DB
3. Ingress `auth.usgov.coderdemo.io` (direct NLB, not Istio)
4. Realm `usgov`, admin bootstrap
5. Coder OIDC client TF from homelab

## Reference

- `reference/homelab/terraform/keycloak`

## Apply

```bash
./scripts/tf-apply.sh terraform/platform-eks
```

Stagger helm 5 min after WS-05 if parallel.

## Handoff outputs

| Key | Description |
|---|---|
| `keycloak_url` | |
| `keycloak_realm` | usgov |
| `coder_oidc_client_id` | |

## Validation

- [ ] **C9** Keycloak UI loads
- [ ] OIDC client exists (full Coder login may need coderd restart)

## Status

PARTIAL acceptable if client configured but end-to-end login pending WS-07.
