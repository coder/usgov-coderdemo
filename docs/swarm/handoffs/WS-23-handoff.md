# WS-23 handoff

- **Status:** AUTHORED / STAGED (nothing applied; root applies, then commits)
- **Agent:** WS-23 (GitLab to Coder agent attribution + PM persona)
- **Timestamp:** 2026-06-08T06:58:43Z
- **Git commit:** 4cb458979c05da731922931ca478bea72c2536f2 (read from worktree ref file; no git command run)
- **Branch:** ws-2x/phase2

## Reference commits read (nothing copied)

| Repo | SHA |
|------|-----|
| reference/coder | 47a8c9572f579913209edddfddd6c71c5546781b |
| reference/demo-aigov-rhsummit-2026 | (read-only; bridge replicated, no code copied) |

## Outputs (required for downstream)

| Key | Value |
|-----|-------|
| design decision | replicate the rhsummit bridge; attribute via Tasks/workspace `{user}` path param |
| trigger | GitLab Issue-events webhook, gated by a coder-* label + assignee |
| receiver | in-cluster Deployment `agent-attribution-bridge`, ns `coder` (`bridge.py`) |
| labels | `coder-workspace[:tmpl]`, `coder-agent[:tmpl]`, `coder-task` (alias of coder-agent) |
| attribution call | agent: `POST /api/v2/tasks/<assignee>`; workspace: `POST /api/v2/users/<assignee>/workspaces` (coder-task-bot token) |
| service account | `coder-task-bot` (custom role, org `coder` only) |
| template | `claude-code` active version (declares `coder_ai_task`) |
| PM persona | Morgan Pierce, `morgan.pm` (Keycloak realm `coder` + GitLab) |
| project | `coderdemo/coder-templates` (id 2), group `coderdemo` (id 13) |
| ASM secret | `usgov-coderdemo/agent-attribution/bridge` (coder-token, webhook-secret, gitlab-pat) |
| ESO store | `ClusterSecretStore/aws-secretsmanager` |
| design doc | `docs/architecture/gitlab-coder-agent-attribution.md` |

## Files authored (this workstream only)

- `docs/architecture/gitlab-coder-agent-attribution.md`
- `docs/swarm/workstreams/WS-23-attribution-persona.md`
- `docs/swarm/handoffs/WS-23-handoff.md` (this file)
- `scripts/setup-pm-persona.py`
- `scripts/setup-gitlab-agent-webhook.py`
- `deploy/coder/agent-attribution/` (bridge.py, externalsecret.yaml,
  deployment.yaml, service.yaml, secrets.example.yaml, README.md)

## EXACT ordered apply commands (root, after the security review is approved)

```sh
. ~/.config/usgov-coderdemo/env
export KUBECONFIG=/home/coder/demoenv-workspace/usgov-coderdemo/kubeconfig
export PATH="$HOME/.local/bin:$PATH"
cd /home/coder/demoenv-workspace/usgov-phase2

# 0. Review plans, read-only, mutate nothing
python3 scripts/setup-pm-persona.py
python3 scripts/setup-gitlab-agent-webhook.py

# 1. PM persona (Keycloak + GitLab + project membership)
python3 scripts/setup-pm-persona.py --apply

# 2. Prerequisites for the bridge (see deploy/coder/agent-attribution/README.md)
#    - create the coder-task-bot service account + least-privilege org role + token
#    - generate the webhook shared secret; reuse the GitLab admin PAT
#    - store all three in ASM usgov-coderdemo/agent-attribution/bridge (JSON)
#    - mirror docker.io/library/python:3.12-slim into ECR

# 3. Deploy the bridge
cd deploy/coder/agent-attribution
kubectl create configmap agent-attribution-receiver -n coder \
  --from-file=bridge.py=./bridge.py \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f externalsecret.yaml
kubectl -n coder get externalsecret agent-attribution-bridge      # SecretSynced=True
kubectl apply -f service.yaml
kubectl apply -f deployment.yaml
kubectl -n coder rollout status deploy/agent-attribution-bridge --timeout=120s

# 4. Register the GitLab webhook (in-cluster Service URL by default)
cd /home/coder/demoenv-workspace/usgov-phase2
python3 scripts/setup-gitlab-agent-webhook.py --apply
```

