# GitLab to Coder bridge (WS-23), STAGED

A tiny in-cluster service that turns a GitLab issue into a Coder workspace or an
attributed Coder AI-agent task, owned by the assigned developer. Nothing here is
applied automatically. The design and rationale live in
`docs/architecture/gitlab-coder-agent-attribution.md`.

This is a pure standard-library re-implementation of the Red Hat Summit 2026
demo bridge (`reference/demo-aigov-rhsummit-2026/services/bridge`), adapted for
self-hosted GitLab and the stable Coder 2.34 Tasks API. The header of
`bridge.py` lists, file by file, what is the same as rhsummit and what was
adapted.

## Contents

| File | Purpose |
|---|---|
| `bridge.py` | Pure-stdlib GitLab to Coder bridge, mounted from a ConfigMap |
| `externalsecret.yaml` | ESO sync of the bridge credentials from ASM |
| `deployment.yaml` | Bridge Deployment (stock python image from ECR) |
| `service.yaml` | ClusterIP Service on port 8080 |
| `secrets.example.yaml` | Shape of the ASM secret (no real values) |

## What it does

For each GitLab Issue event the bridge acts only when the issue carries a
`coder-*` label AND an assignee, and the action is `open`, `update`, or
`reopen`. The first assignee is the attribution target; the actor or author is
never used as the owner. Two label modes, mirroring rhsummit (agent wins when
both are present):

| Label | Action |
|---|---|
| `coder-workspace` | Create a plain workspace on the default template (`claude-code`), owned by the assignee, via `POST /api/v2/users/<assignee>/workspaces`. The developer opens it. |
| `coder-workspace:<template>` | Same, using the named Coder template. |
| `coder-agent` | Dispatch an autonomous AI task on the default template via `POST /api/v2/tasks/<assignee>`. The workspace and agent are owned by the assignee. |
| `coder-agent:<template>` | Same, using the named AI-task template. |
| `coder-task[:<template>]` | Alias of `coder-agent`, retained for continuity. |

The workspace name is deterministic, `<repo>-issue-<iid>`, so repeat deliveries
and issue edits are a no-op once the workspace exists. The bridge confirms the
assignee maps to a Coder user and fails closed if not. For agent mode the GitLab
issue title and body are folded into the task's seed prompt (the `input` that
the `claude-code` template surfaces as its `ai_prompt`).

Endpoints: `POST /webhook`, `GET /healthz` (always 200), `GET /readyz` (200 when
Coder is reachable, else 503).

## Prerequisites (operator, before apply)

1. Coder service account and least-privilege role. Create a dedicated user
   `coder-task-bot` (login type none) and bind a custom role in org `coder`
   (`5de29a6d-8836-4643-a42b-2cb807c8e3e2`) granting workspace create, template
   read, and organization member read. A coarser fallback is Organization Admin
   of org `coder` only. Never grant site Owner. Mint a token for it (for example
   `POST /api/v2/users/coder-task-bot/keys/tokens`). This token is sensitive;
   see the security checklist in the WS-23 handoff. The same token serves both
   modes, because the Tasks and workspace endpoints take the owner as a path
   parameter (no per-user token minting, unlike the rhsummit chat path).
2. Webhook shared secret. Generate a random secret (for example
   `openssl rand -hex 24`). The same value goes into both the ASM secret and the
   GitLab webhook.
3. GitLab admin PAT. Used to read the issue body and post the comment back.
   Reuse the repo PAT pattern (env or ASM `usgov-coderdemo/gitlab/admin-pat`).
4. Store all three in ASM as one JSON object (see `secrets.example.yaml`):

   ```sh
   # never echo the values; write them to a 0600 file first
   aws secretsmanager create-secret --region us-gov-west-1 \
     --name usgov-coderdemo/agent-attribution/bridge \
     --secret-string file:///path/to/bridge.json
   ```

5. Mirror the runtime image into ECR (GovCloud has no pull-through cache):

   ```sh
   crane copy docker.io/library/python:3.12-slim \
     <acct>.dkr.ecr.us-gov-west-1.amazonaws.com/docker-hub/library/python:3.12-slim
   ```

## Apply (operator)

```sh
. ~/.config/usgov-coderdemo/env
export KUBECONFIG=/home/coder/demoenv-workspace/usgov-coderdemo/kubeconfig
export PATH="$HOME/.local/bin:$PATH"
cd /home/coder/demoenv-workspace/usgov-phase2/deploy/coder/agent-attribution

# 1. Generate the bridge ConfigMap from bridge.py
kubectl create configmap agent-attribution-receiver -n coder \
  --from-file=bridge.py=./bridge.py \
  --dry-run=client -o yaml | kubectl apply -f -

# 2. Sync the credentials, then the workloads
kubectl apply -f externalsecret.yaml
kubectl -n coder get externalsecret agent-attribution-bridge   # SecretSynced=True
kubectl apply -f service.yaml
kubectl apply -f deployment.yaml
kubectl -n coder rollout status deploy/agent-attribution-bridge --timeout=120s

# 3. Register the GitLab webhook (defaults to the in-cluster Service URL)
cd /home/coder/demoenv-workspace/usgov-phase2
python3 scripts/setup-gitlab-agent-webhook.py --apply
```

GitLab blocks webhooks to in-cluster addresses by default. Either enable the
admin setting "Allow requests to the local network from webhooks" and keep the
in-cluster Service URL, or expose the bridge through ingress and pass an https
URL with `python3 scripts/setup-gitlab-agent-webhook.py --url https://... --apply`.

## Verify

```sh
# bridge health (in-cluster): port-forward, then curl locally
kubectl -n coder port-forward deploy/agent-attribution-bridge 8080:8080 &
curl -fsS http://127.0.0.1:8080/readyz   # expect {"ok": true}

# end to end: PM assigns an issue with a coder-* label, then confirm a
# workspace appears under the assignee (not a bot):
#   open + assign an issue in coderdemo/coder-templates
#   add label coder-agent  (autonomous task) or coder-workspace (plain workspace)
#   the bridge creates the workspace/task owned by the assignee and comments back
```

No-bridge demo path (before rollout):

```sh
python3 scripts/setup-gitlab-agent-webhook.py --simulate --issue <iid>          # print
python3 scripts/setup-gitlab-agent-webhook.py --simulate --issue <iid> --apply  # send
```

## Rollback

```sh
kubectl -n coder delete deploy/agent-attribution-bridge svc/agent-attribution-bridge
kubectl -n coder delete configmap agent-attribution-receiver
kubectl -n coder delete externalsecret agent-attribution-bridge
# remove the GitLab hook in the project settings, and revoke the coder-task-bot token
```
