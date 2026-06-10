# WS-25 handoff

- **Status:** PUSHED + CONFIGURED (orgs coder and alpha). All 5 templates imported (terraform plan passed), display-name/icon/routing-description applied. One template bug fixed (platform-engineer heredoc escaping). Interactive build + C4 still needs a one-time GitLab OAuth login (manual).
- **Agent:** sub-agent WS-25 (workspace template family)
- **Timestamp:** 2026-06-08T06:28:31Z
- **Git commit:** none (authoring sub-agent does not run git; root commits ws-2x/phase2)
- **Branch:** ws-2x/phase2

## Resolution (2026-06-08, later): github recovered, push completed

Github egress recovered. All five templates were pushed to org `coder` and org
`alpha` (terraform plan passed for each; intermittent 504s were ridden out with
retries). Two real issues were found and fixed during the live push, neither
visible to `terraform fmt`:
1. `platform-engineer` failed terraform plan because bash `${TFVER}`/`${GOARCH}`
   in the agent `startup_script` heredoc were parsed as terraform
   interpolations. Fixed by doubling the braces to `$${...}` (committed).
2. `coder templates edit --description` returned HTTP 500
   (`pq: value too long for type character varying(128)`) for four templates:
   the template `description` column is `varchar(128)`. Descriptions were
   shortened to <=128 characters in each `metadata.json` and in this doc's
   per-template commands, then applied. KEEP routing descriptions <=128 chars.

The routing `description`, `display_name`, and `icon` are now set on all five
templates in both orgs (verified by the CLI `Updated template metadata` success
and the coderd audit log). claude-code and claude-code-ci were left untouched.


Root authenticated the coder CLI to https://dev.usgov.coderdemo.io (org via
`CODER_ORGANIZATION` env or `--org`; the `-O` shorthand is rejected before the
subcommand) and attempted `coder templates push ai-agent-generic --directory
coder-templates/ai-agent-generic --yes` to org `coder`. The provisioner import
got through module download and installed `hashicorp/kubernetes` v3.2.0, then
failed installing `coder/coder` v2.18.0 with:
`failed to retrieve cryptographic signature for provider: ... 504 Gateway
Timeout returned from github.com`. Seven spaced retries over several minutes all
hit the same 504. A direct `curl https://github.com` from the workspace also
returns 504, so github (the terraform-provider release host) is unreachable from
this environment right now. This is the same transient class that the recreation
push-template job hit earlier today and cleared on retry.

This is NOT a template defect:
- `terraform fmt -check` passes for all five templates (static, no network).
- The provider constraints match the proven `claude-code` template exactly
  (`coder/coder >= 2.13.0`, `hashicorp/kubernetes >= 2.23`); no divergence.
- The provisioner has no local provider cache or filesystem mirror
  (`CODER_CACHE_DIRECTORY=/home/coder/.cache/coder` is empty), so every import
  re-downloads from github; nothing template-side avoids that.

Ready-to-run when github egress recovers (push to org coder, then alpha):
```sh
. ~/.config/usgov-coderdemo/env; export PATH="$HOME/.local/bin:$PATH"
export CODER_URL=https://dev.usgov.coderdemo.io
export CODER_SESSION_TOKEN=...   # admin token via /api/v2/users/login
cd /home/coder/demoenv-workspace/usgov-phase2
for ORG in coder alpha; do for T in cpp-engineer java-engineer platform-engineer data-scientist ai-agent-generic; do
  CODER_ORGANIZATION="$ORG" coder templates push "$T" --directory "coder-templates/$T" --yes
done; done
```
The interactive build + C4 test still needs a one-time in-boundary GitLab OAuth
login by the owner, so it remains a manual demo-prep step regardless of github.

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
| `cpp-engineer` | C/C++ Engineer | C/C++ workspace: clang, gcc, CMake, Ninja, gdb, valgrind. Use for C/C++ services, native libraries, and systems programming. | ECR `enterprise-base:ubuntu-noble-20260601` | enabled |
| `java-engineer` | Java Engineer | Java/JVM workspace: OpenJDK 21, Maven, Gradle. Use for Java and Kotlin services, Spring Boot apps, and JVM build tooling. | ECR `enterprise-base:ubuntu-noble-20260601` | enabled |
| `platform-engineer` | Platform Engineer | Platform/DevOps workspace: kubectl, Helm, Terraform, AWS CLI, jq. Use for IaC, Kubernetes ops, and cloud platform work. | ECR `enterprise-base:ubuntu-noble-20260601` | enabled |
| `data-scientist` | Data Scientist | Data science workspace: Python 3, JupyterLab, pip/venv. Use for notebooks, data analysis, and ML prototyping. | ECR `enterprise-base:ubuntu-noble-20260601` | enabled |
| `ai-agent-generic` | Generic Agent Runtime | Generic agent runtime: plain compute, no LLM tooling. Default for server-side Coder Agents tasks not language-specific. | ECR `enterprise-base:ubuntu-noble-20260601` | disabled (`no_new_privs`) |

Full base-image ref:
`<AWS_ACCOUNT_ID>.dkr.ecr.us-gov-west-1.amazonaws.com/docker-hub/codercom/enterprise-base:ubuntu-noble-20260601`.

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
- [x] **root:** `coder templates push` per template succeeds (orgs coder + alpha); terraform plan passes; platform-engineer heredoc bug fixed
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
