# WS-08 — EKS templates

| Field | Value |
|---|---|
| **State key** | none (Coder API / template TF) |
| **Phase** | 1 |
| **Model** | **Sonnet** |
| **Depends on** | WS-07 PASS |
| **Blocks** | Phase 1 validation |

## Goal

Publish EKS kubernetes workspace template with ECR wiring.

## Read handoffs

- WS-07, WS-01 (ECR), WS-05

## Tasks

1. Create `coder-templates/eks-kubernetes/`
2. Parameter `platform=eks`
3. IRSA SA + startup: `aws ecr get-login-password`
4. Devcontainer base via ECR pull-through
5. Publish via Coder CLI or TF provider

## Parallel authoring

SA-8-TEMPLATE, SA-8-ECR, SA-8-PULL may work in parallel on files; one publish agent.

## Handoff outputs

| Key | Description |
|---|---|
| `template_name` | |
| `template_id` | |
| `test_workspace_name` | |

## Validation (Phase 1 complete)

- [ ] **C4** workspace Connected
- [ ] **C3** app URL
- [ ] **C13** docker pull ECR
- [ ] **C14** devcontainer build
- [ ] Orchestrator runs `make validate-track-a`

## Reference

- `reference/coder-eks-deployment/templates`
