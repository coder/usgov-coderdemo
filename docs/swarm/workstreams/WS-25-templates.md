# WS-25 - Workspace template family (cpp / java / platform / data-scientist / ai-agent-generic)

| Field | Value |
|---|---|
| **Workstream** | WS-25 (Phase-2 workspace template family) |
| **Owner (authoring)** | sub-agent WS-25 (authoring only; no push/build/git) |
| **Executor (push/build/test)** | root orchestrator |
| **Status** | PARTIAL (authored; awaiting root push + build + connectivity) |
| **Branch** | ws-2x/phase2 |
| **Depends on** | Coder server live (WS-05), EKS + ECR (WS-04/07), GitLab external auth (WS-10), claude-code template proven |

## Goal

Ship a coherent family of EKS workspace templates that are plain compute for
the Coder Agents path (intelligence runs server-side), so a PM can assign a
labeled issue to a developer and Coder Agents launches the right workspace,
auto-selected by the template `description`, with no LLM wiring inside the
workspace.

## Family design

All five reuse one EKS pod pattern adapted from `coder-templates/claude-code`
(pod plus PVC plus `coder_agent` plus `display_apps` plus `code-server`,
securityContext uid 1000, required GitLab external auth, subdomain apps), minus
all AI Gateway / claude-code / `coder_ai_task` wiring. They differ only by
toolchain, one optional extra app, the routing description, the icon, and the
security posture of `ai-agent-generic`. Shared invariants live in
`coder-templates/_shared/README.md`.

| Template | Routing description (auto-selection signal) | Base image (default) | Notable extras |
|---|---|---|---|
| `cpp-engineer` | C/C++ workspace: clang, gcc, CMake, Ninja, gdb, valgrind. Use for C/C++ services, native libraries, and systems programming. | ECR `enterprise-base` | sudo apt toolchain |
| `java-engineer` | Java/JVM workspace: OpenJDK 21, Maven, Gradle. Use for Java and Kotlin services, Spring Boot apps, and JVM build tooling. | ECR `enterprise-base` | sudo apt toolchain |
| `platform-engineer` | Platform/DevOps workspace: kubectl, Helm, Terraform, AWS CLI, jq. Use for IaC, Kubernetes ops, and cloud platform work. | ECR `enterprise-base` | kubectl/helm/terraform fetch |
| `data-scientist` | Data science workspace: Python 3, JupyterLab, pip/venv. Use for notebooks, data analysis, and ML prototyping. | ECR `enterprise-base` | JupyterLab subdomain app |
| `ai-agent-generic` | Generic agent runtime: plain compute, no LLM tooling. Default for server-side Coder Agents tasks not language-specific. | ECR `enterprise-base` | hardened: no sudo, `no_new_privs` |

Base image today is the only mirrored workspace base:
`<AWS_ACCOUNT_ID>.dkr.ecr.us-gov-west-1.amazonaws.com/docker-hub/codercom/enterprise-base:ubuntu-noble-20260601`.
Toolchains are provisioned best-effort at startup (tolerant). Recommended
production end state is a prebaked per-role image; see
`docs/swarm/handoffs/WS-25-handoff.md` for the root mirror/build TODOs.

## End-to-end acceptance plan (RH-Summit demo path)

The demo proves: a PM assigns a coder-agent-labeled issue to a developer, Coder
Agents launches a workspace as that developer, auto-selecting the template by
description, the server-side AI responds, dashboards reflect it, and the super
admin sees everything across orgs.

### Actors and orgs

- **PM**: creates and labels issues in the in-boundary GitLab.
- **Developer** (member of org `alpha`): the assignee the workspace runs as.
- **Coder Agents** (`chatd` on the control plane): picks up the labeled issue,
  creates a Coder Task/workspace delegated to the developer, and routes to a
  template by description.
- **Super admin / owner**: sees all workspaces and Tasks across orgs `coder`,
  `alpha`, and `bravo`.

### Routing-by-description map (what proves auto-selection)

