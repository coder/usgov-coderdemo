# 70. Workspace template: `claude-code` (as-built)

The single workspace template `claude-code`
(`coder-templates/claude-code/main.tf`) runs Claude Code as a Coder Agent in a
Kubernetes pod, wired through the AI Gateway, and now requires in-boundary
GitLab login. This documents the pod, the modules, Coder Tasks, parameters, and
the GitLab external-auth requirement.

## Verification method

Read-only. Session token via `POST /api/v2/users/login`, then `GET` against
`https://dev.usgov.coderdemo.io`. Template facts come from
`coder-templates/claude-code/main.tf` and its `README.md`, cross-checked against
the live active template version.

Verified live:

- `GET /api/v2/organizations/5de29a6d-8836-4643-a42b-2cb807c8e3e2/templates`:
  one template, `claude-code`, active version `3c0614b5-...`.
- That version's provisioner job status is `succeeded`.

## Pod, PVC, image, and security context

The template provisions one Kubernetes pod and one PVC in namespace
`coder-workspaces` (the `namespace` variable defaults to `coder-workspaces`,
`coder-templates/claude-code/main.tf:60-64`).

- **Pod.** `kubernetes_pod_v1.workspace`, created only when the workspace is
  started (`count = data.coder_workspace.me.start_count`). Labeled
  `app.kubernetes.io/name=coder-workspace`. Source: `main.tf:370-381`.
- **PVC.** `kubernetes_persistent_volume_claim_v1.home`, `ReadWriteOnce`, size
  `${disk_size}Gi`, mounted at `/home/coder`. The cluster default StorageClass
  is `gp3` (encrypted, `WaitForFirstConsumer`), so the home volume lands on gp3.
  `wait_until_bound = false`. Source: `main.tf:345-368, 427-439`; StorageClass
  per the facts sheet.
- **Image.** `var.workspace_image` defaults to the ECR-mirrored
  `430737322961.dkr.ecr.us-gov-west-1.amazonaws.com/docker-hub/codercom/enterprise-base:ubuntu-noble-20260601`.
  `enterprise-base` runs as user `coder` (uid 1000) and ships git/curl/sudo;
  Claude Code and AgentAPI install as standalone binaries into
  `$HOME/.local/bin`, so no Node.js is needed in the base image.
  `image_pull_policy = IfNotPresent`. Source: `main.tf:66-81, 390-394`.
- **Security context.** Pod-level `run_as_user=1000`, `fs_group=1000`;
  container-level `run_as_user=1000`, `allow_privilege_escalation=true`.
  Privilege escalation must stay enabled because the claude-code/agentapi module
  installs the `agentapi` binary to `/usr/local/bin` via passwordless sudo;
  disabling it sets `no_new_privs` and breaks that install and the Coder Tasks
  chat UI it powers. Source: `main.tf:383-404`.
- **Resources.** Requests `cpu=500m` and `memory=max(2, floor(memory/2))Gi`;
  limits `cpu=${cpu}` and `memory=${memory}Gi`. Source: `main.tf:416-425`.
- **Scheduling and stability.** Soft pod anti-affinity by hostname; both the pod
  and the PVC use `lifecycle { ignore_changes = all }` so a running pod survives
  template re-applies and prebuild claims (the agent token is baked into
  `init_script`). Source: `main.tf:441-465`.

The agent container receives `CODER_AGENT_TOKEN` and `CODER_AGENT_URL` (the
access URL) as env (`main.tf:406-414`).

## Agent

`coder_agent.main` (`main.tf:211-267`): a small startup script that only
normalizes `PATH` (adds `$HOME/.local/bin`) and signals readiness, because the
claude-code module's own `coder_script` installs Claude Code and AgentAPI as
native binaries. Agent env sets `EDITOR`/`VISUAL=code` and
`CODER_AGENT_DEVCONTAINERS_ENABLE=false` (no docker socket in the pod, so
devcontainer auto-detection is disabled to avoid the dashboard hanging on
`docker ps`). Metadata reports CPU, memory, and disk usage. `display_apps`
enables VS Code Desktop, web terminal, SSH helper, and port-forwarding helper.

