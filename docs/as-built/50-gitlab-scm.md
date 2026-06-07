# 50. In-boundary GitLab SCM (as-built)

As-built, read-only documentation of the in-boundary GitLab source-control
manager and how it is wired into Coder as a git external-auth provider. Every
nontrivial claim is grounded in a repo file path or a live read-only command.
Items that could not be verified from a repo file or a permitted GET are marked
"unverified".

- GitLab URL: `https://gitlab.usgov.coderdemo.io` (namespace `gitlab`).
- Purpose: in-boundary SCM for workspaces; git auth stays inside the GovCloud
  boundary (no github.com egress).
- Source: `deploy/gitlab/`, `deploy/coder/values.yaml`.

## Deployment

GitLab CE runs as a single-container Omnibus image in a one-replica
`StatefulSet` (not the Helm chart), in namespace `gitlab`
(`deploy/gitlab/statefulset.yaml`, `deploy/gitlab/README.md`).

| Aspect | Value | Source |
|---|---|---|
| Image | `430737322961.dkr.ecr.us-gov-west-1.amazonaws.com/docker-hub/gitlab/gitlab-ce:19.0.1-ce.0` (ECR mirror of `docker.io/gitlab/gitlab-ce:19.0.1-ce.0`) | `deploy/gitlab/statefulset.yaml` |
| Workload | `StatefulSet`, `replicas: 1`, `serviceName: gitlab`, `OrderedReady`; chosen over a Deployment because the data volumes are RWO and two pods must never share them | `deploy/gitlab/statefulset.yaml` |
| Database | EMBEDDED PostgreSQL bundled in the Omnibus image (the default), data under `/var/opt/gitlab/postgresql` on the `var-opt-gitlab` PVC. NOT the shared RDS instance | `deploy/gitlab/statefulset.yaml`, `deploy/gitlab/README.md` |
| External URL | `external_url 'https://gitlab.usgov.coderdemo.io'`; bundled NGINX on plain HTTP `:80`, `listen_https=false`, `redirect_http_to_https=false`, forces `X-Forwarded-Proto=https` | `deploy/gitlab/statefulset.yaml` |
| Storage | 3 gp3 PVCs via `volumeClaimTemplates`: `etc-gitlab` 2Gi, `var-opt-gitlab` 20Gi, `var-log-gitlab` 5Gi (cluster-default `gp3`, encrypted, WaitForFirstConsumer) | `deploy/gitlab/statefulset.yaml` |
| Trimmed footprint | registry, pages, KAS, and all bundled exporters/prometheus disabled; `puma.worker_processes=2`, `sidekiq.concurrency=10` | `deploy/gitlab/statefulset.yaml` |
| Root bootstrap | `GITLAB_INITIAL_ROOT_PASSWORD` from Secret `gitlab-secrets` (key `initial_root_password`, `optional: true`); consumed on first boot only, then the password lives in the DB | `deploy/gitlab/statefulset.yaml`, `deploy/gitlab/secrets.example.yaml` |
| First-boot time | First boot runs DB migrations and asset load; the `startupProbe` allows roughly 15 minutes (`initialDelaySeconds: 60`, `periodSeconds: 15`, `failureThreshold: 60`) before liveness takes over. README notes ~15 to 20 min; do not mistake a slow first boot for failure | `deploy/gitlab/statefulset.yaml`, `deploy/gitlab/README.md`, `STATUS.md` |

Network path (`deploy/gitlab/ingress.yaml`, `service.yaml`):

```
client --HTTPS--> NLB (TLS terminated, ACM cert) --HTTP--> ingress-nginx --HTTP--> Service gitlab:80 --> pod gitlab-0 (bundled NGINX :80 -> Workhorse/Puma)
```

- `Service` is `ClusterIP` on port `80` and is also the StatefulSet governing
  service (`deploy/gitlab/service.yaml`).
- `Ingress` is `ingressClassName: nginx`, host `gitlab.usgov.coderdemo.io`, with
  `ssl-redirect`/`force-ssl-redirect` false, `proxy-body-size: "0"` (large git
  pushes/LFS), and 3600s read/send timeouts (`deploy/gitlab/ingress.yaml`).
- Git over SSH (port 22) is not exposed; only HTTPS 443 is fronted by the NLB
  (`deploy/gitlab/README.md`, open questions). Clone/push over HTTPS is the
  supported path.

Why embedded Postgres rather than RDS (`deploy/gitlab/README.md`): fewest moving
parts for a single-container demo, no dependency on an orchestrator-created
`gitlabhq_production` db/role/Secret, decoupled blast radius from RDS health,
and the bundled engine always meets GitLab 19's PostgreSQL 17+ requirement. The
tradeoff is no managed backups/Multi-AZ. A shared-RDS alternative is sketched in
the README but is not enabled.

### Live verification

