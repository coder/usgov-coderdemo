# As-built: IdP sync, organizations, and demo personas

Keycloak (`realm coder`) is the identity source. Coder consumes a single
full-path `groups` OIDC claim and runs three IdP sync passes on every login:
**organization sync**, **group sync**, and **role sync**. This gives true
multi-tenancy (isolated Coder organizations) plus realistic personas, all
modeled in Keycloak and synced automatically. No org/group/role is assigned by
hand in Coder.

Built by two idempotent scripts:

- `scripts/setup-keycloak-hierarchy.py` - groups, the group-membership claim
  mapper on the `coder` client, and the persona users (Keycloak Admin REST API).
- `scripts/setup-coder-idp-sync.py` - Coder organizations, groups, and the
  org/group/role sync settings (Coder API).

Verify end to end with `scripts/verify-oidc-login.py <user> ...` (drives a real
OIDC login and prints the resulting orgs/roles/groups).

## Organizations (tenants)

| Coder org (slug) | Display name | Role in the demo |
|---|---|---|
| `coder` (default) | Platform Engineering | Central platform team. Owns the built-in provisioners. |
| `alpha` | Mission Partner Alpha | Tenant. Own provisioner (`alpha-eks`) + `claude-code` template. |
| `bravo` | Mission Partner Bravo | Tenant. Own provisioner (`bravo-eks`) + `claude-code` template. |

Tenant isolation boundary is Coder organization membership, RBAC, and
per-org provisioner keys. Workspaces for all orgs currently share the
`coder-workspaces` namespace and the `coder` ServiceAccount, so this is org/RBAC
isolation, not Kubernetes-namespace isolation (see
[30-coder-control-plane.md](30-coder-control-plane.md) and
[20-platform-kubernetes.md](20-platform-kubernetes.md)).

## Keycloak group tree and the `groups` claim

One Group Membership mapper on the `coder` client emits the full group path as a
JSON array claim named `groups`, in the ID token, access token, and userinfo.
Users are explicitly added to the org group, their team subgroup, and any role
subgroup (Keycloak does not imply parent membership).

```
/platform                  org-sync  -> coder (Platform Engineering)
/platform/platform-admins  group-sync -> group "platform-admins"
/platform/sre              group-sync -> group "sre"
/platform/org-admins       role-sync -> organization-admin
/platform/template-admins  role-sync -> organization-template-admin
/alpha                     org-sync  -> alpha
/alpha/developers          group-sync -> group "developers"
/alpha/data-science        group-sync -> group "data-science"
/alpha/security            group-sync -> group "security"
/alpha/org-admins          role-sync -> organization-admin
/alpha/auditors            role-sync -> organization-auditor
/bravo                     org-sync  -> bravo
/bravo/developers          group-sync -> group "developers"
/bravo/org-admins          role-sync -> organization-admin
/bravo/auditors            role-sync -> organization-auditor
```

Example decoded ID token claim (persona `morgan.isso`):
`"groups": ["/alpha", "/alpha/auditors", "/bravo", "/bravo/auditors"]`.

## Coder sync configuration

- **Organization sync** (deployment-level, `/api/v2/settings/idpsync/organization`):
  `field=groups`, `organization_assign_default=false` (membership is purely
  claim-driven), mapping `/platform`,`/alpha`,`/bravo` to the org IDs.
- **Group sync** (per org, `.../settings/idpsync/groups`): `field=groups`,
  `auto_create_missing_groups=false`. Groups are pre-created.
- **Role sync** (per org, `.../settings/idpsync/roles`): `field=groups`, mapping
  role subgroups to the exact role IDs `organization-admin`,
  `organization-template-admin`, `organization-auditor`.

The local `admin` owner is a non-OIDC break-glass account and is unaffected by
`assign_default=false`. The legacy Keycloak `demo` user is in no mapped group,
so with `assign_default=false` it lands in no organization by design.

## Personas (Keycloak realm `coder`)

All persona users have `emailVerified=true` and share the password in
`DEMO_USER_PASSWORD` (`~/.config/usgov-coderdemo/generated-secrets.env`).
Email is `<username>@usgov.coderdemo.io`.

| Username | Name | Org | Org role | Groups |
|---|---|---|---|---|
| pat.platform | Pat Rivera | Platform Engineering | organization-admin | platform-admins |
| sky.sre | Sky Nguyen | Platform Engineering | organization-template-admin | sre |
| alex.admin | Alex Carter | Mission Partner Alpha | organization-admin | (none) |
| dana.dev | Dana Brooks | Mission Partner Alpha | member | developers |
| quinn.data | Quinn Lee | Mission Partner Alpha | member | data-science |
| morgan.isso | Morgan Diaz | Alpha + Bravo | organization-auditor (both) | (none) |
| riley.admin | Riley Fox | Mission Partner Bravo | organization-admin | (none) |
| jordan.dev | Jordan Kim | Mission Partner Bravo | member | developers |

## Operator super admin (not a demo persona)

`austen.platform` (Austen Platform) is the dedicated operator account, separate
from the eight demo personas and with its own password in `SUPERADMIN_PASSWORD`.
It belongs to the `/platform`, `/alpha`, and `/bravo` Keycloak groups (org-admin
in each) and is additionally granted the Coder **site Owner** role
(`scripts/grant-coder-owner.py`), **GitLab instance admin**
(`scripts/setup-gitlab-users.py`), and **Grafana org Admin** (via the `/platform`
group rule). One Keycloak login therefore administers the entire stack: every
Coder org, GitLab, and Grafana.

