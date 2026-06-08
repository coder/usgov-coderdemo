# GitLab CI runners (Istio-safe, air-gapped)

GitLab Runner for the usgov-coderdemo GovCloud demo, plus a demo "Coder
templates" GitLab project with two default-branch CI jobs:

- `push-template`: pushes a Coder template to the GovCloud Coder.
- `build-workspace-image`: builds a custom workspace image with Kaniko
  (rootless, unprivileged, no docker-in-docker) and pushes it to the project's
  GitLab Container Registry.

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
| CI job -> Container Registry | The `build-workspace-image` job pulls/pushes over the **external** URL `https://registry.usgov.coderdemo.io`. |
| Where mTLS happens | All three external URLs resolve to the **Istio ingress gateway** NLB; the gateway is in the mesh and performs mTLS to the `gitlab`/`coder` workloads. |

So nothing the runner or its jobs do requires a plain-text hop to a meshed
Service. The secured (mTLS) hop still happens, just at the gateway. Pods in a
non-meshed namespace reach the gateway NLB via hairpin (verified: GitLab
`/-/health` -> 200, Coder `/api/v2/buildinfo` -> 200 from a non-meshed pod), the
same path Coder workspace agents already use.

DNS check (all resolve to the Istio gateway NLB, not the legacy nginx NLB):

```sh
getent hosts gitlab.usgov.coderdemo.io dev.usgov.coderdemo.io
```

## Air gap (ECR mirrors)

Every image is mirrored to ECR (`scripts/images.txt` + `scripts/mirror-images.sh`);
nothing is pulled from the internet at runtime:

| Role | ECR image |
|---|---|
| Runner manager | `docker-hub/gitlab/gitlab-runner:v19.0.1` |
| Executor helper | `docker-hub/gitlab/gitlab-runner-helper:x86_64-v19.0.1` |
| `push-template` job image | `ghcr/coder/coder:v2.34.0` (ships `/bin/sh` + the `coder` CLI) |
| `build-workspace-image` job image | `gcr/kaniko-project/executor:v1.24.0-debug` (ships a busybox shell at `/busybox`) |
| Workspace base image | `docker-hub/library/debian:bookworm-slim` (pre-seeded into the GitLab CR) |

The runner + helper versions are pinned to match the GitLab CE server (19.0.1).
Each job overrides its image entrypoint (`entrypoint: [""]`) so the runner's
shell runs the job script.

## Container Registry + custom image build (air-gapped)

The demo shows a custom workspace image built end to end with no internet
egress. The supply chain is `docker.io -> ECR -> the project's GitLab Container
Registry`:

1. `scripts/setup-gitlab-ci-runners.py` pre-seeds the base into the project
   registry with `crane` (`<ecr>/docker-hub/library/debian:bookworm-slim ->
   registry.usgov.coderdemo.io/root/coder-templates/workspace-base:bookworm-slim`),
   authenticating with a short-lived registry-scoped root PAT it rotates on each
   run (never printed; staged to a 0600 file and removed).
2. The `build-workspace-image` CI job runs Kaniko, builds `FROM` that
   project-local base, and pushes
   `registry.usgov.coderdemo.io/root/coder-templates/custom-workspace:<sha>` and
   `:latest`. It authenticates with only the built-in CI job token
   (`$CI_REGISTRY_*`), so no external or base-registry credentials are needed in
   the build.

The bundled GitLab Container Registry is enabled in `deploy/gitlab/`
(`statefulset.yaml`, `service.yaml`): the registry NGINX speaks plain HTTP on
`:5050` and trusts the gateway's forwarded-proto header, and TLS terminates
upstream at the NLB / Istio gateway using the existing `*.usgov.coderdemo.io`
ACM cert. `deploy/gitlab/virtualservice-registry.yaml` routes
`registry.usgov.coderdemo.io` through the shared `public-gateway` to the
`gitlab` Service `:5050`.

## Files

