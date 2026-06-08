# coder-templates (demo)

GitOps for Coder templates: edit a template here, push to the default branch,
and GitLab CI pushes the new version to the GovCloud Coder at
`https://dev.usgov.coderdemo.io`.

This directory is the canonical, in-git copy of the demo GitLab project that
`scripts/setup-gitlab-ci-runners.py` seeds into the in-cluster GitLab
(`https://gitlab.usgov.coderdemo.io`, project `root/coder-templates`).

## Layout

| Path | Purpose |
|---|---|
| `.gitlab-ci.yml` | CI pipeline: `push-template` (deploy) and `build-workspace-image` (Kaniko) on default-branch commits. |
| `template/` | A working Coder template (the `claude-code` workspace template). |
| `image/` | Build context for the sample custom workspace image (Dockerfile + `profile.d/`). |

## How it works

The pipeline has two stages, both on the same `gitlab-runner` Kubernetes
executor (non-meshed `gitlab-runner` namespace), each picking its own
ECR-mirrored image.

### Stage `deploy`: `push-template`

1. A commit lands on the default branch of `root/coder-templates`.
2. The job runs the ECR-mirrored Coder image and executes
   `coder templates push claude-code-ci --directory ./template --yes --org coder`.
3. The coder CLI authenticates with `CODER_SESSION_TOKEN` (a masked + protected
   CI/CD variable) and talks to Coder over `CODER_URL`
   (`https://dev.usgov.coderdemo.io`), entering through the Istio ingress
   gateway. The Coder server dispatches the template import to the `coder`
   organization's provisioner, which runs `terraform plan` and creates a new
   template version.

### Stage `build-image`: `build-workspace-image`

1. The job runs the ECR-mirrored Kaniko `executor:v1.24.0-debug` image
   (rootless, unprivileged, no docker-in-docker).
2. It writes `/kaniko/.docker/config.json` from the built-in CI job token
   (`CI_REGISTRY_USER` / `CI_REGISTRY_PASSWORD`), which can both pull and push
   inside this project's registry.
3. Kaniko builds `image/Dockerfile` `FROM` the project's own GitLab Container
   Registry copy of the base (`${CI_REGISTRY_IMAGE}/workspace-base:bookworm-slim`,
   pre-seeded from the ECR mirror by `scripts/setup-gitlab-ci-runners.py`) and
   pushes `custom-workspace:${CI_COMMIT_SHORT_SHA}` and `:latest` to
   `https://registry.usgov.coderdemo.io` through the Istio gateway.

## Istio + air gap

- The runner and its job pods are OUT of the Istio mesh and reach GitLab, the
  GitLab Container Registry, and Coder over their external gateway URLs, so
  mesh-wide STRICT mTLS is satisfied without a sidecar (the gateway does mTLS to
  the backends).
- Every image (runner, helper, Coder CLI, Kaniko) is an ECR mirror, and the
  Kaniko build's base lives in this project's own registry, so nothing is pulled
  from the internet at build time. Supply chain:
  `docker.io -> ECR -> GitLab Container Registry`.

## Auth / secrets

- `CODER_SESSION_TOKEN`: a long-lived (subject to the Coder server's
  `max_token_lifetime`) Coder API token for a template admin, stored only as a
  masked + protected GitLab CI/CD variable. Never committed.
- The runner authentication token lives in AWS Secrets Manager
  (`usgov-coderdemo/gitlab/runner`) and is synced into the cluster by ESO.

Re-run `scripts/setup-gitlab-ci-runners.py` to (re)create the project, rotate
the Coder token, and refresh the variables.
