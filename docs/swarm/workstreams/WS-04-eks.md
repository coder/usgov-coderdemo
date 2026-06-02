# WS-04 — EKS cluster

| Field | Value |
|---|---|
| **State key** | `eks/terraform.tfstate` |
| **Phase** | 1 |
| **Model** | **Opus** |
| **Depends on** | WS-02, WS-03 |
| **Blocks** | WS-05, WS-06 |

## Goal

EKS cluster + base IRSA + kubeconfig.

## Read handoffs

- WS-02, WS-03

## Tasks

1. Adapt `reference/coder-eks-deployment/01-infra` for GovCloud
2. Auto Mode if G0.5 PASS else managed node groups
3. IRSA: External Secrets, cert-manager, R53, ECR
4. Write `./kubeconfig` via `make kubeconfig`

## Partition

All ARNs via `data.aws_partition.current.partition` (R6).

## Apply

```bash
./scripts/tf-apply.sh terraform/eks
make kubeconfig
kubectl get nodes
```

## Handoff outputs

| Key | Description |
|---|---|
| `eks_cluster_name` | |
| `eks_cluster_endpoint` | |
| `kubeconfig_path` | ./kubeconfig |
| `irsa_oidc_provider_arn` | |

## Wave 3b

While cluster creates, SA-COPY-EKS may author eks-apps/eks-day2 TF (no apply).

## Validation

- [ ] `kubectl get nodes` Ready
