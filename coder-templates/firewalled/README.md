# Firewalled Claude Code on Coder Agents (GovCloud demo template)

Coder workspace template that runs **Claude Code** inside a Kubernetes pod on
the EKS cluster, wired through the **Coder AI Gateway (AI Bridge)** and wrapped
in the **Coder Boundary agent firewall**. The workspace never holds a raw
Anthropic API key: every request is proxied through Coder using the workspace
owner's session token and routed to the configured provider (Anthropic-direct
primary, Bedrock secondary) in-boundary.

Claude Code runs inside a process-level network egress jail (`landjail`,
Landlock LSM) that denies all HTTP(S) egress except an allowlist. The agent can
reach the in-boundary AI Gateway and the in-cluster GitLab; every other
destination is denied and audit-logged. This is the data-exfiltration / DLP
guardrail story for the AOI.

Claude Code is driven interactively from the workspace terminal or code-server.
There is no Coder Tasks / AgentAPI wiring in this template. Codex/OpenAI is
also intentionally omitted: this is a Claude-only firewall demo.

- `main.tf`: the template (providers `coder` + `kubernetes`).
- `boundary.config.yaml.tftpl`: the boundary allowlist, rendered at plan time.
- Workspace image: `codercom/enterprise-base:ubuntu-noble-20260601`, pulled
  from the ECR mirror.

## Agent firewall (Coder Boundary)

The workspace `startup_script` installs the standalone `boundary` binary
directly:

```bash
curl -fsSL https://raw.githubusercontent.com/coder/boundary/main/install.sh | bash
```

The standalone binary has no license/login dependency. The `coder boundary`
subcommand requires an authenticated CLI session (the agent carries only an
agent token, not a user session), so the standalone binary is the right choice
here.

The allowlist is rendered from `boundary.config.yaml.tftpl` via
`templatefile()` at plan time and written to
`~/.config/coder_boundary/config.yaml` on every workspace start. boundary
v0.9.0 does not auto-discover this path. The boundary wrapper passes `--config`
explicitly, and the `BOUNDARY_CONFIG` env var (set via `coder_env`) points any
direct `boundary -- <cmd>` invocation at the same file. `BOUNDARY_JAIL_TYPE=landjail`
is also set on the agent via `coder_env`.

A boundary wrapper is installed at `~/.local/bin/boundary-wrappers/claude`.
That directory is prepended to `PATH` in `~/.profile`, `~/.bashrc`, `~/.zshrc`,
and `~/.zprofile`, so `claude` resolves to the wrapper by default. The wrapper
exec's:

```
boundary --config ~/.config/coder_boundary/config.yaml --jail-type landjail -- <real claude> --dangerously-skip-permissions "$@"
```

`--dangerously-skip-permissions` removes Claude's interactive per-tool approval
and bypass-mode prompts. Boundary is the security boundary here; Claude's
built-in permission prompts are redundant friction in this architecture.

`landjail` uses the Landlock LSM (no network namespace, iptables, or added pod
capabilities). The AL2023 node kernel (6.18) is well past the Landlock 6.7
floor and `landlock` is in the node LSM stack.

### Allowlist

The allowlist (`boundary.config.yaml.tftpl`) is adapted from the Red Hat Summit
2026 demo (`coder/demo-aigov-rhaiis-rhsummit-2026`). It covers Claude Code's
default allowed domains: package managers (Python, Ruby, Dart, NuGet, Haskell,
Swift, CPAN), GitHub, GitLab.com, Bitbucket, container registries (Docker Hub,
GCR, GHCR, MCR), cloud SDKs (AWS CloudFront/S3, GCP, Azure), Anthropic
services, and Datadog telemetry. It also includes:

- This deployment's Coder host (`${coder_host}`, rendered from the access URL):
  required for AI Gateway inference.
- `gitlab.usgov.coderdemo.io`: the in-cluster GitLab.
- Test domains (`typicode.com`, `*.typicode.com`).

