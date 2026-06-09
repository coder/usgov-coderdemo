# Claude Code on Coder Agents (CI / UBI9 demo template)

Coder workspace template that runs **Claude Code as a Coder Agent** inside a
Kubernetes pod on the EKS cluster, wired through the **Coder AI Gateway (AI
Bridge)**. The workspace never holds a raw Anthropic API key: every request is
proxied through Coder using the workspace owner's session token and routed to
the configured provider (Anthropic-direct primary, Bedrock secondary)
in-boundary.

Launching the template as a **Coder Task** opens the Claude Code chat UI and
seeds the agent with the task prompt.

- `main.tf`: the template (providers `coder` + `kubernetes`).
- `metadata.json`: `display_name` + `icon`, applied post-push by the
  `push-template` CI job (`coder templates edit`).
- Workspace image: `ubi9-node-workspace:latest`, built by this project's GitLab
  CI pipeline (Kaniko) and pushed to the project's GitLab Container Registry.

## Workspace image and securityContext

The image is the CI-built **`<image_registry>/ubi9-node-workspace:latest`**,
where the `push-template` job sets `image_registry=$CI_REGISTRY_IMAGE`
(`registry.usgov.coderdemo.io/coderdemo/coder-templates`). The image:

- runs as **uid 1001** (user `coder`),
- owns `/home/coder` by **group 0**, group-writable (`chgrp -R 0` + `chmod -R
  g=u`).

The pod therefore sets `run_as_user = 1001`, `run_as_group = 0`, and
`fs_group = 0`, so the mounted `/home` PVC lands on group 0 (group-writable) and
the Coder agent can write `/home/coder` on EKS. The container command wraps the
agent init script in the image's `uid_entrypoint`, which normalizes `HOME`/`USER`.

> The project's Container Registry is private, so a real workspace boot needs a
> `kubernetes.io/dockerconfigjson` pull Secret in `var.namespace`; set its name
> via `image_pull_secret`. Template import (`terraform plan`) does not pull the
> image, so the default empty value is fine for CI import and verification.

## What's inside

| Piece | Resource | Notes |
|---|---|---|
| Agent | `coder_agent.main` | startup script, metadata, `display_apps` (VS Code Desktop, web terminal, SSH) |
| Claude Code | `module.claude_code` (`registry.coder.com/coder/claude-code/coder` **4.7.3**) | `enable_aibridge = true`, bundles AgentAPI + Claude Code web app, outputs `task_app_id` |
| Coder Task | `coder_ai_task.claude_code` | binds the Task UI to the Claude Code app; only created in a Task context |
| Browser IDE | `module.code_server` (`code-server` 1.3.1) | extra `coder_app` tile |
| Compute | `kubernetes_pod_v1.workspace` + `kubernetes_persistent_volume_claim_v1.home` | sizing from `cpu` / `memory` / `disk_size` parameters |
| AI auth | `coder_env.anthropic_auth_token` | exports `ANTHROPIC_AUTH_TOKEN` = session token |

Parameters: `cpu`, `memory`, `disk_size`, and `ai_prompt` (fallback prompt for
non-Task builds).

Variables: `namespace` (default `coder-workspaces`), `image_registry` (set to
`$CI_REGISTRY_IMAGE` by CI), `image_pull_secret` (default empty), and
`use_kubeconfig` (default `false`).

## AI Gateway wiring (end to end)

1. The `claude_code` module is configured with `enable_aibridge = true`. On the
   agent it sets:
   - `ANTHROPIC_BASE_URL = <access_url>/api/v2/aibridge/anthropic`
   - `CLAUDE_API_KEY = <workspace owner session token>`

   With `CODER_ACCESS_URL=https://dev.usgov.coderdemo.io` the base URL resolves
   to `https://dev.usgov.coderdemo.io/api/v2/aibridge/anthropic`.
2. This template additionally exports `ANTHROPIC_AUTH_TOKEN` (the same session
   token) to match the AI Gateway client contract in `deploy/CONVENTIONS.md`.
3. Claude Code calls `ANTHROPIC_BASE_URL`. The Coder AI Gateway authenticates
   the session token, applies governance/audit, and forwards the request to the
   active provider (Anthropic-direct primary / Bedrock secondary).

No Anthropic key is stored in the workspace; the session token is the only
credential and it is scoped to the workspace owner.

### Why module 4.7.3 and `enable_aibridge` (not `enable_ai_gateway`)

- `deploy/CONVENTIONS.md` and `versions.lock.yaml` pin the claude-code module to
  **4.7.3**, where the input is `enable_aibridge`.
- The `enable_ai_gateway` rename, and the removal of the bundled AgentAPI
  integration and the `task_app_id` output that `coder_ai_task` requires, landed
  in the **5.x** line. Staying on 4.7.3 is what makes the Coder Tasks wiring
  here work.

## Git external auth

Declaring `data.coder_external_auth.gitlab` makes the workspace REQUIRE a GitLab
login (`id = "gitlab"` matches `CODER_EXTERNAL_AUTH_0_ID` on the Coder server).
The agent's git credential helper injects a short-lived OAuth token for
clone/fetch/push to `gitlab.usgov.coderdemo.io`; no PATs or SSH keys live in the
workspace.

## Cluster prerequisites

The platform layer (Coder server + ingress + namespaces) is out of scope for
this directory. Before a workspace can boot:

1. **Coder server** 2.34.0 with the AI Governance add-on and the AI Gateway
   providers configured.
2. **Wildcard access URL** (`CODER_WILDCARD_ACCESS_URL=*.usgov.coderdemo.io`) so
   the subdomain apps (Claude Code web app, code-server) work.
3. **Workspaces namespace** (`coder-workspaces`) exists and the Coder
   provisioner has pods/PVC RBAC there.
4. **Registry pull secret**: a `kubernetes.io/dockerconfigjson` Secret in
   `coder-workspaces` with read access to
   `registry.usgov.coderdemo.io/coderdemo/coder-templates`, passed via
   `image_pull_secret`. (Not needed for template import.)
