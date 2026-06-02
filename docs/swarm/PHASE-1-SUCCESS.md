# Phase 1 success criteria

Phase 1 PASS = overnight success line. Orchestrator declares this before launching Track B.

## Required handoffs PASS

| WS | Minimum status |
|---|---|
| WS-01 Bootstrap | PASS |
| WS-02 Network | PASS |
| WS-03 Data | PASS |
| WS-04 EKS | PASS |
| WS-05 Coder | PASS |
| WS-06 Keycloak | PASS or PARTIAL (OIDC wired, login may need polish) |
| WS-07 Day2 | PASS |
| WS-08 Templates | PASS |

## Required connectivity

`make validate-track-a` exits 0:

- [ ] C1 Coder UI TLS
- [ ] C4 workspace agent connected
- [ ] C3 workspace app URL
- [ ] C5 EKS workspace proxy
- [ ] C9 Keycloak login (or documented bootstrap admin fallback)
- [ ] C13 ECR pull in workspace
- [ ] C14 pull-through / devcontainer base

C2 (terminal) strongly recommended; treat FAIL as PARTIAL not block if C4 passes.

## User-visible outcome

1. Browse to `https://dev.usgov.coderdemo.io`
2. Log in
3. Create workspace from EKS template
4. Workspace reaches Connected
5. Launch workspace app

## Not required for Phase 1

- Istio (WS-09)
- GitLab (WS-10)
- OCP cluster ready (WS-11 may still be running)
- Full identity sync (WS-12)
- Bedrock (WS-13)
- Grafana (may defer with observability)

## Document

Orchestrator updates `docs/swarm/SWARM-STATUS.md`:

```markdown
## Phase 1: PASS | FAIL
Timestamp:
validate-track-a exit code:
Blockers:
```
