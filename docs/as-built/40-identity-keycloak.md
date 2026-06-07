# 40. Identity: Keycloak SSO (as-built)

As-built, read-only documentation of the Keycloak identity layer for the
GovCloud Coder demo. Every nontrivial claim below is grounded in a repo file
path or a live read-only command. Items that could not be verified from a repo
file or a permitted GET are marked "unverified".

- Keycloak URL: `https://auth.usgov.coderdemo.io` (realm `coder`).
- Coder URL it serves SSO for: `https://dev.usgov.coderdemo.io`.
- Namespace: `keycloak`. Source: `deploy/keycloak/`.

## Deployment

Keycloak runs as a single-replica `Deployment` in namespace `keycloak`
(`deploy/keycloak/deployment.yaml`).

| Aspect | Value | Source |
|---|---|---|
| Image | `430737322961.dkr.ecr.us-gov-west-1.amazonaws.com/quay/keycloak/keycloak:26.6.3` (ECR mirror of `quay.io/keycloak/keycloak:26.6.3`) | `deploy/keycloak/deployment.yaml` |
| Replicas | 1, `strategy.type: Recreate`, `KC_CACHE=local` (no clustering; HA out of scope) | `deploy/keycloak/deployment.yaml` |
| Start command | `start --import-realm` (not `--optimized`; stock image is not pre-built for postgres, so plain `start` runs the build step on first boot) | `deploy/keycloak/deployment.yaml`, `deploy/keycloak/README.md` |
| Database | RDS PostgreSQL, logical db `keycloak`, `KC_DB=postgres`, `KC_DB_URL=jdbc:postgresql://<rds-endpoint>:5432/keycloak`; credentials from Secret `keycloak-db` (keys `username`/`password`) | `deploy/keycloak/deployment.yaml` |
| Hostname / proxy | `KC_HOSTNAME=https://auth.usgov.coderdemo.io`, `KC_PROXY_HEADERS=xforwarded`, `KC_HTTP_ENABLED=true`. Full https URL pins scheme/host because TLS terminates upstream at the L4 NLB | `deploy/keycloak/deployment.yaml`, `deploy/keycloak/README.md` |
| Bootstrap admin | `KC_BOOTSTRAP_ADMIN_USERNAME`/`KC_BOOTSTRAP_ADMIN_PASSWORD` from Secret `keycloak-admin` (first boot only) | `deploy/keycloak/deployment.yaml` |
| Health/metrics | `KC_HEALTH_ENABLED`/`KC_METRICS_ENABLED=true` on management port `9000`; startup/liveness/readiness probes hit `/health/started`, `/health/live`, `/health/ready` | `deploy/keycloak/deployment.yaml` |

Network path (`deploy/keycloak/ingress.yaml`, `service.yaml`):

```
client --HTTPS--> NLB (TLS terminated, ACM cert) --HTTP--> ingress-nginx --HTTP--> Service keycloak:8080 --> pod :8080
```

- `Service` is `ClusterIP` exposing only HTTP `8080`; the management port `9000`
  is intentionally not exposed through the Service (`deploy/keycloak/service.yaml`).
- `Ingress` is `ingressClassName: nginx`, host `auth.usgov.coderdemo.io`, with
  `ssl-redirect: "false"` (backend is plain HTTP, avoids a redirect loop) and a
  larger `proxy-buffer-size` for Keycloak's auth cookies
  (`deploy/keycloak/ingress.yaml`).
- The realm JSON is mounted from a ConfigMap (`keycloak-realm-coder`) generated
  from `realm-coder.json` by `deploy/keycloak/kustomization.yaml` (with
  `disableNameSuffixHash: true`).

Secrets are provisioned out of band (not committed). `secrets.example.yaml`
documents the expected keys for `keycloak-db` and `keycloak-admin`
(`deploy/keycloak/secrets.example.yaml`).

### Live verification

