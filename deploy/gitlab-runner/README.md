# GitLab CI runners (Istio-safe)

GitLab Runner for the usgov-coderdemo GovCloud demo, plus the demo GitLab
project `coderdemo/coder-templates` with two default-branch CI stages:

- `build-images`: builds the UBI9 workspace images (`ubi9-base-workspace` then
  `ubi9-node-workspace`) with Kaniko (rootless, unprivileged, no
  docker-in-docker) and pushes them to the project's GitLab Container Registry.
- `push-template`: pushes a Coder template (which consumes the CI-built
  `ubi9-node-workspace` image) to the GovCloud Coder.

- **GitLab**: `https://gitlab.usgov.coderdemo.io` (CE 19.0.1, ns `gitlab`).
- **Container Registry**: `https://registry.usgov.coderdemo.io` (bundled with
  GitLab CE, fronted by the Istio gateway).
- **Coder**: `https://dev.usgov.coderdemo.io` (orgs `coder`, `alpha`, `bravo`).
- **Runner namespace**: `gitlab-runner` (NOT in the Istio mesh).

## Why this is Istio-safe

Mesh-wide STRICT mTLS is enforced (`istio-system/default` PeerAuthentication).
The meshed namespaces are `coder`, `keycloak`, and `gitlab`. A plain-text
connection from a non-meshed pod to a meshed Service (for example
`gitlab.gitlab.svc:80`) is refused under STRICT.

This deployment avoids that hop entirely:

| Concern | Decision |
|---|---|
| Sidecar lifecycle vs. short-lived CI pods | `gitlab-runner` namespace is kept **out** of the mesh (`istio-injection: disabled`). |
| Runner -> GitLab | Runner registers/polls the **external** URL `https://gitlab.usgov.coderdemo.io`. |
| CI job -> Coder | The `push-template` job uses the **external** URL `https://dev.usgov.coderdemo.io`. |
| CI job -> Container Registry | The `build-images` job pulls/pushes over the **external** URL `https://registry.usgov.coderdemo.io`. |
| Where mTLS happens | All three external URLs resolve to the **Istio ingress gateway** NLB; the gateway is in the mesh and performs mTLS to the `gitlab`/`coder` workloads. |

So nothing the runner or its jobs do requires a plain-text hop to a meshed
Service. The secured (mTLS) hop still happens, just at the gateway. Pods in a
non-meshed namespace reach the gateway NLB via hairpin, the same path Coder
workspace agents already use.

## Egress and image sourcing

The `gitlab-runner` namespace has internet egress (verified:
`registry.access.redhat.com`, `dl.fedoraproject.org`, `rpm.nodesource.com`,
`download.rockylinux.org`, `starship.rs`), so this is **not** a strict air gap.
Kaniko pulls the UBI base and `dnf`-installs directly. The runner manager,
executor helper, Kaniko, and coder job images are still ECR mirrors
(`scripts/images.txt` + `scripts/mirror-images.sh`) for speed and reliability:

| Role | ECR image |
|---|---|
| Runner manager | `docker-hub/gitlab/gitlab-runner:v19.0.1` |
| Executor helper | `docker-hub/gitlab/gitlab-runner-helper:x86_64-v19.0.1` |
| `build-images` job image | `gcr/kaniko-project/executor:v1.24.0-debug` |
| `push-template` job image | `ghcr/coder/coder:v2.34.0` (ships `/bin/sh` + the `coder` CLI) |

The runner + helper versions are pinned to match the GitLab CE server (19.0.1).
Each job overrides its image entrypoint (`entrypoint: [""]`) so the runner's
shell runs the job script.

## Container Registry + UBI9 image build

`build-images` builds two images with Kaniko and pushes them to the project's
own GitLab Container Registry (`$CI_REGISTRY_IMAGE`,
`registry.usgov.coderdemo.io/coderdemo/coder-templates`):

1. `ubi9-base-workspace` `FROM registry.access.redhat.com/ubi9/ubi:9.7`, adding
   dev tooling (EPEL, a Rocky `tmux` RPM, starship, a uid-1001 `coder` user with
   group-0 home perms).
2. `ubi9-node-workspace` `FROM` the just-pushed immutable `:9.7-<sha>` base,
   adding Node 22 LTS and a C++ toolchain.

Each image is pushed with three tags: `:latest`, `:9.7`, and `:9.7-<short-sha>`.
Kaniko authenticates with only the built-in CI job token (`$CI_REGISTRY_*`),
which can pull the base it just pushed and push the result inside this project.

The bundled GitLab Container Registry is enabled in `deploy/gitlab/`
(`statefulset.yaml`, `service.yaml`): the registry speaks plain HTTP on `:5050`
and trusts the gateway's forwarded-proto header, and TLS terminates upstream at
the NLB / Istio gateway using the existing `*.usgov.coderdemo.io` ACM cert.
`deploy/gitlab/virtualservice-registry.yaml` routes
`registry.usgov.coderdemo.io` through the shared `public-gateway` to the
`gitlab` Service `:5050`.

