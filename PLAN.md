# usgov-coderdemo build plan

**Repo:** [github.com/coder/usgov-coderdemo](https://github.com/coder/usgov-coderdemo)  
**Region:** `us-gov-west-1` | **Domain:** `usgov.coderdemo.io`

This file is the entry point. Detailed instructions live in `docs/`.

## Orchestrator start here

→ **[docs/swarm/ORCHESTRATOR.md](docs/swarm/ORCHESTRATOR.md)**

## Quick reference

| Doc | Purpose |
|---|---|
| [docs/PRE-REQUISITES.md](docs/PRE-REQUISITES.md) | **Human setup** — env, clone URLs, tools |
| [scripts/preflight-readiness.sh](scripts/preflight-readiness.sh) | Verify/clone prerequisites (exit 0 before orch) |
| [docs/AGENT-PRD.md](docs/AGENT-PRD.md) | **Agent entry** — dense PRD (orch + subagents) |
| [decisions-locked.md](docs/decisions-locked.md) | Non-negotiable architecture choices |
| [swarm/RULES.md](docs/swarm/RULES.md) | Agent behavior rules |
| [swarm/GATES.md](docs/swarm/GATES.md) | Phase 0 go/no-go checks |
| [swarm/PARALLELISM.md](docs/swarm/PARALLELISM.md) | Waves, concurrency, state keys |
| [swarm/CONNECTIVITY.md](docs/swarm/CONNECTIVITY.md) | C1–C14 validation matrix |
| [swarm/CREDENTIALS.md](docs/swarm/CREDENTIALS.md) | Env vars and pre-flight |
| [swarm/PHASE-1-SUCCESS.md](docs/swarm/PHASE-1-SUCCESS.md) | Overnight done criteria |
| [swarm/MODELS.md](docs/swarm/MODELS.md) | Opus 4.8/Sonnet/Haiku + effort per WS |
| [architecture/overview.md](docs/architecture/overview.md) | Target architecture |
| [repo-layout.md](docs/repo-layout.md) | Directory tree to scaffold |
| [swarm/workstreams/](docs/swarm/workstreams/) | Per-WS subagent prompts |

## Phase 1 critical path

```
GATE-0 → WS-01 → WS-02 → WS-03 → WS-04 → WS-05 → WS-07 → WS-08 → validate-track-a
```

WS-06 Keycloak may parallel WS-05. WS-11 OCP IPI starts after WS-02 (background).
