# WS-02 — Network

| Field | Value |
|---|---|
| **State key** | `network/terraform.tfstate` |
| **Phase** | 1 |
| **Model** | **Sonnet** |
| **Depends on** | WS-01 |
| **Blocks** | WS-03, WS-04, WS-10, WS-11a |

## Goal

EKS VPC + OCP VPC + peering (G0.11).

## Read handoffs

- `docs/swarm/handoffs/WS-01-handoff.md`

## Tasks

1. EKS VPC `10.0.0.0/16`, 3 AZs, public/private/db subnets, NAT/AZ
2. OCP VPC separate CIDR (e.g. `10.1.0.0/16`)
3. VPC peering + routes both directions
4. Outputs for all downstream modules

## Reference

- `reference/coder-eks-deployment/` VPC/network modules

## Apply

```bash
./scripts/tf-apply.sh terraform/network
```

## Handoff outputs

| Key | Description |
|---|---|
| `eks_vpc_id` | |
| `eks_private_subnet_ids` | comma-separated |
| `eks_public_subnet_ids` | |
| `ocp_vpc_id` | |
| `peering_connection_id` | |

## Parallel authoring

SA-2-EKS-VPC, SA-2-OCP-VPC, SA-2-PEER → single apply agent merges.

## Background

Orchestrator may start WS-11a after this WS PASS.