## Claude Code module 4.7.3 (and why not 5.x)

```hcl
module "claude_code" {
  source          = "registry.coder.com/coder/claude-code/coder"
  version         = "4.7.3"
  agent_id        = coder_agent.main.id
  workdir         = "/home/coder"
  enable_aibridge = true
  ai_prompt       = local.effective_prompt
  report_tasks    = true
  subdomain       = true
}
```

The module is pinned to **4.7.3** (`deploy/CONVENTIONS.md:39-45`). In 4.7.x the
AI Gateway input is `enable_aibridge` (not `enable_ai_gateway`). With
`enable_aibridge = true` the module sets, on the agent,
`ANTHROPIC_BASE_URL=<access_url>/api/v2/aibridge/anthropic` and
`CLAUDE_API_KEY=<workspace owner session token>`. Source: `main.tf:14-32,
288-320`.

Why not 5.x: the `enable_ai_gateway` rename landed in the 5.x line, which also
removed the bundled AgentAPI integration and the `task_app_id` output that
`coder_ai_task` depends on. Staying on 4.7.3 is what makes the Coder Tasks
wiring below possible. If the project later moves to 5.x, switch to
`enable_ai_gateway`, drop the explicit `coder_env.anthropic_auth_token`, and add
a standalone `agentapi` module to supply `task_app_id`. Source:
`coder-templates/claude-code/README.md:65-80`.

Model selection is left at the module default on purpose: the requested model
name must match whichever provider the gateway has live (an Anthropic id for
direct, the GovCloud inference profile for Bedrock). Source: `main.tf:312-320`.

### AI Gateway client auth in the template

The module already sets `ANTHROPIC_BASE_URL` and `CLAUDE_API_KEY`. The template
additionally exports `ANTHROPIC_AUTH_TOKEN` (the same session token) via
`coder_env.anthropic_auth_token` to match the AI Gateway client contract in
`deploy/CONVENTIONS.md`. Both carry the same session token, so no raw Anthropic
key is ever placed in the workspace. Source: `main.tf:269-282`,
`deploy/CONVENTIONS.md:90-92`. The full routing flow is in `60-ai-gateway.md`.

## code-server

`module.code_server` (`registry.coder.com/coder/code-server/coder` **1.3.1**)
adds VS Code in the browser as an extra `coder_app` tile, folder `/home/coder`,
`subdomain = true`. Source: `main.tf:331-339`. Both the Claude Code web app and
code-server use `subdomain = true`, which requires the wildcard access URL
configured on the server (this aligns with path apps being disabled; see
`30-coder-control-plane.md`).

## Coder Tasks

Three pieces wire Coder Tasks:

- `data.coder_task.me` (`main.tf:91-93`): populated when the workspace is created
  as a Task. `enabled` is false for a normal build; `prompt` carries the task
  prompt. `local.effective_prompt` prefers the Task prompt and falls back to the
  `ai_prompt` parameter (`main.tf:198-205`).
- `report_tasks = true` on the module: reports task status to the Coder UI via
  AgentAPI (`main.tf:303-306`).
- `coder_ai_task.claude_code` (`main.tf:322-328`): marks the build as a Coder AI
  Task and binds the Task UI to the Claude Code AgentAPI app
  (`app_id = module.claude_code.task_app_id`). It is created only in a Task
  context (`count = data.coder_task.me.enabled ? start_count : 0`), so normal
  builds are unaffected.

The `coder` provider is pinned `>= 2.13.0` because `data.coder_task` and
`coder_ai_task.app_id` first shipped in provider v2.13.0 (`main.tf:34-46`,
`coder-templates/claude-code/README.md:188`).

## Parameters

| Parameter | Type | Mutable | Default | Options |
|---|---|---|---|---|
| `cpu` | number | yes | `4` | 2, 4, 8 |
| `memory` (GB) | number | yes | `8` | 4, 8, 16 |
| `disk_size` (GB) | number | **no** | `20` | 10, 20, 50 |
| `ai_prompt` | string | yes | `""` | (free text) |

