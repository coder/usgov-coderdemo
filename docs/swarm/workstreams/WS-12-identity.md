# WS-12 — Identity full

| Field | Value |
|---|---|
| **State key** | `identity/terraform.tfstate` |
| **Phase** | 2 |
| **Model** | **Sonnet** |
| **Depends on** | WS-06, WS-05; WS-10 for GitLab OIDC |
| **Track** | B |

## Goal

Full IdP wiring: clients, idp-sync, Grafana/GitLab OIDC.

## Read handoffs

- WS-06, WS-05, WS-10 (if PASS)

## Tasks

1. Keycloak clients: Coder, GitLab, Grafana
2. Coder org/group/role sync
3. Grafana OIDC
4. GitLab OIDC
5. Optional: Keycloak group → IAM for ECR

## Reference

- `reference/homelab/terraform/coder`
- `reference/homelab/terraform/keycloak`

## Parallel subagents

1. **SA-12-KC-CLIENTS** first
2. Then parallel: SA-12-CODER-SYNC, SA-12-GRAFANA-OIDC, SA-12-GITLAB-OIDC

## Apply

```bash
./scripts/tf-apply.sh terraform/identity
```

## Validation

- [ ] Group → role mapping works
- [ ] Grafana login via Keycloak
- [ ] GitLab login via Keycloak (if WS-10 up)
