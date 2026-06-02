# Orchestrator instructions

You are the **top-level Claude Code orchestrator**. Coordinate subagents; do not implement workstreams yourself unless retrying a failed WS once.

## Startup

```bash
cd ~/demoenv-workspace/usgov-coderdemo
source ~/.config/usgov-coderdemo/env   # or source .env
export KUBECONFIG=$PWD/kubeconfig
export REFERENCE_ROOT=${REFERENCE_ROOT:-../reference}
```

## Bootstrap sequence

0. Human: `preflight-readiness.sh` exit 0 (see [PRE-REQUISITES.md](../PRE-REQUISITES.md))
1. Confirm layout: repo + `$REFERENCE_ROOT/{coder-eks-deployment,demo-aigov-rhsummit-2026,homelab,openshift-servicemesh-inventory-demo}`
2. If repo empty → launch **WS-00** (scaffold), merge, commit
3. Run `make gate-0` → **non-zero = STOP**
4. Pin Coder version in `versions.lock.yaml` (G0.7)
5. Create `docs/swarm/handoffs/` and `docs/swarm/SWARM-STATUS.md` from [templates](../templates/)
6. Execute waves per [PARALLELISM.md](PARALLELISM.md)
7. After WS-08 → `make validate-track-a` → [PHASE-1-SUCCESS.md](PHASE-1-SUCCESS.md)
8. Launch Track B (WS-09–13) per parallelism doc

## Model and effort selection

Assign **model** and **effort** per subagent from **[MODELS.md](MODELS.md)** before launch. Match effort to task complexity — uncapped API does not mean max everywhere. Requires Claude Code **v2.1.154+** (Opus 4.8, ultracode, dynamic workflows).

| Tier | Model | Effort | When |
|---|---|---|---|
| **Orchestrator** | Opus 4.8 | **ultracode** | Wave scheduling, parallel subagent coordination |
| **Opus critical path** | Opus 4.8 | **xhigh** | WS-04, 05, 07, 09, 11a/c/d |
| **Sonnet apply** | Sonnet 4.6 | **high** | Most TF/Helm/templates (WS-01–03, 06, 08, 10, 12–13) |
| **Sonnet bulk copy** | Sonnet 4.6 | **medium** | Large manifest trees (WS-11b, parallel copy SAs) |
| **Haiku fast** | Haiku | — | GATE-0 probes, empty stubs, literal doc copy |
| **Escalation** | Opus 4.8 | **max** | Failed apply retry, Istio/C4 debug, blocked critical path |

Orchestrator startup:

```bash
claude --model opus --effort ultracode
```

## Subagent launch prompt

Copy and fill for each subagent:

```
Model: <Opus 4.8|Sonnet|Haiku>  # see docs/swarm/MODELS.md WS-NN row
Effort: <high|xhigh>   # max on retry only; ultracode = orchestrator; omit for Haiku

You are subagent WS-NN for usgov-coderdemo GovCloud build.

Read (in order):
1. docs/swarm/RULES.md
2. docs/decisions-locked.md
3. docs/swarm/workstreams/WS-NN-*.md
4. Upstream handoffs: [list paths]

Environment:
  cd ~/demoenv-workspace/usgov-coderdemo
  source ~/.config/usgov-coderdemo/env
  export KUBECONFIG=$PWD/kubeconfig

Constraints:
- Never edit $REFERENCE_ROOT/
- You own terraform state key: [KEY]
- One terraform apply at a time in your module
- Write docs/swarm/handoffs/WS-NN-handoff.md (use template)
- git commit on branch ws-NN/: "ws-NN: summary"

Execute your workstream now. On FAIL stop and document blockers.
```

## Git strategy

- Branch: `ws-NN/short-description`
- Orchestrator merges to `main` after handoff PASS
- Resolve conflicts in favor of upstream WS dependencies

## Concurrency

| Resource | Max parallel |
|---|---|
| TF applies (all) | 3–4 |
| EKS helm/kubectl | 1–2 |
| Code-only agents | unlimited |

## Critical path (serial applies)

```
GATE-0 → WS-01 → WS-02 → WS-03 → WS-04 → WS-05 → WS-07 → WS-08
```

WS-06 may parallel WS-05. WS-11a may start after WS-02 (background).

## Status tracking

Update `docs/swarm/SWARM-STATUS.md` after every wave. Collect all handoffs in `docs/swarm/handoffs/`.

## Retry policy

Max **1 retry per WS per night**. No `terraform force-unlock` without explicit approval logged in SWARM-STATUS.

## Related docs

- [PARALLELISM.md](PARALLELISM.md)
- [GATES.md](GATES.md)
- [PHASE-1-SUCCESS.md](PHASE-1-SUCCESS.md)
- [workstreams/](workstreams/)
