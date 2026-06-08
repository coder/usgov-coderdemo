# 30. Coder control plane (as-built)

Coder **v2.34.0** control plane for the GovCloud demo, served at
`https://dev.usgov.coderdemo.io`. This document walks `deploy/coder/values.yaml`
section by section and records what was verified against the live deployment.

Scope of `values.yaml`: the Coder control plane only (Deployment,
ServiceAccount, Service, Ingress, and `env`). The platform layer owns
ingress-nginx, the NLB plus ACM cert, the `coder` namespace, and the k8s
Secrets referenced below. Source: `deploy/coder/values.yaml:1-16`,
`deploy/coder/README.md:15-27`.

## Verification method

Read-only. Logged in to the demo Coder with the admin credentials
(`POST /api/v2/users/login`) to obtain a session token, then issued `GET`
requests with the `Coder-Session-Token` header. Cluster facts came from
`kubectl get` and `helm list` against `./kubeconfig`. AWS facts came from
read-only `aws iam get-role` / `get-role-policy`. No mutating call was made.
Always target `https://dev.usgov.coderdemo.io` explicitly; the ambient
`$CODER_URL` points at a different host Coder and was not used.

| Check | Source / command | Result |
|---|---|---|
| Server version | `GET /api/v2/buildinfo` | `v2.34.0+3006da5` |
| Helm release | `helm -n coder list` | `coder-2.34.0`, app `2.34.0`, revision **4**, `deployed` |
| Deployment image | `kubectl -n coder get deploy coder -o jsonpath` | `.../ghcr/coder/coder:v2.34.0` |
| Replicas | same | `1` |
| Service type | `kubectl -n coder get svc coder` | `ClusterIP` |
| Ingress | `kubectl -n coder get ingress` | class `nginx`, hosts `dev.` + `*.usgov.coderdemo.io` |
| Live edge | `kubectl get virtualservice -n coder` / `get gateway -n istio-system` | `coder` VirtualService on `istio-system/public-gateway`, host `*.usgov.coderdemo.io` |

## Image (ECR ghcr mirror)

```yaml
coder:
  image:
    repo: "430737322961.dkr.ecr.us-gov-west-1.amazonaws.com/ghcr/coder/coder"
    tag: "v2.34.0"
    pullPolicy: IfNotPresent
```

The upstream `ghcr.io/coder/coder:v2.34.0` is mirrored into private ECR because
GovCloud has no pull-through cache. The mirror path follows the convention
`ghcr.io/<repo>:<tag>` to `<registry>/ghcr/<repo>:<tag>`
(`deploy/CONVENTIONS.md:47-57`). The chart version is pinned to `2.34.0`
(`deploy/coder/README.md:48-53`, `deploy/CONVENTIONS.md:39-45`). Source:
`deploy/coder/values.yaml:18-26`. Verified live: the running Deployment uses
`430737322961.dkr.ecr.us-gov-west-1.amazonaws.com/ghcr/coder/coder:v2.34.0`.

## ServiceAccount and IRSA (Bedrock)

```yaml
serviceAccount:
  name: coder
  workspacePerms: true
  enableDeployments: true
  annotations:
    eks.amazonaws.com/role-arn: "arn:aws-us-gov:iam::430737322961:role/usgov-coderdemo-coder-bedrock"
```

The chart always creates a ServiceAccount named `coder`. It is annotated for
IRSA so the AI Gateway Bedrock provider can call Bedrock with temporary
credentials and no static AWS keys. `workspacePerms: true` and
`enableDeployments: true` let the in-pod provisioner manage workspace pods and
Deployments. Source: `deploy/coder/values.yaml:28-37`.

Verified live: the SA `coder/coder` carries the annotation
`eks.amazonaws.com/role-arn = arn:aws-us-gov:iam::430737322961:role/usgov-coderdemo-coder-bedrock`
(`kubectl -n coder get sa coder -o jsonpath`). The IRSA chain itself is
documented in `60-ai-gateway.md`.

## Service (ClusterIP behind nginx)

```yaml
service:
  enable: true
  type: ClusterIP
envUseClusterAccessURL: false
```

Coder sits behind ingress-nginx, so its Service must not provision a second
load balancer. The chart default is `LoadBalancer`; it is overridden to
`ClusterIP`. `envUseClusterAccessURL: false` stops the chart from injecting a
cluster-internal access URL because `CODER_ACCESS_URL` is set explicitly below.
Source: `deploy/coder/values.yaml:39-47`. Verified live: Service type is
`ClusterIP`.

