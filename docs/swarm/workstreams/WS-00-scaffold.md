# WS-00 — Scaffold

| Field | Value |
|---|---|
| **State key** | none (no apply) |
| **Phase** | 0 |
| **Model** | **Sonnet** (Haiku for empty TF stubs only) |
| **Depends on** | GATE-0 repo check G0.12 |
| **Blocks** | all other WS |

## Goal

Create repo skeleton so parallel agents share one layout.

## Parallel subagents (orchestrator may fan out)

| SA | Creates |
|---|---|
| SA-S0-ROOT | README, .gitignore, .env.example, versions.lock.yaml |
| SA-S0-MAKE | Makefile, scripts/lib/common.sh |
| SA-S0-GATE | scripts/gate-0-check.sh |
| SA-S0-VALID | scripts/validate-connectivity.sh |
| SA-S0-TFAP | scripts/tf-apply.sh |
| SA-S0-PART | terraform/modules/partition/ |
| SA-S0-TF-* | empty main.tf + variables per terraform/* root |
| SA-S0-DOCS | docs/architecture/, docs/decisions.md stub |
| SA-S0-RB | docs/runbooks/ (copy from pack if missing) |

Copy agent doc pack from human if not already in repo.

## Must create

- Full tree per [repo-layout.md](../../repo-layout.md)
- `docs/swarm/handoffs/` directory (empty)
- `docs/swarm/SWARM-STATUS.md` from [template](../../templates/swarm-status-template.md)
- Copy `docs/swarm/workstreams/` if not present

## Must NOT

- Run terraform apply (except `terraform validate` locally OK)
- Copy reference repo content into modules yet (that's SA-COPY-* in Wave 3b)

## Handoff outputs

| Key | Value |
|---|---|
| `scaffold_commit` | git SHA |
| `makefile_targets` | list |

## Validation

- [ ] `make gate-0` runs (may fail gates — that's OK)
- [ ] all terraform roots exist
- [ ] .gitignore covers .env, kubeconfig, .terraform

## Reference

[repo-layout.md](../../repo-layout.md)