On its first Keycloak sign in `austen.platform` is forced to enroll a WebAuthn
passkey and TOTP: it carries the `webauthn-register` and `CONFIGURE_TOTP`
required actions (set by `scripts/setup-keycloak-hierarchy.py`, only while the
matching credential is missing, so reconciles never re-force enrollment). The
stock browser flow challenges TOTP on subsequent logins. Because of this, the
headless `verify-oidc-login.py` probe does not apply to `austen.platform` once
the required actions are set, until enrollment is completed interactively.

## Verified login matrix

Run `scripts/verify-oidc-login.py` (fresh cookie jar per user, real Keycloak
login). Confirmed output:

```
austen.platform -> coder  organization-admin           groups=[platform-admins]   site_roles=[owner]
                -> alpha  organization-admin           groups=[]
                -> bravo  organization-admin           groups=[]
pat.platform  -> coder  organization-admin           groups=[platform-admins]
sky.sre       -> coder  organization-template-admin  groups=[sre]
alex.admin    -> alpha  organization-admin           groups=[]
dana.dev      -> alpha  member                       groups=[developers]
quinn.data    -> alpha  member                       groups=[data-science]
morgan.isso   -> alpha  organization-auditor         groups=[]
              -> bravo  organization-auditor         groups=[]
riley.admin   -> bravo  organization-admin           groups=[]
jordan.dev    -> bravo  member                       groups=[developers]
```

Tenant isolation holds for the mission-partner personas: Alpha users see only
Alpha, Bravo users see only Bravo, and the ISSO/auditor spans both tenants
read-only. The operator account `austen.platform` is the deliberate exception:
it is super admin (site Owner + org-admin in all three orgs + GitLab
Administrator + Grafana Admin), so a single Keycloak login administers the whole
stack. `pat.platform` is a normal Platform lead (Platform org-admin only).

### Verified live (this review)

Read-only checks confirmed the sync backbone the matrix depends on:

- `GET /api/v2/organizations` returns exactly `coder` (Platform Engineering),
  `alpha` (Mission Partner Alpha), and `bravo` (Mission Partner Bravo).
- `GET /api/v2/settings/idpsync/organization` reports `field=groups`,
  `organization_assign_default=false`, and the mapping keys `/platform`,
  `/alpha`, `/bravo`.
- The two tenant provisioner Deployments `coder-provisioner-alpha` and
  `coder-provisioner-bravo` are `1/1`
  (`kubectl -n coder get deploy -l app.kubernetes.io/name=coder-provisioner`).
- The deployment-config `oidc.group_field` is empty, confirming the legacy OIDC
  group sync is off and the runtime per-org IdP sync is authoritative.

The persona login matrix above is produced by `scripts/verify-oidc-login.py`.
The group tree, persona memberships, and per-org group/role mappings match
`scripts/setup-keycloak-hierarchy.py` and `scripts/setup-coder-idp-sync.py` line
for line.

## Provisioners and templates per tenant org

Each tenant org has its own external provisioner daemon
(`deploy/coder/provisioners.yaml`, Deployments `coder-provisioner-alpha` /
`coder-provisioner-bravo`) authenticated with an org-scoped provisioner key
(Secret `coder-provisioner-<org>`), reusing the `coder` ServiceAccount. The
`claude-code` template is pushed into all three orgs; its import (terraform
init/plan) ran on each org's daemon.

Workspace builds in any org require the user to complete the in-boundary GitLab
external auth first (every template declares `data coder_external_auth
"gitlab"`, see [70-workspace-templates.md](70-workspace-templates.md)).

## Demo flow

1. Log in as `austen.platform`: the operator super admin. Lands in all three
   orgs as org admin (and is site Owner); switch orgs from the org picker.
2. Log in (incognito) as `dana.dev`: lands only in Mission Partner Alpha, group
   developers, no admin. Cannot see Bravo or Platform.
3. Log in as `riley.admin`: Bravo org admin; manage Bravo members/templates.
4. Log in as `morgan.isso`: auditor in both Alpha and Bravo; read-only audit
   access, no build/admin rights.

After changing Keycloak group membership, sync applies on the user's next login;
use a fresh/incognito session to avoid a cached session.

## Re-run / reset

```
. ~/.config/usgov-coderdemo/generated-secrets.env
export KEYCLOAK_ADMIN_USERNAME KEYCLOAK_ADMIN_PASSWORD DEMO_USER_PASSWORD
python3 scripts/setup-keycloak-hierarchy.py     # Keycloak groups/mapper/users
python3 scripts/setup-coder-idp-sync.py         # Coder orgs/groups/sync
export DEMO_USER_PASSWORD
python3 scripts/verify-oidc-login.py pat.platform dana.dev morgan.isso riley.admin
```

Both setup scripts are idempotent.

The operator super admin `austen.platform` also needs its cross-app admin grants
(idempotent; credentials are read from `generated-secrets.env`):

```
python3 scripts/grant-coder-owner.py austen.platform   # Coder site Owner
python3 scripts/setup-gitlab-users.py                  # GitLab instance admin
# Grafana org Admin is automatic via the /platform group rule
```
