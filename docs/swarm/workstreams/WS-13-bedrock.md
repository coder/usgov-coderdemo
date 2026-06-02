# WS-13 — Bedrock AI

| Field | Value |
|---|---|
| **State key** | `ai/terraform.tfstate` |
| **Phase** | 4 |
| **Model** | **Sonnet** |
| **Depends on** | G0.9 PASS, WS-05 |
| **Track** | B |

## Goal

Bedrock IRSA, allowlist, AI Bridge, AI template.

## Skip condition

G0.9 FAIL → orchestrator skips WS-13.

## Read handoffs

- WS-05, gate-0 Bedrock model list

## Tasks

1. IRSA `coder-bedrock` (partition-aware)
2. Model allowlist for `us-gov-west-1` (not commercial IDs)
3. Configure Coder AI Bridge on coderd
4. AI-dev workspace template
5. If WS-09 done: verify ServiceEntry egress (C12)

## Reference

- `reference/demo-aigov-rhsummit-2026/` irsa.tf, allowlist §25

## Apply

```bash
./scripts/tf-apply.sh terraform/ai
```

## Parallel authoring

SA-13-IRSA + SA-13-ALLOW parallel; template after IRSA.

## Validation

- [ ] **C12** AI completion in workspace