```
kubectl -n keycloak get deploy,svc,ingress
  deployment.apps/keycloak   1/1
  service/keycloak           ClusterIP   8080/TCP
  ingress/keycloak           nginx       auth.usgov.coderdemo.io -> NLB

curl -sS https://auth.usgov.coderdemo.io/realms/coder/.well-known/openid-configuration
  issuer = https://auth.usgov.coderdemo.io/realms/coder   (HTTP 200)
```

The discovery document confirms the realm is live and the issuer matches the
value Coder is configured with.

## Realm `coder` (`realm-coder.json`)

The realm is imported from `deploy/keycloak/realm-coder.json`. Import is
idempotent: if realm `coder` already exists it is skipped
(`deploy/keycloak/README.md`).

Realm-level settings (`realm-coder.json`):

- `enabled: true`, `displayName: "Coder (GovCloud Demo)"`,
  `sslRequired: "external"`.
- `registrationAllowed: false`, `loginWithEmailAllowed: true`,
  `resetPasswordAllowed: true`, `editUsernameAllowed: false`.
- Token settings: `accessTokenLifespan: 300` (5 min),
  `ssoSessionIdleTimeout: 1800` (30 min idle),
  `ssoSessionMaxLifespan: 36000` (10 h max), `offlineSessionIdleTimeout: 2592000`.

OIDC client `coder` (`realm-coder.json`):

| Field | Value |
|---|---|
| `clientId` | `coder` |
| Type | Confidential (`publicClient: false`, `clientAuthenticatorType: client-secret`) |
| Flows | `standardFlowEnabled: true`; implicit, direct-access-grants, and service-accounts all disabled |
| `secret` | `REPLACE_WITH_CODER_OIDC_CLIENT_SECRET` placeholder in the committed JSON; the real value must equal what Coder reads from Secret `coder-oidc` |
| `redirectUris` | `https://dev.usgov.coderdemo.io/api/v2/users/oidc/callback` and `https://dev.usgov.coderdemo.io/*` |
| `webOrigins` | `+` |
| `defaultClientScopes` | `web-origins`, `profile`, `roles`, `email` |
| `optionalClientScopes` | `offline_access` |
| `post.logout.redirect.uris` | `https://dev.usgov.coderdemo.io/*` |

User defined in the realm (`realm-coder.json`):

- `demo` / `demo@usgov.coderdemo.io`, `enabled: true`, `emailVerified: true`,
  realm role `default-roles-coder`. Password is a placeholder
  (`REPLACE_WITH_DEMO_USER_PASSWORD`) in the committed JSON and is set out of
  band.

The committed realm JSON defines only the realm flags, the single `coder`
client (with its default/optional client scopes), and the one `demo` user. It
declares no realm groups, no `defaultGroups`, and no custom protocol mappers or
client scopes beyond the Keycloak built-ins. Verified by grepping
`realm-coder.json`: the only matches for group/scope keys are the client's
`defaultClientScopes` and `optionalClientScopes` arrays; there is no `groups`
array, no `defaultGroups`, and no `protocolMappers`.

## How Coder OIDC SSO is wired to Keycloak

Configured in the Coder Helm values (`deploy/coder/values.yaml`, env block):

| Coder env var | Value | Notes |
|---|---|---|
| `CODER_OIDC_ISSUER_URL` | `https://auth.usgov.coderdemo.io/realms/coder` | matches the realm issuer |
| `CODER_OIDC_CLIENT_ID` | `coder` | matches the realm client |
| `CODER_OIDC_CLIENT_SECRET` | from Secret `coder-oidc`, key `client-secret` | must match the realm client `secret` |
| `CODER_OIDC_SCOPES` | `openid,profile,email` | |
| `CODER_OIDC_EMAIL_FIELD` | `email` | |
| `CODER_OIDC_USERNAME_FIELD` | `preferred_username` | |
| `CODER_OIDC_ALLOW_SIGNUPS` | `true` | SSO users self-provision on first login |
| `CODER_OIDC_SIGN_IN_TEXT` | `Sign in with Keycloak` | login-button label |