`disk_size` is immutable because it sizes the persistent `/home/coder` volume,
which cannot be changed after creation. `ai_prompt` is the fallback seed prompt
for non-Task builds and is ignored when the workspace is launched as a Task.
Source: `main.tf:117-196`. Verified live against the active template version
(`GET /api/v2/templateversions/3c0614b5-.../rich-parameters`): the four
parameters, their types, mutability, defaults, and options all match the table.

## Required GitLab external auth (new requirement)

```hcl
data "coder_external_auth" "gitlab" {
  id = "gitlab"
}
```

The template declares `data "coder_external_auth" "gitlab"` with `id = "gitlab"`,
which must match `CODER_EXTERNAL_AUTH_0_ID` on the server. Declaring this data
source makes every workspace require a GitLab login: the dashboard surfaces a
"Login with GitLab" control, and the agent only reports ready once the owner
completes the in-boundary GitLab OAuth flow. Source: `main.tf:95-111`.

Verified live: the active template version's external-auth list
(`GET /api/v2/templateversions/3c0614b5-.../external-auth`) contains exactly one
entry, `gitlab` (type `gitlab`, display `GitLab`, authenticate URL
`https://dev.usgov.coderdemo.io/external-auth/gitlab`), confirming GitLab login
is required by this version.

This satisfies the directive that every workspace template should include
external-auth through GitLab. Source: `STATUS.md:100-105`.

### How in-workspace git auth works

After the owner completes the GitLab OAuth flow, the Coder agent's git
credential helper injects a short-lived OAuth token for any clone/fetch/push to
`gitlab.usgov.coderdemo.io`. No PATs and no SSH keys live in the workspace, and
no auth path leaves the GovCloud boundary. The server-side provider (id
`gitlab`, type `gitlab`, the in-cluster GitLab OAuth app, scopes
`read_user read_repository write_repository`) is defined in
`deploy/coder/values.yaml:117-148`; the regex `gitlab\.usgov\.coderdemo\.io`
scopes which remotes the helper authenticates. Source: `main.tf:95-111`,
`deploy/coder/values.yaml:117-148`. The server-side external-auth config and its
boundary rationale are in `30-coder-control-plane.md`.

## CI-delivered templates and custom images (GitLab CI)

Beyond this hand-deployed `claude-code` template, the demo also shows templates
and workspace images being delivered from in-boundary GitLab CI. The GitLab
project `root/coder-templates` runs two default-branch CI jobs on the
non-meshed `gitlab-runner` Kubernetes executor:

- `push-template` runs `coder templates push claude-code-ci --org coder` against
  `https://dev.usgov.coderdemo.io`, publishing a SEPARATE `claude-code-ci`
  template from `deploy/gitlab-runner/coder-templates-example/template/`.
- `build-workspace-image` builds a custom workspace image with Kaniko (rootless,
  unprivileged) and pushes it to the project's GitLab Container Registry at
  `registry.usgov.coderdemo.io`, air-gapped (Kaniko builds FROM a base
  pre-seeded from the ECR mirror, using only the CI job token).

A workspace template can then set `var.workspace_image` to that registry image
(for example
`registry.usgov.coderdemo.io/root/coder-templates/custom-workspace:latest`) to
run workspaces on a CI-built image, with the pull staying inside the boundary.
The CI runner, Container Registry, and air-gap details are in `50-gitlab-scm.md`.

## Cluster prerequisites (for reference)

The platform layer owns these (not this template directory): the
`coder-workspaces` namespace, provisioner RBAC letting the `coder/coder` SA
manage pods/PVCs in `coder-workspaces`, and ECR read on the node IAM role so the
pod image pulls without an imagePullSecret. Source:
`coder-templates/claude-code/README.md:82-141`. The workspace RBAC also exists
in both `coder` and `coder-workspaces` namespaces per the facts sheet
(`deploy/platform/workspace-rbac.yaml`).