> The CI-built images live in a **private** project registry. A real workspace
> boot needs a `kubernetes.io/dockerconfigjson` pull Secret in
> `coder-workspaces` (passed to the template via `image_pull_secret`). Template
> import (`terraform plan`) does not pull the image, so import and CI work
> without it.

## Files

| File | Purpose |
|---|---|
| `namespace.yaml` | `gitlab-runner` namespace, explicitly out of the mesh. |
| `externalsecret.yaml` | ESO `ExternalSecret` syncing the runner auth token from ASM (`usgov-coderdemo/gitlab/runner`) into the `gitlab-runner-auth` Secret. |
| `values.yaml` | Helm values: ECR images, external `gitlabUrl`, Kubernetes executor, least-privilege RBAC, per-job resource override allowances for the Kaniko build. |
| `coder-templates-example/` | In-git copy of the demo GitLab project (UBI9 image build contexts under `images/`, the Coder template under `template/`, and `.gitlab-ci.yml`). |

The bundled Container Registry that the build job pushes to lives in
`deploy/gitlab/` (`statefulset.yaml`, `service.yaml`,
`virtualservice-registry.yaml`).

## Deploy

Prereqs: `. ~/.config/usgov-coderdemo/env`, `export KUBECONFIG=...`,
`export PATH="$HOME/.local/bin:$PATH"`, and the runner/helper/Kaniko/coder
images mirrored.

```sh
# 1. Mirror images (idempotent).
./scripts/mirror-images.sh --file scripts/images.txt

# 2. Recreate the GitLab project + CI variables + Coder token + group runner
#    token. Deletes root/coder-templates and creates coderdemo/coder-templates.
#    (Writes the runner auth token to ASM usgov-coderdemo/gitlab/runner.)
python3 scripts/setup-gitlab-ci-runners.py

# 3. Namespace + ESO secret (materializes gitlab-runner-auth from ASM).
kubectl apply -f deploy/gitlab-runner/namespace.yaml
kubectl apply -f deploy/gitlab-runner/externalsecret.yaml

# 4. Re-sync the rotated runner token and (re)install/roll the runner so it
#    re-registers with the new GROUP token.
kubectl -n gitlab-runner delete secret gitlab-runner-auth --ignore-not-found
kubectl -n gitlab-runner annotate externalsecret gitlab-runner-auth \
  force-sync=$(date +%s) --overwrite
helm repo add gitlab https://charts.gitlab.io
helm repo update gitlab
helm upgrade --install gitlab-runner gitlab/gitlab-runner \
  --version 0.89.1 --namespace gitlab-runner \
  -f deploy/gitlab-runner/values.yaml

# 5. Confirm the runner is online.
kubectl -n gitlab-runner get pods
#    GitLab UI: group coderdemo > Build > Runners (green), or project
#    coder-templates > Settings > CI/CD > Runners.
```

## Verify end to end

Trigger a pipeline on `coderdemo/coder-templates` (the seed commit carries
`[skip ci]`, so trigger one explicitly via the API/rails or by pushing a commit).
Both stages run in `gitlab-runner` job pods.

`build-images` runs Kaniko and pushes `ubi9-base-workspace` and
`ubi9-node-workspace` (`:latest`, `:9.7`, `:9.7-<sha>`). Confirm the registry
served the push through the gateway and the tags exist:

```sh
# Gateway-served registry (expect 401 Bearer challenge, server: istio-envoy).
curl -sS -D - -o /dev/null https://registry.usgov.coderdemo.io/v2/

# Tags: GitLab UI > project coder-templates > Deploy > Container Registry.
```

`push-template` executes
`coder templates push claude-code-ci --directory ./template --variable namespace=coder-workspaces --variable image_registry=$CI_REGISTRY_IMAGE --org coder --yes`
and applies `template/metadata.json`. Confirm the new version in Coder:

```sh
curl -s https://dev.usgov.coderdemo.io/api/v2/organizations/<coder-org-id>/templates \
  -H "Coder-Session-Token: <admin>" | python3 -m json.tool
```

## Secret handling

- **Runner authentication token** (`glrt-...`): source of truth in AWS Secrets
  Manager (`usgov-coderdemo/gitlab/runner`), synced into the cluster by ESO.
  Never committed. A **group** runner token on `coderdemo` serves
  `coderdemo/coder-templates`.
- **Coder CI token** (`CODER_SESSION_TOKEN`): a rotating Coder API token stored
  only as a masked + protected GitLab CI/CD variable on the project. Never
  committed.
- Re-run `scripts/setup-gitlab-ci-runners.py` to rotate the Coder token and
  reconcile the project/variables/runner token in place.

> Coder caps token lifetime at the server's `max_token_lifetime`. This deploy
> sets both `CODER_MAX_TOKEN_LIFETIME` and `CODER_MAX_ADMIN_TOKEN_LIFETIME` to
> `8760h` (1 year) in `deploy/coder/values.yaml`, so the admin-minted CI token
> lasts a year. The setup script issues the token at that maximum and is safe
> to re-run on a schedule to rotate it. Admin-user tokens are governed by the
> separate `CODER_MAX_ADMIN_TOKEN_LIFETIME`; both caps must be raised for an
> admin-minted token to exceed the 168h default.