| Example issue title and label | Expected template | Why |
|---|---|---|
| "Fix segfault in libsensor (C++)" `coder-agent` | `cpp-engineer` | C/C++ keywords match the cpp description |
| "Upgrade Spring Boot service to JDK 21" `coder-agent` | `java-engineer` | JVM/Maven/Gradle keywords |
| "Add Helm chart and Terraform for new service" `coder-agent` | `platform-engineer` | kubectl/Helm/Terraform keywords |
| "Notebook: analyze telemetry CSV" `coder-agent` | `data-scientist` | Python/Jupyter/data keywords |
| "Triage flaky integration test" `coder-agent` | `ai-agent-generic` | no language-specific match, fallback |

### Demo sequence

1. **Push the family** (root, both orgs) so all five templates exist with their
   descriptions set. See the per-template commands below.
2. **PM creates a labeled issue** in GitLab and assigns it to the developer.
3. **Coder Agents launches a workspace as the developer**, auto-selecting the
   template whose description best matches the issue. Confirm the selected
   template name matches the routing map.
4. **GitLab login**: the workspace requires the in-boundary GitLab login
   (required external auth). The developer completes "Login with GitLab" once;
   the agent then reports ready and the agentic loop clones the assigned repo.
5. **AI responds**: the server-side agent produces output (a plan, edits, or a
   merge request) using the control-plane provider. No LLM key or AI Gateway
   env exists inside the workspace.
6. **Dashboards reflect it**:
   - Coder workspaces list and Tasks view show the running workspace, its
     template, owner, and activity.
   - Grafana (`metrics.usgov.coderdemo.io`) shows workspace pod CPU/memory.
   - Kiali shows the workspace pod in the mesh (if mesh injection is on).
7. **Super admin sees everything**: the owner lists workspaces across orgs
   `coder`, `alpha`, `bravo` and opens the developer's workspace and Task.

### Acceptance criteria

- [ ] All five templates are pushed to org `alpha` and org `coder`, each with
      its display name, icon, and routing description applied.
- [ ] Each template builds a test workspace whose agent reaches Connected (C4)
      after GitLab login.
- [ ] At least one app URL loads per template (C3): code-server for all,
      plus JupyterLab for `data-scientist`.
- [ ] Coder Agents selects the expected template for each routing-map issue.
- [ ] The owner can see the developer's workspace and Task across orgs.

## Per-template root commands (push, build, C4, cleanup)

> Run from the merged repo root (where `coder-templates/<name>` exists).
> Authoring sub-agent does NOT run these; the root orchestrator does.

### Shell preamble (every session)

```sh
. ~/.config/usgov-coderdemo/env
export KUBECONFIG=/home/coder/demoenv-workspace/usgov-coderdemo/kubeconfig
export PATH="$HOME/.local/bin:$PATH"
# GOTCHA: the ambient CODER_URL points at dev.coder.com and is WRONG.
export CODER_URL=https://dev.usgov.coderdemo.io
coder login "$CODER_URL"   # or: export CODER_SESSION_TOKEN=...
```

### Generic shape (substitute NAME and DIR)

For each template NAME with directory `coder-templates/NAME`, push to both orgs,
apply metadata, build a test workspace, prove C4, then clean up.

```sh
# 1. Push to org alpha and org coder (creates or versions the template).
for ORG in alpha coder; do
  coder templates push "NAME" \
    --directory coder-templates/NAME \
    --org "$ORG" \
    --variable namespace=coder-workspaces \
    --yes
done

# 2. Apply display name, icon, and routing description from metadata.json.
#    (templates push does not read metadata.json; the description is the
#     Coder Agents auto-selection signal, so it MUST be set.)
#    Replace the strings from coder-templates/NAME/metadata.json.
for ORG in alpha coder; do
  coder templates edit "NAME" --org "$ORG" \
    --display-name "DISPLAY_NAME" \
    --icon "ICON" \
    --description "ROUTING_DESCRIPTION" \
    --yes
done

# 3. Build a test workspace in org alpha (run as the test developer).
coder create "test-NAME" \
  --template "NAME" \
  --org alpha \
  --parameter cpu=4 \
  --parameter memory=8 \
  --parameter disk_size=20 \
  --parameter git_repo="" \
  --yes
# NOTE: the workspace requires the in-boundary GitLab login before the agent
# reports ready. Complete "Login with GitLab" in the dashboard once (or via
# `coder external-auth access-token gitlab`) so C4 can pass.

# 4. C4 connectivity check (Agent <-> coderd Connected).
#    Preferred wrapper if present:
scripts/validate-connectivity.sh --track a   # covers C1, C2, C3, C4, C5, C9, C13, C14
#    Coder CLI fallback (no wrapper / targeted check):
coder list                 # the workspace row shows the agent status
coder show "test-NAME"     # agent should read Connected / healthy
coder ping "test-NAME"     # agent reachability probe (clean C4 signal)
#    C3 (app URL) fallback: open the code-server subdomain from `coder show`,
#    e.g. https://<app-host>.usgov.coderdemo.io, and for data-scientist also
#    the JupyterLab app.

# 5. Cleanup (delete the test workspace; keep the template).
coder delete "test-NAME" --yes
```