**npm is intentionally omitted**, so asking the agent to `npm install <anything>`
is the obvious DENY in the demo. The deny shows up live in the boundary Grafana
dashboard and the coderd audit log with owner/workspace/agent attribution. Edit
`boundary.config.yaml.tftpl` to change the allowlist; do not inline rules in
`main.tf`.

### Verify allow vs deny in a workspace terminal

```bash
# Allowed: the AI Gateway host returns 200
boundary -- curl -sS -o /dev/null -w '%{http_code}\n' \
  https://dev.usgov.coderdemo.io/api/v2/buildinfo

# Allowed: PyPI is on the allowlist
boundary -- curl -sS -o /dev/null -w '%{http_code}\n' https://pypi.org

# Denied: npm is intentionally off the allowlist (boundary drops it)
boundary -- curl -sS -o /dev/null -w '%{http_code}\n' https://registry.npmjs.org
```

### Firewall smoke-test scripts

Pre-staged under `~/demo/`:

| Script | What it does | Expected result |
|---|---|---|
| `exfil-test.sh` | POST to `webhook.site` (off allowlist) | `curl` fails; boundary drops the connection |
| `unknown-registry-test.sh` | `pip install` from a non-allowlisted `--index-url` | `pip` fails with a resolver error |

Run with `boundary -- ~/demo/exfil-test.sh` or ask an agent to run the file.
Tail `/tmp/boundary_logs/` in another terminal to watch DENY events land.

## What's inside

| Piece | Resource | Notes |
|---|---|---|
| Agent | `coder_agent.main` | startup script, metadata, `display_apps` (VS Code Desktop, web terminal, SSH) |
| Claude Code CLI | native install in `startup_script` | `curl -fsSL https://claude.ai/install.sh \| bash -s -- stable` into `~/.local/bin` |
| Boundary (firewall) | native install in `startup_script` | `curl .../coder/boundary/main/install.sh \| bash`; standalone binary, no license/login dependency |
| Boundary wrapper | generated in `startup_script` | `~/.local/bin/boundary-wrappers/claude`; jails `claude` under `landjail`; prepended to `PATH` in all shell rc files |
| Claude Code config | `startup_script` + `locals.claude_settings` / `locals.claude_config` | `~/.claude/settings.json` (AI Gateway endpoint, onboarding flags); `~/.claude.json` (session-token `primaryApiKey`, project trust) |
| AI auth | `coder_env.claude_api_key` + `coder_env.anthropic_auth_token` | `CLAUDE_API_KEY` and `ANTHROPIC_AUTH_TOKEN` = workspace owner session token |
| Firewall env | `coder_env.boundary_config` + `coder_env.boundary_jail_type` | `BOUNDARY_CONFIG` = allowlist path; `BOUNDARY_JAIL_TYPE=landjail` |
| GitLab auth | `data.coder_external_auth.gitlab` | REQUIRED GitLab login; Coder's git credential helper injects the short-lived OAuth token; no PAT or SSH key in the workspace |
| Browser IDE | `module.code_server` (`code-server` 1.3.1) | extra `coder_app` tile |
| Compute | `kubernetes_pod_v1.workspace` + `kubernetes_persistent_volume_claim_v1.home` | sizing from `cpu` / `memory` / `disk_size` parameters |

Parameters: `cpu`, `memory`, `disk_size`.

## AI Gateway wiring (end to end)

1. The `startup_script` and `coder_agent.main.env` configure the agent on
   every start:
   - `ANTHROPIC_BASE_URL = <access_url>/api/v2/aibridge/anthropic`
   - `ANTHROPIC_API_BASE` = same value (for clients that read that name)
   - `CLAUDE_API_KEY` and `ANTHROPIC_AUTH_TOKEN` = workspace owner session
     token (injected as sensitive `coder_env` resources, not baked into the
     pod spec).
   - `~/.claude/settings.json` also sets `env.ANTHROPIC_BASE_URL` so Claude
     Code reads the gateway endpoint even from non-login shells.
   - `~/.claude.json` carries `primaryApiKey` = session token; Claude Code
     reads this on startup and does not prompt for an Anthropic key.

   With `CODER_ACCESS_URL=https://dev.usgov.coderdemo.io` the base URL
   resolves to `https://dev.usgov.coderdemo.io/api/v2/aibridge/anthropic`.

