# GitLab CI runners (Istio-safe, air-gapped)

GitLab Runner for the usgov-coderdemo GovCloud demo, plus a demo "Coder
templates" GitLab project whose CI job pushes a Coder template to the GovCloud
Coder on every default-branch commit.

- **GitLab**: `https://gitlab.usgov.coderdemo.io` (CE 19.0.1, ns `gitlab`).
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
| CI job -> Coder | The job uses the **external** URL `https://dev.usgov.coderdemo.io`. |
| Where mTLS happens | Both external URLs resolve to the **Istio ingress gateway** NLB; the gateway is in the mesh and performs mTLS to the `gitlab`/`coder` workloads. |

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
| Default CI job image | `ghcr/coder/coder:v2.34.0` (ships `/bin/sh` + the `coder` CLI) |

The runner + helper versions are pinned to match the GitLab CE server (19.0.1).
The CI job image is the already-mirrored Coder image; CI overrides its
entrypoint (`entrypoint: [""]`) so the runner's shell runs the job script.

## Files

| File | Purpose |
|---|---|
| `namespace.yaml` | `gitlab-runner` namespace, explicitly out of the mesh. |
| `externalsecret.yaml` | ESO `ExternalSecret` syncing the runner auth token from ASM (`usgov-coderdemo/gitlab/runner`) into the `gitlab-runner-auth` Secret. |
| `values.yaml` | Helm values: ECR images, external `gitlabUrl`, Kubernetes executor, least-privilege RBAC. |
| `coder-templates-example/` | In-git copy of the demo GitLab project (template + `.gitlab-ci.yml`). |

## Deploy

Prereqs: `. ~/.config/usgov-coderdemo/env`, `export KUBECONFIG=...`,
`export PATH="$HOME/.local/bin:$PATH"`, and the runner/helper images mirrored.

```sh
# 1. Mirror images (idempotent).
./scripts/mirror-images.sh --file scripts/images.txt

# 2. Create the GitLab project + CI variables + Coder token + runner token.
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

Push a commit to `root/coder-templates` (or run the pipeline). The
`push-template` job runs in a `gitlab-runner` job pod and executes
`coder templates push claude-code-ci --directory ./template --yes --org coder`.
Confirm the new version in Coder:

```sh
curl -s https://dev.usgov.coderdemo.io/api/v2/organizations/<coder-org-id>/templates \
  -H "Coder-Session-Token: <admin>" | python3 -m json.tool
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