| File | Purpose |
|---|---|
| `namespace.yaml` | `gitlab-runner` namespace, explicitly out of the mesh. |
| `externalsecret.yaml` | ESO `ExternalSecret` syncing the runner auth token from ASM (`usgov-coderdemo/gitlab/runner`) into the `gitlab-runner-auth` Secret. |
| `values.yaml` | Helm values: ECR images, external `gitlabUrl`, Kubernetes executor, least-privilege RBAC. |
| `coder-templates-example/` | In-git copy of the demo GitLab project (Coder template, custom-image `image/` build context, and `.gitlab-ci.yml`). |

The bundled Container Registry that the build job pushes to lives in
`deploy/gitlab/` (`statefulset.yaml`, `service.yaml`,
`virtualservice-registry.yaml`).

## Deploy

Prereqs: `. ~/.config/usgov-coderdemo/env`, `export KUBECONFIG=...`,
`export PATH="$HOME/.local/bin:$PATH"`, the runner/helper/Kaniko/base images
mirrored, and `crane` on PATH (the setup script uses it to pre-seed the
registry base).

```sh
# 1. Mirror images (idempotent).
./scripts/mirror-images.sh --file scripts/images.txt

# 2. Create the GitLab project + CI variables + Coder token + runner token,
#    and pre-seed the workspace base into the project Container Registry.
#    (Writes the runner auth token to ASM usgov-coderdemo/gitlab/runner.)
python3 scripts/setup-gitlab-ci-runners.py

# 3. Namespace + ESO secret (materializes gitlab-runner-auth from ASM).
kubectl apply -f deploy/gitlab-runner/namespace.yaml
kubectl apply -f deploy/gitlab-runner/externalsecret.yaml
kubectl -n gitlab-runner get externalsecret gitlab-runner-auth -w   # SecretSynced

# 4. Install the runner.
helm repo add gitlab https://charts.gitlab.io
helm repo update gitlab
helm upgrade --install gitlab-runner gitlab/gitlab-runner \
  --version 0.89.1 --namespace gitlab-runner \
  -f deploy/gitlab-runner/values.yaml

# 5. Confirm the runner is online.
kubectl -n gitlab-runner get pods
#    GitLab UI: project coder-templates > Settings > CI/CD > Runners (green).
```

## Verify end to end

Push a commit to `root/coder-templates` (or run the pipeline). Both jobs run in
`gitlab-runner` job pods.

`push-template` executes
`coder templates push claude-code-ci --directory ./template --yes --org coder`.
Confirm the new version in Coder:

```sh
curl -s https://dev.usgov.coderdemo.io/api/v2/organizations/<coder-org-id>/templates \
  -H "Coder-Session-Token: <admin>" | python3 -m json.tool
```

`build-workspace-image` runs Kaniko and pushes `custom-workspace:<sha>` and
`:latest`. Confirm the registry served the push through the gateway and the tags
exist:

```sh
# Gateway-served registry (expect 401 Bearer challenge, server: istio-envoy).
curl -sS -D - -o /dev/null https://registry.usgov.coderdemo.io/v2/

# Tags (GitLab UI: project coder-templates > Deploy > Container Registry).
```

## Secret handling

- **Runner authentication token** (`glrt-...`): source of truth in AWS Secrets
  Manager (`usgov-coderdemo/gitlab/runner`), synced into the cluster by ESO.
  Never committed.
- **Coder CI token** (`CODER_SESSION_TOKEN`): a rotating Coder API token stored
  only as a masked + protected GitLab CI/CD variable on the project. Never
  committed.
- Re-run `scripts/setup-gitlab-ci-runners.py` to rotate the Coder token and
  reconcile the project/variables/runner token in place.

> Coder caps token lifetime at the server's `max_token_lifetime` (currently
> 7 days, the default). The setup script issues the token at that maximum and is
> safe to re-run on a schedule to rotate it. To issue longer-lived CI tokens,
> raise `CODER_MAX_TOKEN_LIFETIME` on the Coder server.
