# Identity (Keycloak)

Keycloak `26.6.3` runs in namespace `keycloak` and serves SSO for the whole
stack from realm `coder` at `https://auth.usgov.coderdemo.io`. Coder, GitLab,
Grafana, Kiali, and this documentation site all authenticate against the same
realm, so the demo is one SSO.

Source of truth: `docs/as-built/40-identity-keycloak.md`,
`docs/as-built/45-idp-sync-personas.md`, `deploy/keycloak/`.

## Deployment

| Aspect | Value |
|---|---|
| Image | ECR mirror of `quay.io/keycloak/keycloak:26.6.3` |
| Replicas | 1, `strategy.type: Recreate`, `KC_CACHE=local` (HA out of scope) |
| Start | `start --import-realm` (stock image; build runs on first boot) |
| Database | RDS PostgreSQL, logical db `keycloak`, `KC_DB=postgres` |
| Hostname / proxy | `KC_HOSTNAME=https://auth.usgov.coderdemo.io`, `KC_PROXY_HEADERS=xforwarded`, `KC_HTTP_ENABLED=true` |

The live edge is the Istio ingress gateway; the `keycloak` VirtualService forces
`x-forwarded-proto: https` so Keycloak issues `Secure; SameSite=None` session
cookies (required by the Account Console silent-SSO iframe). The nginx Ingress is
the retained rollback path.

## Realm `coder` and the `coder` OIDC client

The realm is imported from `deploy/keycloak/realm-coder.json` (idempotent: an
existing realm is skipped). The committed client `coder` is confidential
(`publicClient: false`, `clientAuthenticatorType: client-secret`), standard flow
only, with redirect URIs `https://dev.usgov.coderdemo.io/api/v2/users/oidc/callback`
and `https://dev.usgov.coderdemo.io/*`.

!!! note "Other realm clients"
    Beyond `coder`, the realm carries confidential clients for `grafana`,
    `gitlab`, `kiali`, and `envdocs` (this site). Each is created by an
    idempotent setup script that also publishes its client secret to AWS Secrets
    Manager for ESO to sync, mirroring `scripts/setup-grafana-oidc.py`.

## IdP sync: organizations, groups, roles

Coder consumes a single full-path `groups` OIDC claim (a Group Membership mapper
on the `coder` client emits it in the ID, access, and userinfo tokens) and runs
three sync passes on every login.

```text
/platform                  org-sync   -> coder (Platform Engineering)
/platform/platform-admins  group-sync -> group "platform-admins"
/platform/sre              group-sync -> group "sre"
/platform/org-admins       role-sync  -> organization-admin
/platform/template-admins  role-sync  -> organization-template-admin
/alpha                     org-sync   -> alpha
/alpha/developers          group-sync -> group "developers"
/alpha/org-admins          role-sync  -> organization-admin
/alpha/auditors            role-sync  -> organization-auditor
/bravo                     org-sync   -> bravo
/bravo/developers          group-sync -> group "developers"
/bravo/org-admins          role-sync  -> organization-admin
/bravo/auditors            role-sync  -> organization-auditor
```

- **Organization sync** (deployment level): `field=groups`,
  `organization_assign_default=false`, mapping `/platform`, `/alpha`, `/bravo`.
- **Group sync** (per org): `field=groups`, `auto_create_missing_groups=false`.
- **Role sync** (per org): maps role subgroups to `organization-admin`,
  `organization-template-admin`, and `organization-auditor`.

Built by two idempotent scripts: `scripts/setup-keycloak-hierarchy.py` (groups,
mapper, persona users) and `scripts/setup-coder-idp-sync.py` (Coder orgs,
groups, sync settings). Verify with `scripts/verify-oidc-login.py`.

## Organizations (tenants)

| Coder org | Display name | Role in the demo |
|---|---|---|
| `coder` (default) | Platform Engineering | Central platform team; owns built-in provisioners |
| `alpha` | Mission Partner Alpha | Tenant; own provisioner + `claude-code` template |
| `bravo` | Mission Partner Bravo | Tenant; own provisioner + `claude-code` template |

Tenant isolation is enforced by Coder organization membership, RBAC, and per-org
provisioner keys.

## Personas

All persona users share the password in `DEMO_USER_PASSWORD` and have email
`<username>@usgov.coderdemo.io`.

| Username | Org | Org role | Groups |
|---|---|---|---|
| pat.platform | Platform Engineering | organization-admin | platform-admins |
| sky.sre | Platform Engineering | organization-template-admin | sre |
| alex.admin | Mission Partner Alpha | organization-admin | (none) |
| dana.dev | Mission Partner Alpha | member | developers |
| quinn.data | Mission Partner Alpha | member | data-science |
| morgan.isso | Alpha + Bravo | organization-auditor (both) | (none) |
| riley.admin | Mission Partner Bravo | organization-admin | (none) |
| jordan.dev | Mission Partner Bravo | member | developers |

## Operator super admin

`austen.platform` is the dedicated operator account (its own password in
`SUPERADMIN_PASSWORD`, not a demo persona). It belongs to the `/platform`,
`/alpha`, and `/bravo` groups (org-admin in each) and is additionally Coder
**site Owner**, **GitLab instance admin**, and **Grafana org Admin**. One
Keycloak login administers the entire stack. On first sign in it is forced to
enroll a WebAuthn passkey and TOTP.

`pat.platform` is a normal Platform lead (Platform org-admin only, not a site
Owner and not a GitLab admin).
