# coder-templates (demo)

GitOps for Coder workspaces. This project's GitLab CI builds custom UBI9
workspace images and pushes a Coder template that consumes them. A commit to the
default branch:

1. **builds** `ubi9-base-workspace` then `ubi9-node-workspace` with Kaniko and
   pushes them to this project's GitLab Container Registry, and
2. **pushes** a Coder template to the GovCloud Coder at
   `https://dev.usgov.coderdemo.io`.

This directory is the canonical, in-git copy of the demo GitLab project that
`scripts/setup-gitlab-ci-runners.py` seeds into the in-cluster GitLab
(`https://gitlab.usgov.coderdemo.io`, project `coderdemo/coder-templates`).

## Layout

| Path | Purpose |
|---|---|
| `.gitlab-ci.yml` | CI pipeline: `build-images` (Kaniko) then `push-template` (coder CLI), on default-branch commits. |
| `images/ubi9-base-workspace/` | UBI 9.7 base + dev tooling (`Dockerfile` + `uid_entrypoint.sh`). |
| `images/ubi9-node-workspace/` | `FROM` the base, adds Node 22 LTS + C++ toolchain. |
| `template/` | The Coder template (`main.tf`), plus `metadata.json` (icon + display name) and `README.md`. |

## How it works

Both stages run on the same `gitlab-runner` Kubernetes executor (non-meshed
`gitlab-runner` namespace), each picking its own image.

### Stage `build-images` (Kaniko)

1. The job runs the ECR-mirrored Kaniko `executor:v1.24.0-debug` image
   (rootless, unprivileged, no docker-in-docker).
2. It writes `/kaniko/.docker/config.json` from the built-in CI job token
   (`CI_REGISTRY_USER` / `CI_REGISTRY_PASSWORD`), which can both pull and push
   inside this project's registry.
3. Kaniko builds `ubi9-base-workspace` `FROM registry.access.redhat.com/ubi9/ubi:9.7`
   (the `gitlab-runner` namespace has internet egress, so the UBI base pull and
   the `dnf` / EPEL / Rocky-RPM / starship steps work directly), then builds
   `ubi9-node-workspace` `FROM` the just-pushed immutable `:9.7-<sha>` base.
4. Each image is pushed with three tags to
   `registry.usgov.coderdemo.io/coderdemo/coder-templates/<image>`: `:latest`,
   `:9.7`, and `:9.7-<short-sha>`.

### Stage `push-template` (coder CLI)

1. The job runs the ECR-mirrored Coder image and `coder login`s to
   `$CODER_URL` (`https://dev.usgov.coderdemo.io`) with `CODER_SESSION_TOKEN` (a
   masked + protected CI/CD variable).
2. It runs
   `coder templates push claude-code-ci --directory ./template --variable namespace=coder-workspaces --variable image_registry=$CI_REGISTRY_IMAGE --org coder --yes`.
   The Coder server runs `terraform plan` and creates a new template version.
   `image_registry=$CI_REGISTRY_IMAGE` makes the workspace image resolve to the
   `ubi9-node-workspace:latest` the build stage pushed.
3. It applies `template/metadata.json` (icon + display name) with
   `coder templates edit`.

## Istio + egress

- The runner and its job pods are OUT of the Istio mesh and reach GitLab, the
  GitLab Container Registry, and Coder over their external gateway URLs, so
  mesh-wide STRICT mTLS is satisfied without a sidecar (the gateway does mTLS to
  the backends).
- The `gitlab-runner` namespace has internet egress, so Kaniko pulls the UBI
  base and `dnf`-installs directly. This is not a strict air gap; direct egress
  is acceptable for this demo. The Kaniko and coder job images are still ECR
  mirrors for speed and reliability.

## Auth / secrets

- `CODER_SESSION_TOKEN`: a Coder API token for a template admin (subject to the
  Coder server's `max_token_lifetime`), stored only as a masked + protected
  GitLab CI/CD variable. Never committed.
- The runner authentication token lives in AWS Secrets Manager
  (`usgov-coderdemo/gitlab/runner`) and is synced into the cluster by ESO.

Re-run `scripts/setup-gitlab-ci-runners.py` to (re)create the project, rotate
the Coder token, and refresh the variables.
