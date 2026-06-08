# WS-25 handoff

- **Status:** PARTIAL (authoring complete; awaiting root push + build + connectivity)
- **Agent:** sub-agent WS-25 (workspace template family)
- **Timestamp:** 2026-06-08T06:28:31Z
- **Git commit:** none (authoring sub-agent does not run git; root commits ws-2x/phase2)
- **Branch:** ws-2x/phase2

## Reference commits copied

| Repo | SHA | Use |
|------|-----|-----|
| demo-aigov-rhsummit-2026 (`reference/demo-aigov-rhsummit-2026/coder-templates`) | `da48a48` | Shape/ideas only: `agents-dev-ocp` plain-compute pattern (no AI Bridge), `metadata.json` convention. Adapted from OpenShift/UBI9 to EKS/ECR `enterprise-base`. |
| In-repo `coder-templates/claude-code` | (worktree HEAD) | EKS pod/PVC/agent/securityContext/external-auth/subdomain pattern, reused minus all AI wiring. |

## Outputs (required for downstream)

Five new templates under `coder-templates/`, each with `main.tf`, `README.md`,
`metadata.json`. Plus shared notes in `coder-templates/_shared/README.md`.

| Template | display_name | Routing description | Base image (default) | Privilege escalation |
|---|---|---|---|---|
| `cpp-engineer` | C/C++ Engineer | C and C++ engineering workspace: clang, gcc, CMake, Ninja, gdb/lldb, valgrind. Use for C/C++ services, native libraries, and systems programming. | ECR `enterprise-base:ubuntu-noble-20260601` | enabled |
| `java-engineer` | Java Engineer | Java/JVM engineering workspace: OpenJDK 21, Maven, Gradle. Use for Java and Kotlin services, Spring Boot apps, and JVM build tooling. | ECR `enterprise-base:ubuntu-noble-20260601` | enabled |
| `platform-engineer` | Platform Engineer | Platform/DevOps engineering workspace: kubectl, Helm, Terraform, AWS CLI, jq. Use for infrastructure-as-code, Kubernetes operations, and cloud platform work. | ECR `enterprise-base:ubuntu-noble-20260601` | enabled |
| `data-scientist` | Data Scientist | Data science workspace: Python 3, JupyterLab, pip/venv. Use for notebooks, data analysis, and ML prototyping. | ECR `enterprise-base:ubuntu-noble-20260601` | enabled |
| `ai-agent-generic` | Generic Agent Runtime | Generic agent runtime workspace: plain compute with no in-workspace LLM tooling. Default target for server-side Coder Agents tasks that are not language-specific. | ECR `enterprise-base:ubuntu-noble-20260601` | disabled (`no_new_privs`) |

Full base-image ref:
`430737322961.dkr.ecr.us-gov-west-1.amazonaws.com/docker-hub/codercom/enterprise-base:ubuntu-noble-20260601`.

## Images root must mirror first

Nothing is required to push and build today: all five default to the already
mirrored `enterprise-base` (in `scripts/images.txt`). The following are
OPTIONAL upgrades root MAY mirror or build for a fully air-gapped,
fast-start demo (do not block on them):

| Image | Status | For | Action |
|---|---|---|---|
| `docker.io/codercom/enterprise-node:ubuntu-noble-20260601` | NOT mirrored; tag unverified | optional richer base for `data-scientist`, `ai-agent-generic` (prebaked Node) | verify the tag exists, then add to `scripts/images.txt` |
| Prebaked `cpp-engineer` image | not built | remove startup apt for C/C++ | build via GitLab CI Kaniko (see as-built 70), push to in-boundary registry, set `workspace_image` |
| Prebaked `java-engineer` image | not built | remove startup apt for JDK/Maven/Gradle | same |
| Prebaked `platform-engineer` image | not built | remove kubectl/helm/terraform startup downloads (these reach external endpoints) | same |
| Prebaked `data-scientist` image | not built | remove JupyterLab/pip startup install | same |
| Prebaked `ai-agent-generic` image | not built | give the server-side agent a full toolbox under a git-only egress policy | same |

