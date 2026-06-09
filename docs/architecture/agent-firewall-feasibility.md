# Agent Firewall (Coder Boundary) egress sandbox: feasibility

Read-only investigation for WS-22 (Phase 2). No nodes, pods, templates, cluster
objects, or git were modified. All probes were non-mutating reads against the
existing cluster and an already-running workspace pod.

## Verdict

**GO (feasible in-pod).** Enabling the Agent Firewall egress sandbox in the
`claude-code` template does **not** require a custom AMI or a dedicated
nodepool. It can run entirely inside the existing `coder-workspaces` pods on the
current EKS managed node group, as a template-level change gated behind a
default-off variable. The recommended backend is **landjail** (Landlock V4),
which needs no added Linux capabilities and no seccomp changes. **nsjail**
(the default backend) is also viable in-pod on these Amazon Linux nodes by
adding only the `NET_ADMIN` capability, and serves as a stronger-isolation
fallback.

One verification item remains open because it cannot be read from inside an
unprivileged pod (see "Open verification item"). Even in the worst case that
item resolves against landjail, the fallback (nsjail + `NET_ADMIN`) stays
in-pod, so the GO decision holds either way.

## Evidence (live, read-only)

### Nodes / kernel / AMI

| Fact | Value | Source |
|------|-------|--------|
| Node group | EKS managed node group, 3 nodes, `<none>` role | `kubectl get nodes -o wide` |
| OS image | Amazon Linux 2023.11.20260526 | node `.status.nodeInfo.osImage` |
| Kernel | `6.18.30-61.116.amzn2023.x86_64` | node `.status.nodeInfo.kernelVersion` |
| Arch | amd64 | node `.status.nodeInfo.architecture` |
| Container runtime | `containerd://2.2.3+unknown` | node `.status.nodeInfo` |
| Kubelet / EKS | `v1.36.1-eks-3385e9b` | node `.status.nodeInfo` |
| User namespaces (in-pod) | `max_user_namespaces = 63005` (enabled) | `cat /proc/sys/user/max_user_namespaces` in workspace pod |

Kernel `6.18.30` is far above the **Linux 6.7+** floor that landjail requires.
Landlock network restriction (the `connect`/`bind` controls landjail depends on)
landed as Landlock ABI v4 in 6.7 and has only been extended since, so the kernel
source support is firmly present on these nodes. Amazon Linux 2023 ships the
Landlock LSM compiled into the kernel.

### Control plane / version / license

| Fact | Value | Source |
|------|-------|--------|
| Coder server version | `v2.34.0` | control-plane deploy image tag; `GET /api/v2/buildinfo` at `https://dev.usgov.coderdemo.io` returns `v2.34.0+3006da5` |
| Embedded `coder agent-firewall` | Yes (Coder v2.30+) | upstream `agent-firewall/version.md` |
| Add-on gating | AI Governance Add-On required as of v2.32 | upstream `ai-governance.md` |
| License feature set | `premium`, non-trial (salesforce) | `CODER_LICENSE` JWT `features` claim |
| AI Governance entitlement | `ai_governance_user_limit: 30` | `CODER_LICENSE` JWT `features` claim |

The same AI Governance Add-On gates both AI Gateway and Agent Firewall. AI
Gateway (AI Bridge) is already live in this environment (the active `claude-code`
template wires `enable_aibridge = true`), which corroborates that the add-on is
active, and the license claim `ai_governance_user_limit: 30` confirms the
entitlement directly. The licensing gate is therefore **satisfied**.

