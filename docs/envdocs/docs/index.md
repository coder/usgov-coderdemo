# usgov-coderdemo environment

A self-contained, in-boundary developer platform where every authentication,
source-control, and AI path stays inside AWS GovCloud. This site is the
human-readable companion to the engineering as-built docs that live in the
`usgov-coderdemo` repository under `docs/as-built/`.

!!! info "Audience and access"
    This site is published at `https://envdocs.usgov.coderdemo.io` and gated by
    Keycloak SSO: any authenticated user in the realm `coder` can read it, with
    no group restriction. See [Access and auth gate](access-and-auth.md) for how
    the gate works.

## What the demo proves

1. **Coder control plane** on EKS as the single governance and workspace plane.
2. **Keycloak SSO** (realm `coder`) as the identity provider via OIDC, so users
   sign in with "Sign in with Keycloak" instead of any external IdP.
3. **In-boundary GitLab** as the source-control manager, wired as a Coder git
   external-auth provider so workspace git operations use short-lived
   in-boundary OAuth tokens.
4. **Coder AI Gateway (AI Bridge)** as the governed egress for model traffic,
   fronting two providers: `anthropic` (direct to `api.anthropic.com` over the
   NAT gateway) and `anthropic-bedrock` (Amazon Bedrock in-region via IRSA, with
   no static keys).
5. **Coder Agents running Claude Code** in workspace pods, talking only to the
   AI Gateway with the owner's session token, never holding a raw model key.

The hardening posture removes external egress paths: Coder's built-in GitHub
login is disabled, path-based workspace apps are disabled, and the only model
egress is the governed AI Gateway path.

## Environment facts

| Property | Value |
|---|---|
| Region / account | `us-gov-west-1`, account `<AWS_ACCOUNT_ID>`, partition `aws-us-gov` |
| Domain | `usgov.coderdemo.io` (Route53 zone `Z06701704WFETYIRU5C8`) |
| Coder | `v2.34.0`, licensed with the AI Governance add-on plus premium |
| Keycloak | `26.6.3`, realm `coder` |
| GitLab | CE `19.0.1-ce.0`, embedded Postgres |
| EKS | cluster `usgov-coderdemo`, Kubernetes `1.36`, 3x `m5.xlarge` node group `mng` |
| Database | RDS PostgreSQL `18.4` (databases `coder` and `keycloak`), `rds.force_ssl=1` |
| Registry | ECR `<AWS_ACCOUNT_ID>.dkr.ecr.us-gov-west-1.amazonaws.com` (mirrored images; no pull-through in GovCloud) |

## Live URLs

| Service | URL | Auth |
|---|---|---|
| Coder | `https://dev.usgov.coderdemo.io` | Keycloak SSO only |
| Keycloak | `https://auth.usgov.coderdemo.io` | Realm `coder`; admin console at `/admin` |
| GitLab | `https://gitlab.usgov.coderdemo.io` | root password or Keycloak SSO |
| Grafana | `https://grafana.usgov.coderdemo.io` | Keycloak SSO (group maps to org role) |
| Kiali | `https://kiali.usgov.coderdemo.io` | Keycloak SSO (view-only mesh console) |
| This site | `https://envdocs.usgov.coderdemo.io` | Keycloak SSO (any realm user) |

!!! note "Source of truth"
    Content here is curated from the repository: `STATUS.md`, `docs/as-built/*`,
    `deploy/**`, and `scripts/**`. When infrastructure, configuration, or scripts
    change, the matching page here must change in the same commit. See the
    repository `CLAUDE.md` and `docs/DOCS-POLICY.md`.
