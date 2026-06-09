# WS-22 handoff

- **Status:** PASS (decision: GO, feasible in-pod)
- **Agent:** WS-22 (Agent Firewall / Boundary feasibility)
- **Timestamp:** 2026-06-08T06:21:34Z
- **Git commit:** ab67f0da96d6ed86084b584e745cb6d6b7aff152 (read from worktree ref file; no git command run)
- **Branch:** ws-2x/phase2

## Reference commits copied
| Repo | SHA |
|------|-----|
| (none; read-only, no code copied) | |

## Outputs (required for downstream)
| Key | Value |
|-----|-------|
| decision | GO (feasible in-pod, no custom AMI, no dedicated nodepool) |
| recommended_backend | landjail (Landlock V4, no added capabilities) |
| fallback_backend | nsjail + capabilities.add[NET_ADMIN] (Amazon Linux default seccomp ok) |
| node_kernel | 6.18.30-61.116.amzn2023.x86_64 (Amazon Linux 2023.11.20260526, amd64) |
| coder_version | v2.34.0 (buildinfo v2.34.0+3006da5 at dev.usgov.coderdemo.io) |
| ai_governance_entitlement | present (license feature ai_governance_user_limit=30, feature_set=premium) |
| module_change | module 4.7.3 + enable_boundary=true (embedded coder agent-firewall; no boundary_version, stay off 5.x) |
| default_off_variable | enable_agent_firewall (bool, default false) |
| open_item | confirm "landlock" in active LSM list (/sys/kernel/security/lsm) on a node or securityfs-mounted probe pod |
| findings_doc | docs/architecture/agent-firewall-feasibility.md |

## Commands run
```
# All read-only. KUBECONFIG=/home/coder/demoenv-workspace/usgov-coderdemo/kubeconfig
kubectl get nodes -o wide
kubectl get node <node> -o jsonpath='{.status.nodeInfo}'
kubectl get pods -n coder-workspaces -o wide
kubectl get pod <pod> -n coder-workspaces -o jsonpath='{.spec.securityContext}{.spec.containers[*].securityContext}'
kubectl exec -n coder-workspaces <pod> (read-only): uname -r ; cat /sys/kernel/security/lsm ; cat /proc/sys/user/max_user_namespaces
kubectl get ns coder-workspaces -o jsonpath='{.metadata.labels}'
kubectl get deploy -n coder -o jsonpath='{...image...}'
kubectl get cm -n monitoring ; grep boundary panels in coder-dashboard-ai-governance
curl -fsS https://dev.usgov.coderdemo.io/api/v2/buildinfo
python3 (decode CODER_LICENSE features claim only, no raw token printed)
```

## Validation
- [x] Kernel/OS captured: 6.18.30 AL2023, amd64, containerd 2.2.3, EKS v1.36.1.
- [x] User namespaces enabled in-pod (max_user_namespaces=63005).
- [x] Coder v2.34.0 confirmed (image tag + live buildinfo).
- [x] AI Governance Add-On entitled (ai_governance_user_limit=30).
- [x] Pod securityContext / seccomp / namespace PSA captured (no PSA labels, no seccompProfile set, not mesh-injected).
- [x] nsjail vs landjail requirements documented from upstream reference.
- [x] Observability Boundary panels confirmed present and reading 0.
- [x] Minimal reversible (default-off) template change described, NOT applied.
- [x] Go/no-go recorded.

## Blockers
- None that block the GO decision.
- One open verification item (non-blocking): Landlock must be in the active LSM
  list for landjail. It could not be read from inside an unprivileged pod
  because securityfs is not mounted there. Worst case falls back to nsjail +
  NET_ADMIN, still in-pod. Confirm before flipping the default.

## Notes for orchestrator

**Go/no-go: GO.** Agent Firewall can be enabled in-pod on the current EKS
managed node group with no custom AMI and no dedicated nodepool. Recommended
path: land a default-off `enable_agent_firewall` variable on the `claude-code`
template that sets `enable_boundary = true` on the (already pinned) 4.7.3 module,
drops an in-boundary `config.yaml` with `jail_type: landjail`, and only adds
`NET_ADMIN` if an operator opts into the nsjail backend. Nothing was applied
tonight (read-only). Details and the exact HCL/YAML are in
`docs/architecture/agent-firewall-feasibility.md`.

Allowlist must be in-boundary: permit `dev.usgov.coderdemo.io` (required, the
agent reaches Anthropic via the in-cluster AI Gateway) and the in-cluster GitLab
host. Do not rely on allowing `api.anthropic.com` directly.

### Defer issue: NOT warranted

The "needs custom AMI/nodepool" defer issue does not apply, since neither is
required. Do not file it. An optional enablement tracking issue is provided
below for root to file as @ausbru87 if the team wants to schedule the change.

### Optional enablement tracking issue (for root to file as @ausbru87)

Title: Enable Agent Firewall (Boundary) egress sandbox in claude-code template (default-off)

Body:

> ## Summary
> Land the Coder Agent Firewall (Boundary) egress sandbox in the `claude-code`
> workspace template, gated behind a default-off variable. Feasibility (WS-22)
> confirmed it works in-pod on the current EKS managed node group with no custom
> AMI and no dedicated nodepool.
>
> ## Findings (WS-22, read-only)
> - Nodes: Amazon Linux 2023, kernel `6.18.30-61.116.amzn2023.x86_64`, amd64,
>   containerd 2.2.3, EKS v1.36.1. User namespaces enabled in-pod.
> - Coder `v2.34.0`; AI Governance Add-On entitled
>   (`ai_governance_user_limit=30`), which is the licensing gate for Agent
>   Firewall. AI Gateway (same add-on) is already live.
> - Module pinned 4.7.3 supports `enable_boundary=true` via the embedded
>   `coder agent-firewall` subcommand. No move to 5.x (which would break the
>   bundled AgentAPI / Coder Tasks wiring).
> - Backend: prefer **landjail** (Landlock V4, no added capabilities, no seccomp
>   change). Fallback **nsjail + NET_ADMIN** (Amazon Linux default seccomp is
>   sufficient). Both are in-pod.
> - Observability: the `coder-dashboard-ai-governance` Grafana dashboard already
>   ships Boundary panels; they read 0 until enabled.
>
> ## Pre-flight (one read-only check)
> Confirm `landlock` is in the active LSM list on a node or a securityfs-mounted
> probe pod:
> `cat /sys/kernel/security/lsm` should include `landlock`. If absent, use the
> nsjail + NET_ADMIN fallback (still in-pod, no node change).
>
> ## Proposed change (reversible, default-off)
> - Add `enable_agent_firewall` (bool, default false) and
>   `agent_firewall_jail_type` (string, default `landjail`).
> - When enabled: set `enable_boundary = var.enable_agent_firewall` on the 4.7.3
>   module and add a `coder_script` that writes
>   `~/.config/coder_boundary/config.yaml` with an in-boundary allowlist
>   (`dev.usgov.coderdemo.io` and the in-cluster GitLab host) and
>   `jail_type: landjail`.
> - nsjail path only: conditionally add container capability `NET_ADMIN`.
> - With the variable false (default), template behavior is unchanged.
>
> ## Acceptance
> - [ ] Landlock LSM pre-flight confirmed (or nsjail fallback selected).
> - [ ] Template applies with `enable_agent_firewall=false` and no behavior change.
> - [ ] With the flag on, a task workspace reaches the AI Gateway and GitLab, and
>       the AI Governance dashboard Boundary panels show allow/deny activity.
>
> Filed on behalf of the WS-22 investigation. Generated by Coder Agents.