All scripts default to a read-only plan; they mutate only with `--apply`. The
GitLab webhook registration refuses to create a hook without a shared secret.

## Security review checklist (USER MUST APPROVE BEFORE GOING LIVE)

- [ ] Service-account scope. `coder-task-bot` has a least-privilege custom role
      (workspace create, template read, organization member read) bound to org
      `coder` only, not site Owner. Confirm the token lifetime and rotation plan,
      ASM + ESO storage, and that nothing logs the token.
- [ ] Blast radius understood. The token can create workspaces owned by any user
      in org `coder`. Acceptable for the demo, documented, and revocable.
- [ ] Webhook authenticity. The hook uses a strong shared secret over the chosen
      transport (in-cluster Service URL, or https via ingress). The bridge
      compares `X-Gitlab-Token` in constant time and rejects mismatches.
- [ ] Input trust. The issue body becomes the agent prompt. The agent runs under
      the WS-22 Agent Firewall egress sandbox and the AI Gateway; the
      service-account token is never exposed to the agent workspace. Duplicate
      and flood protection via the deterministic name and existence check.
- [ ] Identity mapping. GitLab username equals Coder username (both from Keycloak
      realm `coder`). Unmapped users fail closed, never fall back to a shared bot
      owner. The assignee has signed into Coder at least once.
- [ ] GitLab local-network webhook setting. If targeting the in-cluster Service
      URL, the admin setting "Allow requests to the local network from webhooks"
      is enabled deliberately, or the bridge is exposed via ingress instead.

## Verification (root, after apply)

- [ ] `python3 scripts/setup-pm-persona.py` plan is clean; after apply,
      `morgan.pm` can sign into `https://dev.usgov.coderdemo.io` and is a member
      of project 2 in GitLab.
- [ ] `kubectl -n coder get externalsecret agent-attribution-bridge` is
      `SecretSynced=True` and the Deployment is Running.
- [ ] Bridge `/readyz` returns 200 in-cluster.
- [ ] End to end: PM assigns an issue in `coderdemo/coder-templates` with a
      coder-* label (`coder-agent` for an AI task, `coder-workspace` for a plain
      workspace); a workspace appears under the assignee (not a bot), and the
      bridge comments back on the issue.
- [ ] No-bridge path: `setup-gitlab-agent-webhook.py --simulate --issue N`
      prints the exact attributed call (Tasks for agent mode,
      users/workspaces for workspace mode); `--apply` creates it owned by the
      assignee.

## Validation done by WS-23 (authoring only)

- [x] `python3 -m py_compile` on both scripts and the bridge.
- [x] Coder Tasks API surface verified against `reference/coder` with file and
      line citations in the design doc.
- [x] In-cluster Coder Service (`coder.coder.svc.cluster.local:80`) and ESO
      `ClusterSecretStore/aws-secretsmanager` confirmed by read-only `kubectl`.
- [x] dash-scan: no emdash (U+2014), endash (U+2013), or spaced double-hyphen in
      any authored file.

## Blockers

- None for authoring. Apply is blocked on the security review approval above and
  on the operator creating the `coder-task-bot` service account, token, webhook
  secret, and ASM entry (the agent cannot mint Coder service-account tokens).

## Notes for orchestrator

- Nothing was applied. No git command was run by this agent.
- The bridge is intentionally a stock-image plus ConfigMap (no build step), so
  the whole feature reverts by deleting the Deployment, Service, ConfigMap, and
  ExternalSecret, removing the GitLab hook, and revoking the service-account
  token.
- The bridge replicates `reference/demo-aigov-rhsummit-2026/services/bridge`;
  the `bridge.py` header documents, file by file, what is the same as rhsummit
  and what was adapted for GitLab + Coder 2.34.
- The stable Tasks API accepts the owner as a path
  parameter, so unlike the Red Hat Summit chat path it needs no per-user token
  minting. If a future flow uses the experimental chat endpoint instead, fall
  back to attribution option i (mint a per-user token). `coder-agent:<slug>`
  selects a template here, not a chatd model (Tasks does not expose model
  configs); CreateTaskRequest carries no rich parameters, so the issue context
  rides in the seed prompt (`input` -> the template's `ai_prompt`).
