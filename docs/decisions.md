# Decisions and reference provenance

Append-only log of decisions and of code copied/adapted from `$REFERENCE_ROOT`
(the read-only reference clones). Each sub-agent also records its provenance in
its `docs/swarm/handoffs/WS-NN-handoff.md`; the orchestrator consolidates here.

## Reference clones (SHAs at the start of the Phase-2 wave)
| Repo | SHA |
|------|-----|
| reference/coder | 47a8c9572f |
| reference/demo-aigov-rhsummit-2026 | da48a48 |
| reference/observability | 863d498 |

## Phase-2 decisions

### Recreation: coderdemo/coder-templates on UBI9 (fold-in)
- source: reference/demo-aigov-rhsummit-2026@da48a48
- files: coder-templates/images/ubi9-base-workspace/{Dockerfile,uid_entrypoint.sh},
  coder-templates/images/ubi9-node-workspace/Dockerfile
- changes: reused the UBI9 base + node Dockerfiles for the GitLab CI build; built
  with Kaniko in the gitlab-runner namespace and pushed to the
  coderdemo/coder-templates GitLab Container Registry; rewrote 19 emdashes and a
  literal spaced double hyphen out of the reference Dockerfiles to satisfy
  make lint/emdash; the starship install step was changed to download-then-run.
- decision: NOT a strict air gap. GovCloud/CUI can egress to the internet
  (verified the gitlab-runner namespace reaches registry.access.redhat.com,
  EPEL, NodeSource, Rocky, starship.rs), so the UBI dnf/npm builds run directly.
  ECR mirroring is a performance/reliability choice, not a hard requirement.
- decision: the coder-templates project lives at coderdemo/coder-templates (group
  coderdemo, austen.platform Owner); the runner is a coderdemo GROUP runner. The
  prior root/coder-templates project was deleted.

### Realm name
- The live identity realm is "coder" (per docs/as-built/45-idp-sync-personas.md
  and the Phase-2 tasking), not "usgov" as written in the Phase-1
  docs/decisions-locked.md. The live system is authoritative.

## WS-2x provenance (consolidated from handoffs)
- WS-20: see docs/swarm/handoffs/WS-20-handoff.md
- WS-21: see docs/swarm/handoffs/WS-21-handoff.md
- WS-22: see docs/swarm/handoffs/WS-22-handoff.md
- WS-24: see docs/swarm/handoffs/WS-24-handoff.md (upstream reference/observability@863d498)
- WS-25: see docs/swarm/handoffs/WS-25-handoff.md