## Ingress (host, wildcard, TLS off, websocket annotations)

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

One internet-facing NLB routes to ingress-nginx, which routes to this Ingress.
TLS terminates upstream at the NLB via the ACM cert, so `tls.enable=false` and
the backend is plain HTTP. `ssl-redirect: "false"` avoids a redirect loop
because nginx talks plain HTTP to Coder. The two 86400-second proxy timeouts
and `proxy-body-size: "0"` support Coder's long-lived websockets (web terminal,
agent, logs) and large streamed payloads. Source:
`deploy/coder/values.yaml:49-67`; ingress contract in
`deploy/CONVENTIONS.md:25-33`.

Verified live: the `coder` Ingress has `ingressClassName: nginx`, rules for
`dev.usgov.coderdemo.io` and `*.usgov.coderdemo.io`, and exactly the four nginx
annotations above (`kubectl -n coder get ingress`).

### Live edge: Istio gateway (nginx Ingress is the rollback path)

Public DNS now resolves Coder through the Istio ingress gateway, not
ingress-nginx. The `coder` VirtualService (ns `coder`) binds host
`*.usgov.coderdemo.io` to gateway `istio-system/public-gateway` and routes to
`coder.coder.svc.cluster.local:80`, forcing `x-forwarded-proto: https` for
parity with the other hosts (`deploy/istio/gateway/virtualservice-coder.yaml`).
The single wildcard already matches `dev.usgov.coderdemo.io`, so only the
wildcard is listed (Istio rejects an overlapping exact host). TLS terminates
upstream at the gateway NLB (ACM cert); the gateway forwards plain HTTP, so the
ClusterIP Service and the env settings above are unchanged. The nginx `Ingress`
declared in `values.yaml` still exists and is the rollback path, out of the live
DNS path. See [25-istio-service-mesh.md](25-istio-service-mesh.md) and
[40-identity-keycloak.md](40-identity-keycloak.md).

Mesh note: the `coder` namespace is labeled `istio-injection=enabled` and Coder
IS enrolled in the mesh. Because the cluster runs Kubernetes 1.36 with native
sidecars, the `istio-proxy` runs as a restartable init container, so
`kubectl -n coder get pod` reports the Coder pod as `2/2` with `coder` the only
entry in `.spec.containers` and `istio-init`/`istio-proxy` under
`.spec.initContainers` (a check of `.spec.containers` alone misleadingly looks
like there is no sidecar). Verified live: the Coder pod's
`sidecar.istio.io/status` annotation lists `istio-proxy` under `initContainers`,
and `istioctl proxy-status` shows `coder-...coder` plus
`coder-provisioner-alpha`/`-bravo` SYNCED with istiod 1.30.1. The `coder`
VirtualService (`kubectl get virtualservice -n coder`) routes
`*.usgov.coderdemo.io` through `istio-system/public-gateway`, and the gateway
does mTLS to the meshed Coder workload. See
[25-istio-service-mesh.md](25-istio-service-mesh.md).

## Access URLs

```yaml
env:
  - name: CODER_ACCESS_URL
    value: "https://dev.usgov.coderdemo.io"
  - name: CODER_WILDCARD_ACCESS_URL
    value: "*.usgov.coderdemo.io"
```

The single-level wildcard lets the one ACM cert cover the dashboard and all
workspace apps. Source: `deploy/coder/values.yaml:69-75`. Verified live:
`GET /api/v2/deployment/config` reports `access_url=https://dev.usgov.coderdemo.io`
and `wildcard_access_url=*.usgov.coderdemo.io`.

## Database

`CODER_PG_CONNECTION_URL` is taken from Secret `coder-db` key `url`, a full
libpq connection string for the `coder` database on RDS. Source:
`deploy/coder/values.yaml:77-84`, `deploy/coder/secrets.example.yaml:16-31`.
The connection string enforces `sslmode=require` because RDS sets
`rds.force_ssl=1` (`deploy/coder/secrets.example.yaml:28-31`). The exact
credential value was not read (read-only, secrets out of scope).

## OIDC SSO to Keycloak

