# Swarm agent rules

All orchestrator and subagent sessions must follow these rules.

## Scope

1. **cwd:** `usgov-coderdemo/` only for writes
2. **Never modify** `$REFERENCE_ROOT/` — copy/adapt only
3. **One workstream per subagent** unless orchestrator assigns a named SA-* sub-task
4. **One terraform apply agent per state key** at any time

## Before work

- Read `docs/decisions-locked.md`
- Read your `docs/swarm/workstreams/WS-NN-*.md`
- Read all upstream `docs/swarm/handoffs/WS-*-handoff.md` listed in your prompt
- `source` creds env before AWS/kubectl/helm

## During work

- Versions from `versions.lock.yaml` only
- Partition ARNs via `data.aws_partition.current` — no hardcoded `arn:aws:`
- `terraform plan` before every apply; **abort on unexpected destroy**
- Idempotent modules — safe to re-run
- Record reference commit SHAs in handoff + `docs/decisions.md`

## Secrets

- Never commit secrets, kubeconfig with tokens, or `.env`
- Use External Secrets / SSM for runtime secrets
- `$CODER_LICENSE` from env only

## After work

- Write `docs/swarm/handoffs/WS-NN-handoff.md` (required — no file = FAIL)
- `git commit` with message `ws-NN: <summary>`
- Release TF lock (finish apply or fail cleanly)

## Failures

- Do not blind retry
- Max 1 retry per WS per orchestrator instruction
- Do not `terraform force-unlock` unless orchestrator approves in writing in SWARM-STATUS

## Helm / kubectl

- Coordinate on EKS: stagger releases 5+ min or use separate namespaces
- Do not modify another WS's namespace without orchestrator approval

## Provenance

When copying from reference:

```
docs/decisions.md entry:
- source: reference/coder-eks-deployment@abc1234
- files: terraform/eks/*
- changes: partition refactor, us-gov-west-1, auto_mode fallback
```