Note: the `coder` CLI inside this orchestration workspace is authenticated to
`https://dev.coder.com` (Coder's own deployment), not to the usgov deployment,
so `coder licenses list` there is not authoritative for this environment. The
entitlement evidence above comes from the deployment's own `CODER_LICENSE` and
the live `buildinfo`, not from that CLI.

### Module

The template pins the Claude Code module to **4.7.3**. Module v4.7.0+ uses the
embedded `coder agent-firewall` subcommand by default, so `enable_boundary =
true` works on 4.7.3 with no `boundary_version` pin and no move to the 5.x line.
Staying on 4.7.3 preserves the bundled AgentAPI / Coder Tasks wiring that the
5.x line removed (see `docs/as-built/70-workspace-templates.md`).

### Pod security posture (live)

From the running pod `coder-df4dfaf8-...` in `coder-workspaces`:

- Pod `securityContext`: `runAsUser=1000`, `fsGroup=1000`, `runAsNonRoot=false`.
- Container `dev` `securityContext`: `runAsUser=1000`,
  `allowPrivilegeEscalation=true`, `privileged=false`,
  `readOnlyRootFilesystem=false`, no added capabilities, no `seccompProfile`
  set (runtime default applies).
- Namespace `coder-workspaces` has **no Pod Security Admission labels**, so no
  enforced `restricted`/`baseline` policy blocks a capability add or a custom
  jail. `coder-workspaces` is also **not** mesh-injected (Istio), so there is no
  sidecar interaction with the egress sandbox.

This posture matters because:

- **landjail** needs none of these relaxed: it adds no capability and changes no
  seccomp profile, so it fits the current pod spec as-is.
- **nsjail** on these Amazon Linux nodes needs only `capabilities.add:
  [NET_ADMIN]` (the default seccomp and runtime already permit the namespace
  syscalls, and user namespaces are enabled in-pod). The absence of PSA
  enforcement means that capability add is admissible without a node change.

### Observability

The `coder-dashboard-ai-governance` Grafana ConfigMap in the `monitoring`
namespace already ships Agent Firewall / Boundary panels, including the
`boundary_log_proxy_batches_forwarded_total` metric and `boundary_sessions`
allow/deny queries joined to `workspace_agents`. These panels read 0 today
because no workspace runs the firewall yet. Enabling it lights them up with no
dashboard change.

## Backend comparison for this environment

| Aspect | nsjail (namespaces + veth + iptables) | landjail (Landlock V4) |
|--------|----------------------------------------|------------------------|
| Capabilities required | `NET_ADMIN` (template change) | none |
| Seccomp change | none on Amazon Linux nodes | none |
| Kernel floor | Linux 3.8+ (met) | Linux 6.7+ (met: 6.18.30) |
| Node / AMI change | none | none |
| Bypass resistance | strong (transparent interception) | medium (a process can reach `evil.com:<proxy_port>`) |
| PID isolation | yes | no |
| UDP control | yes (iptables) | no (UDP can leak) |
| App compatibility | any app (transparent) | only `HTTP_PROXY`-aware tools |

Recommendation for this demo: default to **landjail** because it requires zero
capability or seccomp relaxation and the nodes exceed the kernel floor. Keep
**nsjail + NET_ADMIN** documented as the stronger-isolation fallback if a future
requirement needs transparent interception or UDP control.

## Environment-specific allowlist note

Because the agent reaches Anthropic through the in-boundary AI Gateway
(`ANTHROPIC_BASE_URL = https://dev.usgov.coderdemo.io/api/v2/aibridge/anthropic`),
the Agent Firewall allowlist for this environment must permit the **Coder
deployment domain** `dev.usgov.coderdemo.io` (required, so the agent can reach
the gateway) plus the **in-cluster GitLab** host used for SCM, and should **not**
rely on allowing `api.anthropic.com` directly. The upstream sample allowlist
(api.anthropic.com, github.com, public registries) is mostly irrelevant here
since egress is in-boundary. This keeps the allowlist small and aligned with the
GovCloud boundary story.

## Open verification item (one read-only check before enabling)

landjail requires that the **Landlock LSM is in the kernel's active LSM list**
(the boot-time `CONFIG_LSM` / `lsm=` stack), not merely compiled in. That list
is exposed at `/sys/kernel/security/lsm`, which is served by `securityfs`.
`securityfs` is **not mounted inside the unprivileged workspace pod**
(the in-pod read of `/sys/kernel/security/lsm` returned "No such file or
directory", and `/sys/kernel/security/` is empty in the pod), so this could not
be confirmed read-only from inside a pod tonight, and node-level access is out
of scope for this investigation.

Expectation: on Amazon Linux 2023 with kernel 6.18, Landlock is normally present
in the default LSM stack, so landjail is expected to work. Confirm with one
read-only command on a node or in a throwaway pod that mounts securityfs before
flipping the default:

```bash
# On a node (node-level, do NOT run tonight), or in a disposable probe pod:
cat /sys/kernel/security/lsm    # expect a list that includes "landlock"
```

If `landlock` is absent from that list, fall back to **nsjail + NET_ADMIN**,
which stays in-pod and requires no node change. The GO decision is unaffected.

## Minimal, reversible template change (described, NOT applied)

Land this behind a default-off variable so the change is inert until explicitly
enabled, and trivially reversible by flipping the variable back to `false`.

1. Add variables (default-off):

   ```hcl
   variable "enable_agent_firewall" {
     type        = bool
     description = "Wrap the agent in the Coder Agent Firewall (Boundary) egress sandbox."
     default     = false
   }

   variable "agent_firewall_jail_type" {
     type        = string
     description = "Boundary jail backend: landjail (no caps) or nsjail (needs NET_ADMIN)."
     default     = "landjail"
   }
   ```

2. Enable the module's Boundary integration when the flag is on (4.7.3 supports
   `enable_boundary` with the embedded subcommand, so no `boundary_version`):

   ```hcl
   module "claude_code" {
     source          = "registry.coder.com/coder/claude-code/coder"
     version         = "4.7.3"
     agent_id        = coder_agent.main.id
     workdir         = "/home/coder"
     enable_aibridge = true
     enable_boundary = var.enable_agent_firewall
     # ... existing inputs unchanged ...
   }
   ```

3. Drop a `config.yaml` into `~/.config/coder_boundary/` via a `coder_script`
   gated on the flag, with an in-boundary allowlist and `jail_type` from the
   variable:

   ```yaml
   allowlist:
     - "domain=dev.usgov.coderdemo.io"   # required: reach the in-boundary AI Gateway
     - "domain=<in-cluster-gitlab-host>" # SCM (set to the live GitLab host)
   jail_type: landjail
   log_dir: /tmp/boundary_logs
   proxy_port: 8087
   log_level: warn
   ```

4. nsjail fallback only: when `agent_firewall_jail_type == "nsjail"`, add the
   container capability `NET_ADMIN` (and nothing else). Default landjail adds no
   capability, so the default path leaves the pod securityContext unchanged.

Reversibility: with `enable_agent_firewall = false` (the default) the template
behaves exactly as today. No node, AMI, or nodepool change is involved in any of
the above.

## Why DEFER is NOT warranted

The decision gate for deferral was "requires custom AMIs or dedicated
nodepools." Neither is required:

- Kernel and OS on the existing managed node group already meet both backends'
  requirements (6.18.30 AL2023, user namespaces enabled, default seccomp
  permissive enough for nsjail on Amazon Linux).
- landjail needs no capability, no seccomp change, and no node change.
- The only residual is a one-line read-only Landlock LSM check, with an in-pod
  fallback if it fails.

A "needs custom AMI/nodepool" defer issue would therefore misrepresent the
findings and should not be filed. An optional enablement tracking issue is
included in the handoff instead.