```yaml
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

SSO points at the Keycloak realm `coder`. The confidential client secret comes
from Secret `coder-oidc` key `client-secret` (`deploy/coder/secrets.example.yaml:33-43`).
Self-provisioning on first login is enabled for the demo. Source:
`deploy/coder/values.yaml:86-107`.

Verified live (`GET /api/v2/deployment/config`, `oidc` block):
`issuer_url=https://auth.usgov.coderdemo.io/realms/coder`, `client_id=coder`,
`email_field=email`, `username_field=preferred_username`,
`scopes=[openid, profile, email]`, `allow_signups=true`,
`sign_in_text="Sign in with Keycloak"`. Note: `oidc.group_field` is empty
(`None`), confirming group/role sync is not configured (known gap, tracked in
the facts sheet and STATUS notes).

## Auth boundary hardening

Three settings keep all login and git egress inside the GovCloud boundary.

1. **GitHub default login provider disabled.**
   `CODER_OAUTH2_GITHUB_DEFAULT_PROVIDER_ENABLE=false`. Coder's built-in GitHub
   login uses Coder's hosted GitHub app and calls github.com, which is out of
   boundary. Disabling it makes login Keycloak SSO plus the local password owner
   only. Source: `deploy/coder/values.yaml:109-115`. Verified live:
   `deployment/config` `oauth2.github.default_provider_enable=false`.

2. **GitLab git external auth (in-boundary SCM).**
   `CODER_EXTERNAL_AUTH_0_*` declares an explicit external-auth provider for the
   in-cluster GitLab: id `gitlab`, type `gitlab`, display `GitLab`, client
   id/secret from Secret `coder-external-auth`
   (`deploy/coder/secrets.example.yaml:57-71`), explicit auth URL
   `.../oauth/authorize`, token URL `.../oauth/token`, validate URL
   `.../oauth/token/info`, regex `gitlab\.usgov\.coderdemo\.io`, scopes
   `read_user read_repository write_repository`. Self-managed GitLab needs the
   explicit URLs. Declaring this provider also suppresses Coder's built-in
   github.com default external-auth provider. Source:
   `deploy/coder/values.yaml:117-148`. Verified live: `deployment/config`
   `external_auth[0]` matches (type `gitlab`, id `gitlab`, the three GitLab
   OAuth URLs, regex, and the three scopes). In-workspace git auth is detailed
   in `70-workspace-templates.md`.

3. **Path-based workspace apps disabled.**
   `CODER_DISABLE_PATH_APPS=true`. Path apps share the dashboard origin and can
   make authenticated requests to the Coder API, so disabling them is the
   hardened posture; every template here serves apps from its own subdomain.
   Source: `deploy/coder/values.yaml:150-157`. Verified live:
   `deployment/config` `disable_path_apps=true`.

## AI Gateway env (seed-once provider config)

```yaml
- name: CODER_AI_GATEWAY_ENABLED
  value: "true"
# Provider 0: Anthropic direct
- CODER_AI_GATEWAY_PROVIDER_0_TYPE = "anthropic"
- CODER_AI_GATEWAY_PROVIDER_0_NAME = "anthropic"
- CODER_AI_GATEWAY_PROVIDER_0_BASE_URL = "https://api.anthropic.com"
- CODER_AI_GATEWAY_PROVIDER_0_KEY  # from Secret coder-ai key ANTHROPIC_API_KEY
# Provider 1: Amazon Bedrock (IRSA, no static key)
- CODER_AI_GATEWAY_PROVIDER_1_TYPE = "bedrock"
- CODER_AI_GATEWAY_PROVIDER_1_NAME = "anthropic-bedrock"
- CODER_AI_GATEWAY_PROVIDER_1_BEDROCK_REGION = "us-gov-west-1"
- CODER_AI_GATEWAY_PROVIDER_1_BEDROCK_MODEL = "us-gov.anthropic.claude-sonnet-4-5-20250929-v1:0"
- CODER_AI_GATEWAY_PROVIDER_1_BEDROCK_SMALL_FAST_MODEL = "amazon.nova-pro-v1:0"
# AWS SDK / IRSA resolution
- AWS_REGION = "us-gov-west-1"
- AWS_DEFAULT_REGION = "us-gov-west-1"
- AWS_STS_REGIONAL_ENDPOINTS = "regional"
```

