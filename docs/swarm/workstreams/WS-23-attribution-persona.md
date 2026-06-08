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
spawns a Coder AI-agent workspace (a Coder Task) that does the work, owned by and
attributed to the assigned developer rather than a shared bot. Add the missing PM
persona who does the assigning.

## Scope

- Design the trigger, receiver, and attribution model against the verified Coder
  2.34 Tasks API and the Red Hat Summit bridge reference.
- Author (do not apply) the PM persona installer, the GitLab webhook installer,
  and the in-cluster receiver manifests.
- Everything reversible and clearly STAGED. No live apply, no git, no cluster or
  GitLab or Coder or Keycloak or AWS mutation by this workstream.

## Deliverables

- `docs/architecture/gitlab-coder-agent-attribution.md` design with verified
  Coder source citations (trigger, receiver, attribution options i/ii/iii,
  idempotency, demo happy path, security surface).
- `scripts/setup-pm-persona.py` idempotent, `--plan` default: Keycloak user
  `morgan.pm` (Morgan Pierce), matching GitLab user, project membership on
  `coderdemo/coder-templates`.
- `scripts/setup-gitlab-agent-webhook.py` idempotent, `--plan` default: registers
  the Issue-events webhook, plus a `--simulate --issue N` no-receiver demo path.
- `deploy/coder/agent-attribution/` receiver.py, ExternalSecret, Deployment,
  Service, secrets.example.yaml, and a STAGED README with apply and rollback.
- `docs/swarm/handoffs/WS-23-handoff.md` status, apply commands, security
  checklist, verification, rollback.

## Recommended design decision

Service-account-on-behalf-of via the Tasks `{user}` path parameter. The 2.34
Tasks API (`POST /api/v2/tasks/{user}`) natively sets the workspace owner to the
named user and authorizes the caller for
`ResourceWorkspace.InOrg(org).WithOwner(owner)`, so one scoped service-account
token yields true per-developer ownership with no per-user token storage. The
trigger is a GitLab Issue-events webhook gated by the `coder-task` label plus an
assignee; the receiver is a tiny in-cluster Deployment in the `coder` namespace.

## Acceptance criteria

- [ ] Design names the exact Coder API calls and the identity and permission
      needed, with file and line citations from `reference/coder`.
- [ ] Attribution options i, ii, iii compared; one recommended and justified.
- [ ] PM persona script is idempotent, `--plan` default, never logs secrets,
      creates Keycloak + GitLab user + project membership.
- [ ] Webhook script is idempotent, `--plan` default, registers the hook and can
      simulate the flow without a running receiver.
- [ ] Receiver manifests are minimal, STAGED, reversible, with ESO-backed
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
