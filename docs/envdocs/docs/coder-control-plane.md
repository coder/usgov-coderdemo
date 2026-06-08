# Coder control plane

Coder **v2.34.0** is the single governance and workspace plane, served at
`https://dev.usgov.coderdemo.io` from namespace `coder`. It is deployed with the
Coder Helm chart; the full configuration lives in `deploy/coder/values.yaml`.

Source of truth: `docs/as-built/30-coder-control-plane.md`,
`deploy/coder/values.yaml`.

## Image (ECR ghcr mirror)

```yaml
coder:
  image:
    repo: "430737322961.dkr.ecr.us-gov-west-1.amazonaws.com/ghcr/coder/coder"
    tag: "v2.34.0"
    pullPolicy: IfNotPresent
```

GovCloud has no ECR pull-through cache, so `ghcr.io/coder/coder:v2.34.0` is
mirrored into private ECR (`scripts/mirror-images.sh`).

## ServiceAccount and IRSA (Bedrock)

```yaml
serviceAccount:
  name: coder
  workspacePerms: true
  enableDeployments: true
  annotations:
    eks.amazonaws.com/role-arn: "arn:aws-us-gov:iam::430737322961:role/usgov-coderdemo-coder-bedrock"
```

The `coder` ServiceAccount is annotated for IRSA so the AI Gateway Bedrock
provider can call Bedrock with temporary credentials and no static AWS keys.
`workspacePerms` and `enableDeployments` let the in-pod provisioner manage
workspace pods.

## Networking

Coder runs as a `ClusterIP` Service behind the edge. The live front door is the
Istio ingress gateway: the `coder` VirtualService binds `*.usgov.coderdemo.io`
to `istio-system/public-gateway`. The nginx `Ingress` declared in `values.yaml`
still exists as the rollback path but is out of the public DNS path. TLS
terminates upstream at the gateway NLB (ACM cert), so the backend is plain HTTP.

```yaml
ingress:
  enable: true
  className: "nginx"
  host: "dev.usgov.coderdemo.io"
  wildcardHost: "*.usgov.coderdemo.io"
  tls:
    enable: false
  annotations:
    nginx.ingress.kubernetes.io/ssl-redirect: "false"
    nginx.ingress.kubernetes.io/proxy-read-timeout: "86400"
    nginx.ingress.kubernetes.io/proxy-send-timeout: "86400"
    nginx.ingress.kubernetes.io/proxy-body-size: "0"
```

The two 86400-second proxy timeouts and `proxy-body-size: "0"` support Coder's
long-lived websockets (web terminal, agent, logs) and large streamed payloads.

The `coder` namespace is labeled `istio-injection=enabled`, so the Coder pod
runs a native-sidecar `istio-proxy` and reports `2/2`.

## OIDC SSO to Keycloak

```yaml
env:
  - name: CODER_OIDC_ISSUER_URL
    value: "https://auth.usgov.coderdemo.io/realms/coder"
  - name: CODER_OIDC_CLIENT_ID
    value: "coder"
  - name: CODER_OIDC_CLIENT_SECRET    # from Secret coder-oidc key client-secret
  - name: CODER_OIDC_SCOPES
    value: "openid,profile,email"
  - name: CODER_OIDC_EMAIL_FIELD
    value: "email"
  - name: CODER_OIDC_USERNAME_FIELD
    value: "preferred_username"
  - name: CODER_OIDC_ALLOW_SIGNUPS
    value: "true"
  - name: CODER_OIDC_SIGN_IN_TEXT
    value: "Sign in with Keycloak"
```

The legacy `oidc.group_field` is intentionally empty; multi-organization
identity is handled by runtime per-org IdP sync, not the legacy env vars. See
[Identity (Keycloak)](identity-keycloak.md).

## Auth boundary hardening

Three settings keep all login and git egress inside the GovCloud boundary.

1. **GitHub default login disabled.**
   `CODER_OAUTH2_GITHUB_DEFAULT_PROVIDER_ENABLE=false`. Login is Keycloak SSO
   plus the local password owner only, with no github.com egress.
2. **GitLab git external auth.** `CODER_EXTERNAL_AUTH_0_*` declares an explicit
   provider for the in-cluster GitLab (id `gitlab`, type `gitlab`). Declaring it
   also suppresses Coder's built-in github.com external-auth provider. See
   [GitLab SCM](gitlab.md).
3. **Path-based workspace apps disabled.** `CODER_DISABLE_PATH_APPS=true`. Every
   template serves apps from its own `*.usgov.coderdemo.io` subdomain.

## Licensing and entitlements

`GET /api/v2/entitlements` reports `has_license=true` with no warnings.
Entitled and enabled features include `aibridge`, `ai_governance_user_limit`,
`appearance`, `audit_log`, `connection_log`, `high_availability`,
`multiple_external_auth`, `multiple_organizations`, `template_rbac`, and
`workspace_prebuilds`. This confirms both the AI Governance add-on and the
broader premium entitlement.

## Classification banner

A green `UNCLASSIFIED - USGOVCLOUD` banner (`#007a33`) is enabled. It is a
runtime database setting (premium-gated), reproduced idempotently by
`scripts/set-appearance.sh`, not part of Helm.

## Secrets consumed (names and keys only)

| Secret | Keys | Used by |
|---|---|---|
| `coder-db` | `url` | `CODER_PG_CONNECTION_URL` |
| `coder-oidc` | `client-secret` | `CODER_OIDC_CLIENT_SECRET` |
| `coder-ai` | `ANTHROPIC_API_KEY` | `CODER_AI_GATEWAY_PROVIDER_0_KEY` (seed only) |
| `coder-external-auth` | `gitlab-client-id`, `gitlab-client-secret` | `CODER_EXTERNAL_AUTH_0_CLIENT_ID/SECRET` |

All real values come from AWS Secrets Manager via the External Secrets Operator.
See [Secrets](secrets.md).
