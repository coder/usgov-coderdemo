# WS-11 — OCP fabric

| Field | Value |
|---|---|
| **State key** | `ocp/terraform.tfstate` (IPI) |
| **Phase** | 3 |
| **Model** | see sub-table below |
| **Depends on** | WS-02, G0.8 PASS |
| **Track** | B (start IPI early) |

### Models by sub-workstream

| Sub-WS | Model |
|---|---|
| WS-11a IPI | **Opus** |
| WS-11b GitOps prep | **Sonnet** |
| WS-11c OCP provisioner | **Opus** |
| WS-11d OCP proxy | **Opus** |
| WS-11e UBI9 → ECR | **Sonnet** |
| WS-11f OCP template | **Sonnet** |

Split into sub-workstreams. Orchestrator tracks each separately in SWARM-STATUS.

---

## WS-11a — OCP IPI

**Start after WS-02.** Long-running (~hours).

### Tasks

1. Adapt demo-aigov OCP IPI for GovCloud
2. Strip GPU, RHAIIS, in-cluster Coder
3. `terraform apply` and poll until cluster READY

### Apply

```bash
./scripts/tf-apply.sh terraform/ocp
```

### Handoff

| Key | Description |
|---|---|
| `ocp_api_url` | |
| `ocp_kubeconfig` | path |
| `ipi_duration_min` | |

---

## WS-11b — GitOps prep (code-only)

**Wave 3b** — no cluster needed.

- Copy/adapt `gitops/`, `manifests/` from reference
- Remove rhaiis, gpu, in-cluster-coder

---

## WS-11c — OCP provisioner

**After cluster READY.**

- Deploy external provisioner `platform=ocp` via Argo
- Register to `dev.usgov.coderdemo.io`

---

## WS-11d — OCP workspace proxy

**After 11c.**

- Proxy at `ocp.usgov.coderdemo.io`

---

## WS-11e — UBI9 → ECR

**After WS-01 ECR.** May parallel 11a.

- Build/push SCC-compatible UBI9 workspace image

---

## WS-11f — OCP template

**After 11c/11d.**

- Publish template `platform=ocp`

## Validation

- [ ] **C6** OCP proxy
- [ ] **C7** provisioner builds

## Skip condition

G0.8 FAIL → orchestrator skips entire WS-11.
