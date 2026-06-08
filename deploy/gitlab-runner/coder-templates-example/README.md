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
| `.gitlab-ci.yml` | CI pipeline: `coder templates push` on default-branch commits. |
| `template/` | A working Coder template (the `claude-code` workspace template). |

## How it works

1. A commit lands on the default branch of `root/coder-templates`.
2. GitLab schedules the `push-template` job on the `gitlab-runner` Kubernetes
   executor (non-meshed `gitlab-runner` namespace).
3. The job runs the ECR-mirrored Coder image and executes
   `coder templates push claude-code-ci --directory ./template --yes --org coder`.
4. The coder CLI authenticates with `CODER_SESSION_TOKEN` (a masked + protected
   CI/CD variable) and talks to Coder over `CODER_URL`
   (`https://dev.usgov.coderdemo.io`), entering through the Istio ingress
   gateway. The Coder server dispatches the template import to the `coder`
   organization's provisioner, which runs `terraform plan` and creates a new
   template version.

## Istio + air gap

- The runner and its job pods are OUT of the Istio mesh and reach GitLab and
  Coder over their external gateway URLs, so mesh-wide STRICT mTLS is satisfied
  without a sidecar (the gateway does mTLS to the backends).
- The job image and all runner images are ECR mirrors; nothing is pulled from
  the internet at runtime.

## Auth / secrets

- `CODER_SESSION_TOKEN`: a long-lived (subject to the Coder server's
  `max_token_lifetime`) Coder API token for a template admin, stored only as a
  masked + protected GitLab CI/CD variable. Never committed.
- The runner authentication token lives in AWS Secrets Manager
  (`usgov-coderdemo/gitlab/runner`) and is synced into the cluster by ESO.

Re-run `scripts/setup-gitlab-ci-runners.py` to (re)create the project, rotate
the Coder token, and refresh the variables.