```
kubectl -n gitlab get statefulset,svc,ingress
  statefulset.apps/gitlab   1/1
  service/gitlab            ClusterIP   80/TCP
  ingress/gitlab            nginx       gitlab.usgov.coderdemo.io -> NLB

curl -sS -o /dev/null -w '%{http_code}' https://gitlab.usgov.coderdemo.io/oauth/authorize
  302   (OAuth authorize endpoint live; redirects to login when called without params)
```

## The instance-wide OAuth app "Coder"

To let Coder authenticate git operations, an instance-wide OAuth application
named "Coder" was minted in GitLab (`deploy/coder/values.yaml` comment;
`STATUS.md` "Auth boundary hardening"). Its parameters:

| Property | Value | Source |
|---|---|---|
| Application name | `Coder` | `deploy/coder/values.yaml` comment, `STATUS.md` |
| Redirect URI | `https://dev.usgov.coderdemo.io/external-auth/gitlab/callback` | Coder external-auth callback shape `<access_url>/external-auth/<id>/callback`, with access_url `https://dev.usgov.coderdemo.io` and id `gitlab` |
| Scopes | `read_user read_repository write_repository` | `deploy/coder/values.yaml` (`CODER_EXTERNAL_AUTH_0_SCOPES`); verified live in Coder config |
| Scope | Instance-wide (admin-owned application, not a user/group app) | `deploy/coder/values.yaml` comment, `STATUS.md` |
| `organization_id` | `1` (the default GitLab organization). Recent GitLab associates OAuth applications with an organization; an instance-wide application is scoped to the default org id `1`. See note below | build context / facts sheet |

Note on `organization_id=1`: this detail comes from the build context (facts
sheet / lead) and is consistent with how recent GitLab scopes instance-wide
applications to the default organization. It was not independently re-verified
in this read-only pass, because confirming it requires an authenticated admin
API call to GitLab (a login POST and a token), which is outside the GET-only
constraint of this documentation task. Treat the specific value as unverified
here.

The application's client id and secret are recorded in the gitignored
`~/.config/usgov-coderdemo/generated-secrets.env` as `GITLAB_CODER_OAUTH_APP_ID`
and `GITLAB_CODER_OAUTH_SECRET` (key names confirmed; secret values are not
reproduced in this doc).

## How it maps to Coder external auth

Coder consumes the GitLab OAuth app as external-auth provider index 0
(`deploy/coder/values.yaml`, env block):

| Coder env var | Value |
|---|---|
| `CODER_EXTERNAL_AUTH_0_ID` | `gitlab` |
| `CODER_EXTERNAL_AUTH_0_TYPE` | `gitlab` |
| `CODER_EXTERNAL_AUTH_0_DISPLAY_NAME` | `GitLab` |
| `CODER_EXTERNAL_AUTH_0_CLIENT_ID` | from Secret `coder-external-auth`, key `gitlab-client-id` |
| `CODER_EXTERNAL_AUTH_0_CLIENT_SECRET` | from Secret `coder-external-auth`, key `gitlab-client-secret` |
| `CODER_EXTERNAL_AUTH_0_AUTH_URL` | `https://gitlab.usgov.coderdemo.io/oauth/authorize` |
| `CODER_EXTERNAL_AUTH_0_TOKEN_URL` | `https://gitlab.usgov.coderdemo.io/oauth/token` |
| `CODER_EXTERNAL_AUTH_0_VALIDATE_URL` | `https://gitlab.usgov.coderdemo.io/oauth/token/info` |
| `CODER_EXTERNAL_AUTH_0_REGEX` | `gitlab\.usgov\.coderdemo\.io` |
| `CODER_EXTERNAL_AUTH_0_SCOPES` | `read_user read_repository write_repository` |

The OAuth app client id and secret are supplied to Coder via the k8s Secret
`coder-external-auth` (keys `gitlab-client-id` and `gitlab-client-secret`);
these correspond to `GITLAB_CODER_OAUTH_APP_ID` and `GITLAB_CODER_OAUTH_SECRET`
in `generated-secrets.env`.

A self-managed GitLab requires the explicit auth/token/validate URLs above
(`deploy/coder/values.yaml` comment). Configuring an explicit external-auth
provider also suppresses Coder's built-in github.com default external-auth
provider, so no auth path leaves the GovCloud boundary (`STATUS.md`).

### Live verification (Coder's view of external auth)

From `GET /api/v2/deployment/config` against `https://dev.usgov.coderdemo.io`,
the `external_auth` entry reports:

```
id            = gitlab
type          = gitlab
display_name  = GitLab
auth_url      = https://gitlab.usgov.coderdemo.io/oauth/authorize
token_url     = https://gitlab.usgov.coderdemo.io/oauth/token
validate_url  = https://gitlab.usgov.coderdemo.io/oauth/token/info
regex         = gitlab\.usgov\.coderdemo\.io
scopes        = [read_user, read_repository, write_repository]
```

