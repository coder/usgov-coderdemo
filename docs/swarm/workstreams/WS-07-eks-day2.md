# WS-07 — EKS day2 (provisioner + proxy)

| Field | Value |
|---|---|
| **State key** | `eks-day2/terraform.tfstate` |
| **Phase** | 1 |
| **Model** | **Opus** |
| **Depends on** | WS-05 PASS |
| **Blocks** | WS-08 |

## Goal

License, EKS external provisioner, EKS workspace proxy.

## Read handoffs

- WS-05 (coder_url), WS-04 (cluster)

## Tasks

1. Apply `$CODER_LICENSE`
2. Deploy external provisioner, tag `platform=eks`
3. Deploy workspace proxy (`aws.usgov.coderdemo.io` or per design)
4. Store provisioner key in External Secrets

## Reference

- `reference/coder-eks-deployment/03-day2`

## Apply

```bash
./scripts/tf-apply.sh terraform/eks-day2
```

## Parallel authoring

SA-7-PROV and SA-7-PROXY author in parallel; apply registers provisioner then proxy.

## Handoff outputs

| Key | Description |
|---|---|
| `provisioner_name` | |
| `workspace_proxy_url` | |
| `provisioner_tags` | platform=eks |

## Validation

- [ ] Provisioner Connected in Coder UI
- [ ] **C5** proxy URL works
