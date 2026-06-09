# WS-23: GitLab to Coder agent attribution + PM persona

| Field | Value |
|---|---|
| **State key** | ws23.attribution |
| **Phase** | 2 |
| **Model** | **Sonnet** |
| **Depends on** | WS-05 (Coder), WS-06 (Keycloak), WS-10 (GitLab), WS-12 (identity), WS-25 (templates), WS-22 (Agent Firewall, recommended) |
| **Track** | Feature (authored + STAGED) |

## Goal

A project manager assigns a GitLab issue to a developer, and that assignment
spawns attributed Coder work owned by the assigned developer rather than a
shared bot: a plain workspace (`coder-workspace`) or an autonomous Coder AI-agent
task (`coder-agent`). Replicate the proven Red Hat Summit 2026 "bridge" service,
adapted to GitLab plus the Coder 2.34 Tasks API. Add the missing PM persona who
does the assigning.

## Scope

- Replicate the rhsummit bridge (`reference/demo-aigov-rhsummit-2026/services/
  bridge`) as a pure-stdlib in-cluster service, mapped to the verified Coder
  2.34 Tasks and workspace APIs and the GitLab webhook shapes.
- Author (do not apply) the PM persona installer, the GitLab webhook installer,
  and the in-cluster bridge manifests.
- Everything reversible and clearly STAGED. No live apply, no git, no cluster or
  GitLab or Coder or Keycloak or AWS mutation by this workstream.

## Deliverables

- `docs/architecture/gitlab-coder-agent-attribution.md` design with verified
  Coder source citations (trigger, bridge, attribution options i/ii/iii,
  idempotency, demo happy path, security surface).
- `scripts/setup-pm-persona.py` idempotent, `--plan` default: Keycloak user
  `morgan.pm` (Morgan Pierce), matching GitLab user, project membership on
  `coderdemo/coder-templates`.
- `scripts/setup-gitlab-agent-webhook.py` idempotent, `--plan` default: registers
  the Issue-events webhook, plus a `--simulate --issue N` no-bridge demo path.
- `deploy/coder/agent-attribution/` bridge.py, ExternalSecret, Deployment,
  Service, secrets.example.yaml, and a STAGED README with apply and rollback.
- `docs/swarm/handoffs/WS-23-handoff.md` status, apply commands, security
  checklist, verification, rollback.

## Recommended design decision

Replicate the rhsummit bridge, attributing via the Tasks `{user}` path
parameter. The bridge is an in-cluster Deployment in the `coder` namespace that
receives GitLab Issue events, gates on a coder-* label plus an assignee, and
spawns work owned by the assignee. Two modes mirror rhsummit (agent wins when
both labels are present): `coder-workspace[:tmpl]` calls
`POST /api/v2/users/{user}/workspaces`, and `coder-agent[:tmpl]` (alias
`coder-task`) calls `POST /api/v2/tasks/{user}`. Both endpoints set the owner
from the path parameter and authorize the caller for
`ResourceWorkspace.InOrg(org).WithOwner(owner)`, so one scoped service-account
token yields true per-developer ownership with no per-user token storage. Unlike
rhsummit's experimental-chat path, the Tasks API needs no per-user token
minting, and model selection moves from chatd model-configs into the AI-task
template.

## Acceptance criteria

- [ ] Design names the exact Coder API calls and the identity and permission
      needed, with file and line citations from `reference/coder`.
- [ ] Bridge replicates the rhsummit service responsibilities and structure,
      with provenance file paths and an explicit same-vs-adapted breakdown.
- [ ] Attribution options i, ii, iii compared; one recommended and justified.
- [ ] PM persona script is idempotent, `--plan` default, never logs secrets,
      creates Keycloak + GitLab user + project membership.
- [ ] Webhook script is idempotent, `--plan` default, registers the hook and can
      simulate both modes (Tasks and workspace) without a running bridge.
- [ ] Bridge manifests are minimal, STAGED, reversible, with ESO-backed
      secrets and no secret material in git.
- [ ] Idempotency prevents duplicate workspaces per issue.
- [ ] Security review items called out explicitly (token scope and blast radius,
      webhook authenticity and input trust, identity mapping integrity).
- [ ] No emdash, endash, or spaced double-hyphen in any authored file.

## Risk posture

- Authoring only. No applies. The service-account token, webhook secret, and
  GitLab PAT are created and stored by the operator at apply time, in ASM via
  ESO, never in git.
- The recommended design has a bounded blast radius (one org-scoped service
  account) and fails closed when a GitLab user does not map to a Coder user.

## Go / no-go

GO to author and STAGE. NO-GO on any live apply until the security checklist in
the handoff is approved by the user, since the service account can create
workspaces on behalf of other users and the webhook accepts external input.