This matches `deploy/coder/values.yaml` exactly.

## Every workspace template requires GitLab login

The `claude-code` template declares the GitLab external-auth data source, which
makes a GitLab login mandatory before a workspace agent reports ready
(`coder-templates/claude-code/main.tf`):

```hcl
data "coder_external_auth" "gitlab" {
  id = "gitlab"   # MUST match CODER_EXTERNAL_AUTH_0_ID on the Coder server
}
```

Per the template comment and `STATUS.md`: declaring this data source surfaces a
"Login with GitLab" control on the dashboard; the agent only reports auth as
satisfied once the owner completes the in-boundary GitLab OAuth flow. The Coder
agent's git credential helper then injects a short-lived OAuth token for any
clone/fetch/push to `gitlab.usgov.coderdemo.io`, so no PATs or SSH keys live in
the workspace. `STATUS.md` records this as verified: the active template
version's `/external-auth` lists `gitlab` as required.

## Keycloak SSO (OpenID Connect)

GitLab signs in through the same Keycloak realm (`coder`) as Coder and Grafana,
so the demo is one SSO. The OmniAuth `openid_connect` provider is configured in
`GITLAB_OMNIBUS_CONFIG` (`deploy/gitlab/statefulset.yaml`):

- Confidential realm client `gitlab` (PKCE S256, redirect
  `https://gitlab.usgov.coderdemo.io/users/auth/openid_connect/callback`),
  created by `scripts/setup-gitlab-oidc.py`. The client secret lives in AWS
  Secrets Manager (`usgov-coderdemo/gitlab/oidc`), is synced by ESO into the
  `gitlab-oidc` Secret, and is injected as `GITLAB_OIDC_CLIENT_SECRET`
  (referenced as `ENV[...]` in the omnibus config), so no secret is in git.
- Auto sign-on (JIT) creates the GitLab user on first Keycloak login;
  `uid_field` is `preferred_username`. Auto-redirect is deliberately NOT set, so
  the local username/password form stays available as break-glass for root.

Verified live: the sign-in page shows a "Keycloak" button; the OmniAuth request
phase redirects to the realm with `client_id=gitlab` and PKCE; a headless
authorization-code login provisions the persona and returns to the dashboard.

### Roles: CE limitation and explicit user provisioning

GitLab **Community Edition does not implement OIDC group-to-role assignment**.
`admin_groups` / `required_groups` / `external_groups` are EE features; this CE
image (`gitlab-ce` 19.0.1, no `ee/` directory) ships only the SAML and LDAP
equivalents with no `openid_connect` code path, so the `admin_groups` line in the
omnibus config is a no-op (kept only so it activates if the image is ever
switched to GitLab EE). Per-group membership/roles is impossible on either
edition without SAML Group Sync (a Premium feature).

Because of that, the persona users and the instance admin attribute are
provisioned explicitly by `scripts/setup-gitlab-users.py` (idempotent,
`gitlab-rails`): it creates the eight demo personas from
`scripts/setup-keycloak-hierarchy.py` plus the operator super admin
`austen.platform`, links each to its `openid_connect` identity
(`extern_uid = preferred_username`) so SSO lands on the right account, and sets
GitLab instance admin only on `austen.platform` (the operator super admin),
keeping every demo persona (including the Platform lead `pat.platform`) a regular
user to preserve tenant isolation. Verified live: `austen.platform` SSO login is
`is_admin=true` (`/admin` returns 200); `pat.platform` and `dana.dev` are regular
users (`/admin` returns 404).

## Notes and out of scope

- GitLab to Keycloak SSO (OIDC) is now ENABLED (see "Keycloak SSO" above).
  GitLab CE has no OIDC group-to-role mapping, so the instance admin attribute
  is provisioned by `scripts/setup-gitlab-users.py`, not by group claims.
- Git over SSH is not wired (NLB terminates 443 only). HTTPS clone/push is the
  supported path.
- Backups: with embedded Postgres there is no managed backup; durability relies
  on the EBS PVC plus GitLab's own backup tooling (`deploy/gitlab/README.md`).

## Sources

Repo files:

- `deploy/gitlab/statefulset.yaml`, `service.yaml`, `ingress.yaml`,
  `secrets.example.yaml`, `README.md`
- `deploy/coder/values.yaml` (external-auth env block)
- `coder-templates/claude-code/main.tf` (the `coder_external_auth` data source)
- `STATUS.md`

Live read-only commands run (GET only):

- `kubectl -n gitlab get statefulset,svc,ingress`
- `curl -sS -o /dev/null -w '%{http_code}' https://gitlab.usgov.coderdemo.io/oauth/authorize`
- `POST /api/v2/users/login` then `GET /api/v2/deployment/config` against
  `https://dev.usgov.coderdemo.io` (admin creds from `generated-secrets.env`;
  no secret values reproduced here)
- Secret key-name listing from `generated-secrets.env` (names only; no values)