Do NOT default any template to an image that is not yet in the ECR mirror.

## Commands run

```
none (authoring only: read context, wrote template files and docs)
```

## Per-template push/test commands for root

Full, copy-paste commands (push to org alpha and coder, apply metadata, build a
test workspace, run the C4 check, clean up) are in
`docs/swarm/workstreams/WS-25-templates.md` under "Per-template root commands".
Summary per template:

```sh
# push to both orgs
for ORG in alpha coder; do
  coder templates push NAME --directory coder-templates/NAME --org "$ORG" \
    --variable namespace=coder-workspaces --yes
done
# apply display name + icon + routing description (the auto-selection signal)
for ORG in alpha coder; do
  coder templates edit NAME --org "$ORG" \
    --display-name "DISPLAY" --icon "ICON" --description "DESCRIPTION" --yes
done
# build, prove C4, clean up
coder create test-NAME --template NAME --org alpha \
  --parameter cpu=4 --parameter memory=8 --parameter disk_size=20 --parameter git_repo="" --yes
# complete "Login with GitLab" once (required external auth) so the agent is ready
coder ping test-NAME      # C4 agent reachability; also: coder show test-NAME
coder delete test-NAME --yes
```

Shell preamble (note the CODER_URL gotcha):

```sh
. ~/.config/usgov-coderdemo/env
export KUBECONFIG=/home/coder/demoenv-workspace/usgov-coderdemo/kubeconfig
export PATH="$HOME/.local/bin:$PATH"
export CODER_URL=https://dev.usgov.coderdemo.io   # ambient dev.coder.com is WRONG
coder login "$CODER_URL"
```

## Validation

- [x] Five templates authored (main.tf + README.md + metadata.json) plus shared notes
- [x] Plain compute: no aibridge/claude-code module, no `coder_ai_task`, no `ANTHROPIC_*`/AI Gateway env
- [x] Invariants kept: required GitLab external auth (`id="gitlab"`, not optional), subdomain apps, ECR `enterprise-base` only, uid 1000, namespace `coder-workspaces`, gp3 PVC at `/home/coder`
- [x] Routing-friendly `description` per template (in metadata.json and WS-25-templates.md)
- [x] `ai-agent-generic` hardened: `allow_privilege_escalation = false`, no sudo, egress note
- [x] No emdash/endash/spaced double hyphen (dash-scan clean)
- [ ] **root:** `terraform fmt`/`validate` or `coder templates push` succeeds for each
- [ ] **root:** test workspace per template reaches Connected (C4) after GitLab login
- [ ] **root:** at least one app URL per template loads (C3); JupyterLab loads for `data-scientist`
- [ ] **root:** Coder Agents routes each example issue to the expected template
- [ ] **root:** owner sees workspaces across orgs `coder`/`alpha`/`bravo`

## Blockers

- None for authoring. Push/build/test require live Coder access and the
  in-boundary GitLab login, which only root performs.

## Notes for orchestrator

- The existing `coder-templates/claude-code` was left intact; nothing outside
  the assigned paths was touched.
- `coder templates push` does not apply `metadata.json`; the routing
  `description` (the Coder Agents auto-selection signal) MUST be set with
  `coder templates edit ... --description`. Commands are provided.
- `platform-engineer` startup fetches kubectl/helm/terraform from external
  endpoints. If workspace egress is restricted, prebake an image; the installs
  are tolerant so the build still succeeds and C4 still passes.
- Icons use built-in `/icon/*.svg` paths (`cpp`, `java`, `kubernetes`,
  `python`, `coder`). If any is missing in this Coder build, swap it; it is
  cosmetic and does not affect routing or C4.
- Suggested template `_shared` is documentation only; Coder uploads only the
  pushed directory, so each `main.tf` is self-contained by design.
