# GitLab SCM

GitLab CE `19.0.1-ce.0` is the in-boundary source-control manager at
`https://gitlab.usgov.coderdemo.io` (namespace `gitlab`). It is wired into Coder
as a git external-auth provider, so workspace git operations stay inside the
GovCloud boundary with no github.com egress.

Source of truth: `docs/as-built/50-gitlab-scm.md`, `deploy/gitlab/`,
`deploy/coder/values.yaml`.

## Deployment

GitLab runs as a single-container Omnibus image in a one-replica `StatefulSet`
(not the Helm chart).

| Aspect | Value |
|---|---|
| Image | ECR mirror of `docker.io/gitlab/gitlab-ce:19.0.1-ce.0` |
| Workload | `StatefulSet`, `replicas: 1`, `serviceName: gitlab` |
| Database | EMBEDDED PostgreSQL bundled in the Omnibus image (not RDS) |
| External URL | `https://gitlab.usgov.coderdemo.io`, bundled NGINX on plain HTTP `:80`, forces `X-Forwarded-Proto=https` |
| Storage | 3 gp3 PVCs: `etc-gitlab` 2Gi, `var-opt-gitlab` 20Gi, `var-log-gitlab` 5Gi |
| First boot | runs migrations and asset load; `startupProbe` allows roughly 15 minutes |

!!! warning "Slow first boot is normal"
    First boot can take 15 to 20 minutes while migrations and assets load. Do not
    mistake a slow first boot for failure.

The live front door is the shared Istio ingress gateway for both
`gitlab.usgov.coderdemo.io` and `registry.usgov.coderdemo.io`; the nginx Ingress
is the retained rollback path. Git over SSH is not exposed; HTTPS clone/push is
the supported path.

## Coder git external auth (provider 0)

Coder consumes an instance-wide GitLab OAuth app named "Coder" as external-auth
provider index 0.

```text
CODER_EXTERNAL_AUTH_0_ID           = gitlab
CODER_EXTERNAL_AUTH_0_TYPE         = gitlab
CODER_EXTERNAL_AUTH_0_DISPLAY_NAME = GitLab
CODER_EXTERNAL_AUTH_0_AUTH_URL     = https://gitlab.usgov.coderdemo.io/oauth/authorize
CODER_EXTERNAL_AUTH_0_TOKEN_URL    = https://gitlab.usgov.coderdemo.io/oauth/token
CODER_EXTERNAL_AUTH_0_VALIDATE_URL = https://gitlab.usgov.coderdemo.io/oauth/token/info
CODER_EXTERNAL_AUTH_0_REGEX        = gitlab\.usgov\.coderdemo\.io
CODER_EXTERNAL_AUTH_0_SCOPES       = read_user read_repository write_repository
```

The OAuth app client id and secret are supplied to Coder via Secret
`coder-external-auth` (keys `gitlab-client-id`, `gitlab-client-secret`). A
self-managed GitLab requires the explicit auth/token/validate URLs above.

## Every workspace template requires GitLab login

The `claude-code` template declares the GitLab external-auth data source, which
makes a GitLab login mandatory before a workspace agent reports ready:

```hcl
data "coder_external_auth" "gitlab" {
  id = "gitlab"   # MUST match CODER_EXTERNAL_AUTH_0_ID on the Coder server
}
```

The dashboard surfaces a "Login with GitLab" control; the agent only reports
ready once the owner completes the in-boundary GitLab OAuth flow. The agent's git
credential helper then injects a short-lived OAuth token for clone/fetch/push, so
no PATs or SSH keys live in the workspace.

## Keycloak SSO and roles

GitLab signs in through the same realm `coder` via the OmniAuth
`openid_connect` provider (confidential client `gitlab`, PKCE S256), created by
`scripts/setup-gitlab-oidc.py`. The client secret lives in AWS Secrets Manager
(`usgov-coderdemo/gitlab/oidc`) and is synced by ESO.

GitLab **Community Edition has no OIDC group-to-role mapping** (an EE/Premium
feature), so persona users and the instance admin attribute are provisioned
explicitly by `scripts/setup-gitlab-users.py`: it links each user to its
`openid_connect` identity and sets GitLab instance admin only on
`austen.platform`, keeping every demo persona a regular user.

## CI runners and the Container Registry

GitLab CI runs in-boundary on EKS in a dedicated, non-meshed namespace
`gitlab-runner`, and the bundled GitLab Container Registry is enabled at
`https://registry.usgov.coderdemo.io` (routed through the Istio gateway). A demo
project `root/coder-templates` defines two jobs: `push-template` (pushes a
`claude-code-ci` template to Coder) and `build-workspace-image` (Kaniko build,
rootless and unprivileged, pushed to the project registry). The air-gapped
supply chain is `docker.io -> ECR -> the project Container Registry`. See
`docs/as-built/50-gitlab-scm.md` for the full CI detail.