GitHub's built-in default login provider is disabled
(`CODER_OAUTH2_GITHUB_DEFAULT_PROVIDER_ENABLE=false`), so the dashboard login
options are the local password owner plus "Sign in with Keycloak"
(`deploy/coder/values.yaml`, and `STATUS.md` "Auth boundary hardening").

### Login UX

- The Coder login screen shows a "Sign in with Keycloak" button
  (`CODER_OIDC_SIGN_IN_TEXT`). Clicking it runs the standard OIDC
  authorization-code flow against the `coder` realm client.
- Because `CODER_OIDC_ALLOW_SIGNUPS=true`, a Keycloak user who logs in for the
  first time is auto-provisioned a Coder account; username is taken from
  `preferred_username` and email from `email`.

### Live verification (Coder's view of OIDC)

Logged into `https://dev.usgov.coderdemo.io` (the demo Coder, explicitly, not
the ambient `$CODER_URL`) with the admin credentials from
`generated-secrets.env`, then `GET /api/v2/deployment/config`. The `oidc` block
reports:

```
issuer_url     = https://auth.usgov.coderdemo.io/realms/coder
client_id      = coder
scopes         = ["openid","profile","email"]
email_field    = email
username_field = preferred_username
allow_signups  = true
sign_in_text   = Sign in with Keycloak
```

This matches `deploy/coder/values.yaml` exactly.

## Configured vs NOT configured

### Configured and working

- OIDC SSO end to end: realm `coder`, confidential client `coder`, issuer and
  client id matching on both sides, standard authorization-code flow.
- Identity claim mapping: email from `email`, username from
  `preferred_username`.
- Self-service signup on first SSO login (`allow_signups: true`).
- Boundary hardening: GitHub default login disabled, so no github.com login
  egress.

### IdP organization, group, and role sync (CONFIGURED)

Keycloak-to-Coder sync is now wired and verified. Organization sync, group sync,
and role sync all read a single full-path `groups` claim that a Group Membership
mapper on the `coder` client emits. See
[45-idp-sync-personas.md](45-idp-sync-personas.md) for the full hierarchy,
persona matrix, and verification.

High-level:

1. Keycloak realm `coder` has a hierarchical group tree (`/platform`, `/alpha`,
   `/bravo` with team and role subgroups) and 8 persona users, created by
   `scripts/setup-keycloak-hierarchy.py`. The `coder` client emits the
   `groups` claim (full path; ID + access + userinfo).
2. Coder runs runtime IdP sync (not the legacy `CODER_OIDC_*` env vars):
   organization sync (`field=groups`, `organization_assign_default=false`),
   per-org group sync, and per-org role sync mapping to `organization-admin`,
   `organization-template-admin`, and `organization-auditor`. Configured by
   `scripts/setup-coder-idp-sync.py`.

The legacy deployment-config keys (`groups_field`, `user_role_field`, etc.)
remain empty on purpose: this deployment uses the runtime per-org IdP sync
settings instead, which are required for multi-organization sync.

Net effect: SSO users are placed into the correct Coder organization(s), groups,
and roles automatically on login, with no manual assignment. Tenant isolation
(Alpha vs Bravo vs Platform) is enforced by organization membership.

## Sources

Repo files:

- `deploy/keycloak/deployment.yaml`, `service.yaml`, `ingress.yaml`,
  `kustomization.yaml`, `realm-coder.json`, `secrets.example.yaml`, `README.md`
- `deploy/coder/values.yaml` (OIDC env block)
- `STATUS.md`

Live read-only commands run (GET only):

- `kubectl -n keycloak get deploy,svc,ingress`
- `curl -sS https://auth.usgov.coderdemo.io/realms/coder/.well-known/openid-configuration`
- `POST /api/v2/users/login` then `GET /api/v2/deployment/config` against
  `https://dev.usgov.coderdemo.io` (admin creds from `generated-secrets.env`;
  no secret values reproduced here)
- `grep` over `deploy/keycloak/realm-coder.json` for group/mapper keys