2. Claude Code calls `ANTHROPIC_BASE_URL`. The Coder AI Gateway authenticates
   the session token, applies governance/audit, and forwards the request to the
   active provider:
   - **Anthropic-direct** (primary): egress via the NAT gateway.
   - **Bedrock** (secondary): IRSA on the `coder/coder` service account, model
     `us-gov.anthropic.claude-sonnet-4-5-20250929-v1:0`, in-region only.

No Anthropic key is stored in the workspace; the session token is the only
credential and it is scoped to the workspace owner.

### Model selection

Model is left at the Claude Code CLI / AI Gateway default on purpose, because
the requested model name must match whichever provider the Gateway has live:

- Anthropic-direct: an Anthropic model id, e.g. `claude-sonnet-4-5-20250929`.
- Bedrock (GovCloud): the inference profile
  `us-gov.anthropic.claude-sonnet-4-5-20250929-v1:0`.

To pin a model, pass `--model <id>` when running `claude`, or edit the
boundary wrapper at `~/.local/bin/boundary-wrappers/claude` and insert
`--model <id>` before `"$@"` in the exec line. Bedrock Claude access was
still gated at authoring time (see `STATUS.md`), so the safe default is to
let Claude Code and the Gateway negotiate.

## Cluster prerequisites

The platform layer (Coder server + ingress + namespaces) is out of scope for
this directory. Before pushing/using the template, ensure:

1. **Coder server** 2.34.0 with the AI Governance add-on license and the AI
   Gateway providers configured (Anthropic-direct + Bedrock). See
   `deploy/coder/`.
2. **Wildcard access URL** set so subdomain apps work
   (`CODER_WILDCARD_ACCESS_URL=*.usgov.coderdemo.io`). code-server uses
   `subdomain = true`.
3. **Workspaces namespace** exists:

   ```bash
   kubectl create namespace coder-workspaces
   ```

4. **Provisioner RBAC**: the Coder provisioner (service account `coder` in the
   `coder` namespace) must be able to manage pods/PVCs in `coder-workspaces`.
   Example (apply with the platform layer, not from this directory):

   ```yaml
   apiVersion: rbac.authorization.k8s.io/v1
   kind: Role
   metadata:
     name: coder-workspace-provisioner
     namespace: coder-workspaces
   rules:
     - apiGroups: [""]
       resources: ["pods", "persistentvolumeclaims"]
       verbs: ["create", "get", "list", "watch", "update", "patch", "delete"]
     - apiGroups: [""]
       resources: ["pods/exec", "pods/log"]
       verbs: ["get", "create"]
     - apiGroups: [""]
       resources: ["events"]
       verbs: ["get", "list", "watch"]
   ---
   apiVersion: rbac.authorization.k8s.io/v1
   kind: RoleBinding
   metadata:
     name: coder-workspace-provisioner
     namespace: coder-workspaces
   roleRef:
     apiGroup: rbac.authorization.k8s.io
     kind: Role
     name: coder-workspace-provisioner
   subjects:
     - kind: ServiceAccount
       name: coder
       namespace: coder
   ```

5. **Image pull**: the EKS node IAM role needs ECR read
   (`ecr:GetAuthorizationToken`, `ecr:BatchGetImage`,
   `ecr:GetDownloadUrlForLayer`) for
   `430737322961.dkr.ecr.us-gov-west-1.amazonaws.com`. With that on the node
   role, no `imagePullSecret` is required on the pod. The image must already be
   mirrored into ECR (`scripts/mirror-images.sh`).