### Concrete values per template

`cpp-engineer`

```sh
NAME=cpp-engineer
DISPLAY_NAME="C/C++ Engineer"
ICON="/icon/cpp.svg"
ROUTING_DESCRIPTION="C/C++ workspace: clang, gcc, CMake, Ninja, gdb, valgrind. Use for C/C++ services, native libraries, and systems programming."
```

`java-engineer`

```sh
NAME=java-engineer
DISPLAY_NAME="Java Engineer"
ICON="/icon/java.svg"
ROUTING_DESCRIPTION="Java/JVM workspace: OpenJDK 21, Maven, Gradle. Use for Java and Kotlin services, Spring Boot apps, and JVM build tooling."
```

`platform-engineer`

```sh
NAME=platform-engineer
DISPLAY_NAME="Platform Engineer"
ICON="/icon/kubernetes.svg"
ROUTING_DESCRIPTION="Platform/DevOps workspace: kubectl, Helm, Terraform, AWS CLI, jq. Use for IaC, Kubernetes ops, and cloud platform work."
```

`data-scientist`

```sh
NAME=data-scientist
DISPLAY_NAME="Data Scientist"
ICON="/icon/python.svg"
ROUTING_DESCRIPTION="Data science workspace: Python 3, JupyterLab, pip/venv. Use for notebooks, data analysis, and ML prototyping."
```

`ai-agent-generic`

```sh
NAME=ai-agent-generic
DISPLAY_NAME="Generic Agent Runtime"
ICON="/icon/coder.svg"
ROUTING_DESCRIPTION="Generic agent runtime: plain compute, no LLM tooling. Default for server-side Coder Agents tasks not language-specific."
```

## Notes and risks for root

- Pushing the same template to two orgs creates two independent templates with
  the same slug, one per org. That is the intended per-org publish.
- The required GitLab external auth means a fresh test workspace blocks at
  "Login with GitLab" until the owner authenticates once. Do this before
  asserting C4, or the agent will correctly report not-ready.
- Toolchains install best-effort at startup. If the workspace pod egress is
  locked down (especially for `ai-agent-generic`), prebake images instead; see
  the handoff TODOs. A failed install never fails the build, so C4 still passes.
- `coder_app.jupyter` in `data-scientist` depends on the startup launch; if
  JupyterLab did not install, the app shows unhealthy but the workspace is
  still Connected.
- Icons are cosmetic. If a `/icon/*.svg` is missing in this Coder build, the
  template still works; swap to a known icon or a raw URL.

## Validation checklist (root fills in)

- [ ] `cpp-engineer` pushed (alpha, coder), metadata applied, C4 pass
- [ ] `java-engineer` pushed (alpha, coder), metadata applied, C4 pass
- [ ] `platform-engineer` pushed (alpha, coder), metadata applied, C4 pass
- [ ] `data-scientist` pushed (alpha, coder), metadata applied, C4 pass, Jupyter app loads
- [ ] `ai-agent-generic` pushed (alpha, coder), metadata applied, C4 pass
- [ ] Routing map verified for at least one issue per template
- [ ] Owner sees workspaces across orgs
