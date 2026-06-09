# WS-22: Agent Firewall / Boundary feasibility

| Field | Value |
|---|---|
| **State key** | none (read-only investigation) |
| **Phase** | 2 |
| **Model** | **Sonnet** |
| **Depends on** | WS-05 (Coder), WS-13 (AI Bridge), observability stack |
| **Track** | Investigation |

## Goal

Decide go/no-go on enabling the Coder Agent Firewall (Boundary) egress sandbox
in the `claude-code` template, without any node-level or AMI change. Evaluate a
Landlock-based backend (landjail) for the live `coder-workspaces` pods and
compare against the namespace-based backend (nsjail).

## Constraints

- Strictly READ-ONLY. No changes to nodes, pods, templates, cluster objects, or
  git. No mutating commands in pods. No AMI or nodepool changes.
- In-pod probes limited to non-mutating reads (`uname -r`,
  `cat /sys/kernel/security/lsm`, `cat /proc/sys/user/max_user_namespaces`).

## Read handoffs

- WS-05 (control plane version/license), WS-13 (AI Bridge wiring), as-built
  `70-workspace-templates.md`.

## Tasks

1. Probe node kernel / OS / arch and in-pod user namespace availability.
2. Confirm Coder version and the AI Governance Add-On entitlement (license).
3. Inspect live pod securityContext, seccomp, and namespace PSA posture.
4. Read upstream Boundary docs: nsjail vs landjail requirements and k8s notes.
5. Confirm the observability Boundary panels exist and read 0.
6. Decide go/no-go against the AMI/nodepool gate; describe the minimal,
   reversible, default-off template change (do NOT apply).

## Reference

- `reference/coder/docs/ai-coder/agent-firewall/*` (index, version, landjail,
  nsjail/k8s), `reference/coder/docs/ai-coder/ai-governance.md`,
  `reference/coder/dogfood/coder/boundary-config.yaml`.

## Apply

None. Read-only. Deliverables are docs only.

## Parallel authoring

Node/kernel probe, license/version probe, pod/securityContext probe, and
upstream doc reads run in parallel; decision synthesized after.

## Validation

- [ ] Kernel and OS captured from node `.status.nodeInfo`.
- [ ] AI Governance Add-On entitlement confirmed from license features.
- [ ] nsjail vs landjail requirements documented from upstream.
- [ ] In-pod feasibility decided against the AMI/nodepool gate.
- [ ] Minimal reversible (default-off) template change described, not applied.
- [ ] Clear go/no-go recorded in the handoff.

## Outcome

GO (feasible in-pod). No custom AMI or dedicated nodepool required. landjail
recommended (no capabilities), nsjail + NET_ADMIN documented as fallback. One
read-only Landlock LSM pre-flight check remains before flipping the default.
Findings in `docs/architecture/agent-firewall-feasibility.md`.
