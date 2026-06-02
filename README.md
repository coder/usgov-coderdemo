# usgov-coderdemo

GovCloud Coder demo environment — agent swarm docs + infrastructure (see [PLAN.md](PLAN.md)).

**Region:** `us-gov-west-1` | **Domain:** `usgov.coderdemo.io`

## Pre-requisites (human, first)

1. [docs/PRE-REQUISITES.md](docs/PRE-REQUISITES.md) — workspace layout, env, reference clone URLs
2. `./scripts/preflight-readiness.sh --clone` then `./scripts/preflight-readiness.sh` (exit 0)

## Workspace layout

```text
~/demoenv-workspace/
├── usgov-coderdemo/    # this repo (WRITE)
└── reference/          # read-only upstream clones
```

```bash
mkdir -p ~/demoenv-workspace && cd ~/demoenv-workspace
git clone git@github.com:coder/usgov-coderdemo.git
mkdir -p reference
```

## Who reads what

| Role | Read first | Then |
|---|---|---|
| **Orchestrator** | [docs/AGENT-PRD.md](docs/AGENT-PRD.md) + [docs/swarm/ORCHESTRATOR.md](docs/swarm/ORCHESTRATOR.md) | per-WS workstream on spawn |
| **Subagent WS-N** | AGENT-PRD WS_INDEX row + [docs/swarm/workstreams/WS-NN-*.md](docs/swarm/workstreams/) | upstream handoffs |
| **All agents** | [docs/swarm/RULES.md](docs/swarm/RULES.md) | [docs/decisions-locked.md](docs/decisions-locked.md) |

## Orchestrator bootstrap

1. `docs/decisions-locked.md`
2. `docs/PRE-REQUISITES.md` + `preflight-readiness.sh`
3. `docs/swarm/GATES.md` — `make gate-0` (after WS-00)
4. `docs/swarm/ORCHESTRATOR.md`
5. `docs/swarm/MODELS.md`
6. `docs/swarm/PARALLELISM.md`
7. Fan out `docs/swarm/workstreams/WS-*.md`

## Runtime

- Claude Code in `tmux`, cwd = `usgov-coderdemo/`
- `source ~/.config/usgov-coderdemo/env` before AWS commands
- Phase 1 success = [docs/swarm/PHASE-1-SUCCESS.md](docs/swarm/PHASE-1-SUCCESS.md)