AI Gateway is enabled by default in v2.34; it is set explicitly here for
clarity. Provider 0 is Anthropic-direct (primary), keyed from Secret `coder-ai`.
Provider 1 is Amazon Bedrock (secondary), authenticated by IRSA with no static
key; Bedrock-ness is detected from `BEDROCK_REGION`. The AWS region and regional
STS endpoint settings make the SDK use the GovCloud regional STS endpoint for
the IRSA `AssumeRoleWithWebIdentity` exchange. Source:
`deploy/coder/values.yaml:159-215`. Provider behavior, routing, and the IRSA
chain are documented in `60-ai-gateway.md`.

Verified live: `deployment/config` `ai.bridge.enabled=true`, and the seeded
`ai.bridge.providers` array contains `anthropic` (type `anthropic`, base
`https://api.anthropic.com`) and `anthropic-bedrock` (type `bedrock`, region
`us-gov-west-1`, model `us-gov.anthropic.claude-sonnet-4-5-20250929-v1:0`,
small fast model `amazon.nova-pro-v1:0`). `chat.ai_gateway_routing_enabled` is
`true`.

### Deprecated-AI-provider-seed drift guard

The `CODER_AI_GATEWAY_PROVIDER_*` env vars are deprecated as of v2.34. They seed
the database once on first startup; after that the database is authoritative and
providers are managed at `/ai/settings`. Editing a seeded env var in place later
(or changing the `coder-ai` secret contents) makes `coderd` refuse to start
(the drift guard). The safe workflow is to change providers in the dashboard,
then reconcile or remove the matching env vars. Treat these values as one-time
seed config and freeze them after first boot. Source:
`deploy/coder/values.yaml:13-16, 159-164`, `deploy/coder/README.md:123-140`.

## Replicas

```yaml
replicaCount: 1
```

Single replica for the demo. HA (`replicaCount > 1`) is an Enterprise feature
and out of scope. Source: `deploy/coder/values.yaml:217-219`. Verified live:
Deployment `coder` has `spec.replicas=1`.

## Licensing and entitlements (AI Governance Add-On plus premium)

AI Gateway requires the AI Governance Add-On license. Per
`deploy/coder/README.md:142-156`, v2.34 has no `CODER_LICENSE` server env var
(the chart/server does not read a license from env or a Secret); the license is
a JWT applied at runtime and stored in the database, via `coder licenses add` or
the dashboard. A `CODER_LICENSE` value does exist in the operator's local env
file, but that is for applying the license with the CLI, not for the chart to
read.

Verified live (`GET /api/v2/entitlements`): `has_license=true`, no warnings, and
the following are entitled and enabled: `aibridge`, `ai_governance_user_limit`
(limit 30, actual 1), `appearance`, `audit_log`, `connection_log`,
`high_availability`, `multiple_external_auth`, `multiple_organizations`,
`template_rbac`, `workspace_prebuilds`, and other premium features. This
confirms both the AI Governance add-on and the broader premium entitlement.

## Appearance banner (runtime DB setting, not Helm)

The classification banner is a runtime database setting, not part of Helm. It is
applied idempotently by `scripts/set-appearance.sh` and shows green
`UNCLASSIFIED - USGOVCLOUD` (`#007a33`). The `appearance` feature is
premium-gated. Source: `STATUS.md:107-116`.

Verified live (`GET /api/v2/appearance`): `service_banner` and
`announcement_banners[0]` are both `enabled=true`, message
`UNCLASSIFIED - USGOVCLOUD`, background color `#007a33`.

## Secrets consumed (names and keys only)

| Secret | Keys | Used by |
|---|---|---|
| `coder-db` | `url` | `CODER_PG_CONNECTION_URL` |
| `coder-oidc` | `client-secret` | `CODER_OIDC_CLIENT_SECRET` |
| `coder-ai` | `ANTHROPIC_API_KEY` | `CODER_AI_GATEWAY_PROVIDER_0_KEY` (seed only) |
| `coder-external-auth` | `gitlab-client-id`, `gitlab-client-secret` | `CODER_EXTERNAL_AUTH_0_CLIENT_ID/SECRET` |

Source: `deploy/coder/secrets.example.yaml` (all values are `REPLACE_ME`
placeholders in the repo; real values are created out-of-band by the platform
layer). Secret values were not read.

## Notes and known gaps

- OIDC group/role sync is not configured (`oidc.group_field` empty live); a
  documented future-work item.
- The `anthropic` provider is currently seeded with a placeholder key; making AI
  respond requires pasting a real key at `/ai/settings`. See `60-ai-gateway.md`.