6. **GitLab external auth provider** configured on the Coder server
   (`CODER_EXTERNAL_AUTH_0_ID=gitlab`). The template declares
   `data.coder_external_auth.gitlab` as required; workspace creation blocks
   until the owner completes the GitLab OAuth flow. No PATs or SSH keys live
   in the workspace; no auth path leaves the GovCloud boundary.

## Pushing the template

From the repo root:

```bash
# First time: create the template.
coder templates push firewalled \
  --directory coder-templates/firewalled \
  --variable namespace=coder-workspaces

# Subsequent updates push a new version.
coder templates push firewalled \
  --directory coder-templates/firewalled
```

Override the image or namespace at push time if needed:

```bash
coder templates push firewalled \
  --directory coder-templates/firewalled \
  --variable namespace=coder-workspaces \
  --variable workspace_image=430737322961.dkr.ecr.us-gov-west-1.amazonaws.com/docker-hub/codercom/enterprise-base:ubuntu-noble-20260601
```

Template variables:

| Variable | Default | Purpose |
|---|---|---|
| `namespace` | `coder-workspaces` | namespace for workspace pods |
| `workspace_image` | ECR-mirrored `enterprise-base` | workspace container image |
| `use_kubeconfig` | `false` | use a host kubeconfig instead of in-cluster config |

## Using it

Create a workspace from the template. Once the startup script completes
(`=== Workspace ready ===` in the agent log), open the web terminal or
code-server and run:

```bash
claude
```

`claude` in `PATH` resolves to the boundary wrapper, so all Claude Code network
egress is jailed from the first keystroke. The real Claude Code binary is still
reachable at its absolute path (`~/.local/bin/claude`) for debugging or for
running without the firewall in a controlled test.

To run the firewall smoke tests before a demo:

```bash
~/demo/exfil-test.sh             # POST to webhook.site: boundary drops it
~/demo/unknown-registry-test.sh  # pip from unapproved mirror: boundary drops it
```

To verify allowed hosts from the same terminal:

```bash
curl -sI https://api.github.com | head -1   # expect HTTP/2 200
pip install --dry-run requests              # expect success
```

## Verification status

| Item | Source | Status |
|---|---|---|
| Claude Code CLI native install (`curl https://claude.ai/install.sh \| bash -s -- stable`) | `main.tf` startup_script | verified |
| boundary standalone install (`curl .../coder/boundary/main/install.sh \| bash`) | `main.tf` startup_script | verified |
| boundary v0.9.0 does not auto-discover config; `--config` required | boundary changelog / `main.tf` comment | verified |
| `BOUNDARY_CONFIG` + `BOUNDARY_JAIL_TYPE` env vars set via `coder_env` | `main.tf` `coder_env` resources | verified |
| `CLAUDE_API_KEY` + `ANTHROPIC_AUTH_TOKEN` = session token (no raw Anthropic key) | `main.tf` `coder_env` resources | verified |
| `ANTHROPIC_BASE_URL` + `ANTHROPIC_API_BASE` = AI Gateway endpoint | `main.tf` `coder_agent.main.env` | verified |
| `~/.claude/settings.json` + `~/.claude.json` pre-seeded (onboarding skipped, session-token auth) | `main.tf` `locals.claude_settings` / `locals.claude_config` | verified |
| `allow_privilege_escalation = true` required (boundary install.sh writes to `/usr/local/bin` via sudo) | `main.tf` pod security context | verified |
| Workspace image tag | Docker Hub `codercom/enterprise-base` | verified (`ubuntu-noble-20260601`) |
| `code-server` 1.3.1 | registry tag `release/coder/code-server/v1.3.1` | verified (latest is 1.5.0) |
| Live AI Gateway routing / Bedrock model access | runtime cluster | NOT verified here (no live infra access; Bedrock Claude access gated per `STATUS.md`) |
