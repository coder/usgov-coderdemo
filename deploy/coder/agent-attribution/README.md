# Agent attribution receiver (WS-23), STAGED

A tiny in-cluster receiver that turns a GitLab issue assignment into a Coder Task
owned by and attributed to the assigned developer. Nothing here is applied
automatically. The design and rationale live in
`docs/architecture/gitlab-coder-agent-attribution.md`.

## Contents

| File | Purpose |
|---|---|
| `receiver.py` | Pure-stdlib webhook receiver, mounted from a ConfigMap |
| `externalsecret.yaml` | ESO sync of the receiver credentials from ASM |
| `deployment.yaml` | Receiver Deployment (stock python image from ECR) |
| `service.yaml` | ClusterIP Service on port 8080 |
| `secrets.example.yaml` | Shape of the ASM secret (no real values) |

## What it does

For each GitLab Issue event the receiver acts only when the issue has the
`coder-task` label AND an assignee. It confirms the assignee maps to a Coder
user, then creates a Coder Task on the `claude-code` template version with
`POST /api/v2/tasks/<assignee>`. The workspace owner is the assignee. Repeat
deliveries and issue edits are a no-op once the workspace exists (deterministic
name `<repo>-issue-<iid>`). The author or actor is never used as the owner.

## Prerequisites (operator, before apply)

1. Coder service account and least-privilege role. Create a dedicated user
   `coder-task-bot` (login type none) and bind a custom role in org `coder`
   (`5de29a6d-8836-4643-a42b-2cb807c8e3e2`) granting workspace create, template
   read, and organization member read. A coarser fallback is Organization Admin
   of org `coder` only. Never grant site Owner. Mint a token for it (for example
   `POST /api/v2/users/coder-task-bot/keys/tokens`). This token is sensitive;
   see the security checklist in the WS-23 handoff.
2. Webhook shared secret. Generate a random secret (for example
   `openssl rand -hex 24`). The same value goes into both the ASM secret and the
   GitLab webhook.
3. GitLab admin PAT. Used only for the best-effort issue comment back. Reuse the
   repo PAT pattern (env or ASM `usgov-coderdemo/gitlab/admin-pat`).
4. Store all three in ASM as one JSON object (see `secrets.example.yaml`):

   ```sh
   # never echo the values; write them to a 0600 file first
   aws secretsmanager create-secret --region us-gov-west-1 \
     --name usgov-coderdemo/agent-attribution/bridge \
     --secret-string file:///path/to/bridge.json
   ```

5. Mirror the receiver image into ECR (GovCloud has no pull-through cache):

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

# 1. Generate the receiver ConfigMap from receiver.py
kubectl create configmap agent-attribution-receiver -n coder \
  --from-file=receiver.py=./receiver.py \
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
in-cluster Service URL, or expose the receiver through ingress and pass an
https URL with `python3 scripts/setup-gitlab-agent-webhook.py --url https://... --apply`.

## Verify

```sh
# receiver health (in-cluster): port-forward, then curl locally
kubectl -n coder port-forward deploy/agent-attribution-bridge 8080:8080 &
curl -fsS http://127.0.0.1:8080/readyz   # expect {"ok": true}

# end to end: PM assigns an issue with the coder-task label, then confirm a
# workspace appears under the assignee (not a bot):
#   open + assign an issue in coderdemo/coder-templates, add label coder-task
#   the receiver creates a task owned by the assignee and comments back
```

No-receiver demo path (before rollout):

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
