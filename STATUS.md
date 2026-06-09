# Demo build status

Single source of progress truth for the lean Coder+AI GovCloud demo.
Target: `us-gov-west-1`, `usgov.coderdemo.io`. Account `430737322961`.

> Engineering "as-built" documentation (architecture, configuration, and the
> declarative-vs-imperative ledger) lives in [`docs/as-built/`](docs/as-built/README.md).

> Overnight autonomous build by Coder Agents. **The full stack is deployed and
> running.** One action remains before AI responses work end to end: drop a real
> Anthropic API key into the `anthropic` AI provider (see "Remaining action").

## Live environment

| Service | URL | Auth / notes |
|---|---|---|
| Coder | https://dev.usgov.coderdemo.io | Owner login (password) or "Sign in with Keycloak" (OIDC). |
| Keycloak | https://auth.usgov.coderdemo.io | Realm `coder` imported; admin console at `/admin`. |
| GitLab | https://gitlab.usgov.coderdemo.io | root + `GITLAB_ROOT_PASSWORD` (embedded Postgres). |

All credentials generated overnight are in **`~/.config/usgov-coderdemo/generated-secrets.env`**
(gitignored, mode 600): Coder owner, Keycloak admin, Keycloak `demo` user, DB
passwords, and the Coder<->Keycloak OIDC client secret. The GitLab root password
is `GITLAB_ROOT_PASSWORD` in `~/.config/usgov-coderdemo/env`.

## Current state (2026-06-09)

Follow-on wave applied live and pushed on branch `ws-2x/phase2` (DRAFT PR #38):

- **Coder control plane v2.34.1** (was v2.34.0; image `ghcr/coder/coder:v2.34.1`,
  live `v2.34.1+2e8d80a`, coderd 2/2 with 0 restarts). Driver: Bedrock SigV4
  proxy-header fix (backport #26053). The two external provisioner daemons
  (alpha/bravo) were rebuilt to v2.34.1.
- **AI Gateway providers (DB-managed)**: `anthropic` (direct), `openai` (direct),
  and `anthropic-bedrock` (GovCloud IRSA, `us-gov-west-1`, Sonnet 4.5) all
  enabled. Bedrock is now ENABLED and verified HTTP 200 (blocking, streaming,
  anthropic-beta); it was previously blocked on v2.34.0 by a SigV4 403.
- **Coder Agents model picker** curated to exactly 4 enabled models, each at
  reasoning effort `high` with an estimated per-model cost (USD per 1M in/out):
  Opus 4.8 (Anthropic Direct) 15/75; Sonnet 4.6 (Anthropic Direct, DEFAULT)
  3/15; GPT 5.5 (OpenAI Direct) 1.25/10; Sonnet 4.5 (GovCloud Bedrock) 3/15.
  Reconciler `scripts/reconcile-ai-providers.py` was extended to manage
  `model_config` (cost + effort).
- **Coder Agents MCP**: a read-only `datastore` MCP server
  (`deploy/datastore-mcp`) is registered via the supported path
  (`/api/experimental/mcp/servers`; slug `datastore`, `auth_type=none`,
  `default_on`, enabled). The deprecated gateway-injected MCP and the datastore
  External Auth were removed.
- **GitLab MCP dropped** (Linear CODAGT-570): GitLab CE 19.0.1 `/api/v4/mcp`
  works standalone, but Coder v2.34.1 cannot connect (GitLab returns 204 on
  `notifications/initialized` while `mark3labs/mcp-go` accepts only 200/202, and
  the RFC 9728 resource-array breaks oauth2 auto-DCR). Not worth a 204-to-202
  shim.
- **Coder Agents chat spend-limits** configured live: global default $500/month
  (master ON), group `alpha`/developers $100, group `bravo` "Everyone" $250
  (org-wide), user `patrickplatform` $50. Precedence is user > MIN(group) >
  default; enforcement is a hard HTTP 409. Control script
  `scripts/demo-chat-spend-limits.py`; doc `docs/plans/chat-spend-limits.md`. The
  AI Bridge `/ai/budget` path is non-functional scaffolding (not used).

## Foundations
- [x] GovCloud creds (`demoenv-usgov`, acct 430737322961)
- [x] Service quotas verified healthy
- [x] ACM cert issued + sufficient (`*.usgov.coderdemo.io`)
- [x] Route53 zone `Z06701704WFETYIRU5C8` + NS delegation LIVE
- [x] DNS: `dev` / `auth` / `gitlab` / `*` alias A records -> ingress NLB
- [x] Bedrock Claude Sonnet 4.5 model access ENABLED in GovCloud
      (`us-gov-west-1`); the `anthropic-bedrock` AI Gateway provider is verified
      HTTP 200 (unblocked by the Coder v2.34.1 SigV4 proxy-header fix)
- [x] Bedrock fallback proven: `amazon.nova-pro-v1:0` invokes in GovCloud

## Substrate (Terraform, applied — PR #4 merged)
- [x] VPC (single, 3 AZ, 1 NAT), RDS PostgreSQL 18.4, ECR, IRSA OIDC + Bedrock role
- [x] EKS cluster `usgov-coderdemo` (k8s 1.36)
- [x] ECR repos + 4 mirrored images (+ `docker-hub/library/postgres:18-alpine` for db bootstrap)

> **Deviation from Terraform (reconcile later):** EKS Auto Mode node provisioning
> is broken in this GovCloud account (the AWS service-linked role
> `AWSServiceRoleForAmazonEKS` lacks `iam:AddRoleToInstanceProfile`/`TagInstanceProfile`,
> so NodeClass validation never succeeds). Auto Mode was disabled and the cluster
> converted to **standard EKS**. See "Deviations to reconcile into Terraform".

## Platform (live cluster)
- [x] 3x m5.xlarge managed node group `mng` (node role `usgov-coderdemo-mngnode`), k8s 1.36
- [x] Addons: vpc-cni, kube-proxy, coredns, aws-ebs-csi-driver (IRSA role `usgov-coderdemo-ebs-csi`)
- [x] `gp3` default StorageClass (encrypted, WaitForFirstConsumer)
- [x] aws-load-balancer-controller + ingress-nginx -> internet-facing NLB (ACM TLS termination)
- [x] In-cluster NLB hairpin to the public hostnames verified (valid TLS) — OIDC + agents work server-side
- [x] RDS roles/dbs: `coder` (owns db `coder`), `keycloak` (owns db `keycloak`); `rds.force_ssl=1`

## Apps (T1)
- [x] Keycloak (`auth.`) — realm `coder` imported; authorize flow for client `coder` returns the login page
- [x] Coder (`dev.`) v2.34.1, licensed (AI Governance add-on + premium, entitled+enabled); OIDC SSO live
- [x] AI Gateway providers (DB-managed): `anthropic` (direct), `openai` (direct), and `anthropic-bedrock` (GovCloud IRSA, `us-gov-west-1`, Sonnet 4.5) all enabled; Bedrock verified HTTP 200 (blocking/streaming/anthropic-beta)
- [x] AI Gateway routing verified end to end: `POST /api/v2/aibridge/anthropic/v1/messages`
      reaches api.anthropic.com (currently 502 "keys failed authentication" — placeholder key)
- [x] Template `claude-code` pushed; test workspace built, agent connected + healthy,
      Claude Code + AgentAPI + code-server installed
- [x] GitLab single-container (`gitlab.`) — embedded Postgres; first boot can take ~15-20 min
- [ ] **Real Anthropic key in the `anthropic` provider** (see below) — only thing gating live AI

## Remaining action (to make AI respond)

The AI path is fully wired but seeded with a **placeholder** Anthropic key (no
real key was available in the environment overnight). To finish:

1. Sign in to https://dev.usgov.coderdemo.io as the owner (creds in
   `generated-secrets.env`).
2. Go to **Admin settings > AI > Providers** (`/ai/settings`).
3. Edit the provider named **`anthropic`** and replace its API key with the real
   `sk-ant-...` key. (Do this in the UI, **not** by editing the `coder-ai`
   k8s secret — the provider config lives in the database now.)
4. Re-run the routing check; it should return 200.

Alternative (in-boundary): enable **Bedrock** Claude Sonnet 4.5 model access in
the GovCloud console, then point Claude Code at the `anthropic-bedrock` provider
(rename it to `anthropic`, or set the workspace model). Bedrock access is still
gated; Nova Pro is the proven fallback.

## Deviations to reconcile into Terraform
1. Auto Mode disabled; standard managed node group `mng` (3x m5.xlarge, `AL2023_x86_64_STANDARD`).
2. New node role `usgov-coderdemo-mngnode` (worker/CNI/ECR/SSM/EBS policies). The
   original Auto Mode node role `usgov-coderdemo-node` is left untouched/unused.
3. EBS CSI IRSA role `usgov-coderdemo-ebs-csi` + addon `service-account-role-arn`.
4. Self-managed addons (vpc-cni, kube-proxy, coredns, aws-ebs-csi-driver) and `gp3` StorageClass.
5. ingress-nginx + aws-load-balancer-controller (Helm) replacing the Auto Mode NLB path.
6. Workspace RBAC: `deploy/platform/workspace-rbac.yaml` (coder SA -> coder-workspaces ns).

## Auth boundary hardening
- [x] Disabled Coder's built-in **GitHub login** default provider
      (`CODER_OAUTH2_GITHUB_DEFAULT_PROVIDER_ENABLE=false`). Login is now
      Keycloak SSO + local password owner only (no github.com egress).
- [x] Configured **GitLab external auth** for git-in-workspaces against the
      in-cluster GitLab (instance-wide OAuth app; id/secret in Secret
      `coder-external-auth`). This also suppresses Coder's default github.com
      external-auth provider, so no auth path leaves the GovCloud boundary.
      (App id/secret recorded in `generated-secrets.env` as
      `GITLAB_CODER_OAUTH_*`.)
- [x] **Every workspace template requires GitLab login.** The `claude-code`
      template declares `data "coder_external_auth" "gitlab"` (id `gitlab`),
      so each workspace must complete the in-boundary GitLab OAuth flow before
      the agent reports ready; the agent's git credential helper then injects a
      short-lived token for clone/fetch/push. Verified: the active template
      version's `/external-auth` lists `gitlab` as required.

## Demo hardening (runtime + Helm)
- [x] **Path-based workspace apps disabled** (`CODER_DISABLE_PATH_APPS=true`,
      Helm rev 4). Workspace apps are served only from their own
      `*.usgov.coderdemo.io` subdomains (all templates use `subdomain = true`),
      removing the same-origin path-app attack surface. Verified live
      (`deployment/config.disable_path_apps = true`).
- [x] **Classification banner** enabled: green `UNCLASSIFIED - USGOVCLOUD`
      (`#007a33`). This is a runtime DB setting (premium-gated), NOT in Helm;
      reproduce with `scripts/set-appearance.sh` (idempotent). Verified via
      `GET /api/v2/appearance`.

## Identity / multi-tenancy (Keycloak -> Coder IdP sync)
- [x] **3 Coder organizations**: `coder` (display "Platform Engineering"),
      `alpha` ("Mission Partner Alpha"), `bravo` ("Mission Partner Bravo").
- [x] **Org + group + role sync** from a single full-path `groups` OIDC claim
      (Group Membership mapper on the `coder` client). `assign_default=false`;
      runtime per-org IdP sync (not legacy env vars). Configured by
      `scripts/setup-keycloak-hierarchy.py` + `scripts/setup-coder-idp-sync.py`
      (both idempotent).
- [x] **8 persona users** in realm `coder` (platform lead, SRE/template-admin,
      org admins, developers, data scientist, cross-tenant ISSO/auditor).
- [x] **Verified end to end** with `scripts/verify-oidc-login.py`: each persona
      lands in the right org(s)/group(s)/role(s); tenant isolation holds.
- [x] **Tenant provisioners + templates**: external provisioner daemon per
      tenant org (`deploy/coder/provisioners.yaml`, org-scoped keys) + the
      `claude-code` template pushed into all three orgs.
- See `docs/as-built/45-idp-sync-personas.md` for the full hierarchy + matrix.

## Single sign-on + operator super admin
- [x] **One SSO across the stack**: Coder, GitLab, and Grafana all authenticate
      against the Keycloak realm `coder`. Grafana via generic OAuth
      (`scripts/setup-grafana-oidc.py`); GitLab via OmniAuth `openid_connect`
      (`scripts/setup-gitlab-oidc.py`, in `deploy/gitlab/statefulset.yaml`).
- [x] **GitLab CE caveat**: CE has no OIDC group-to-role mapping (an EE
      feature), so GitLab persona users + the instance admin attribute are
      provisioned explicitly by `scripts/setup-gitlab-users.py`
      (`austen.platform` -> admin; all demo personas regular).
- [x] **Unified super admin**: a dedicated operator SSO identity
      `austen.platform` (its own `SUPERADMIN_PASSWORD`, not a demo persona) is
      super admin in all three (Coder site Owner via
      `scripts/grant-coder-owner.py` plus org-admin in every org, GitLab
      Administrator, Grafana org Admin). It is a member of all three Coder orgs
      (the `/platform`, `/alpha`, and `/bravo` Keycloak groups in
      `scripts/setup-keycloak-hierarchy.py`), so the org switcher shows Platform,
      Alpha, and Bravo. The `pat.platform` persona is a normal Platform lead
      (Platform org-admin only, not a site Owner and not a GitLab admin). Sign in
      with "Keycloak" on each app.
- [x] **Operator MFA enrollment enforced**: `austen.platform` carries the
      Keycloak `webauthn-register` and `CONFIGURE_TOTP` required actions, so the
      first Keycloak sign in forces passkey + TOTP enrollment
      (`scripts/setup-keycloak-hierarchy.py`). The stock browser flow then
      challenges TOTP on later logins; re-running the script never re-forces
      enrollment once the credentials exist.
- [x] **Local break-glass admins** remain per app (Coder owner, GitLab root,
      Grafana admin). Credentials live in
      `~/.config/usgov-coderdemo/generated-secrets.env` and AWS Secrets Manager
      (`usgov-coderdemo/gitlab/secrets` `root_password`,
      `usgov-coderdemo/observability/grafana`); none are committed to git.

## Secrets management (ESO + AWS Secrets Manager)
- [x] **AWS Secrets Manager is the source of truth** for the 9 runtime app
      secrets (`usgov-coderdemo/{coder,keycloak,gitlab}/*`). No secret material
      in git.
- [x] **External Secrets Operator** (chart 2.6.0, ns `external-secrets`, ECR
      mirror image) syncs ASM into the app namespaces via IRSA role
      `usgov-coderdemo-external-secrets` (read-only, scoped to
      `usgov-coderdemo/*`, no static keys). ClusterSecretStore
      `aws-secretsmanager` Valid; all 9 ExternalSecrets SecretSynced.
- [x] Migrated with `scripts/migrate-secrets-to-asm.py`; ESO adopted the
      existing Secrets with byte-identical data (no app disruption);
      delete/recreate recovery verified.
- [ ] **EKS Secrets envelope encryption (customer KMS)**: NOT applied
      (irreversible re-encrypt; needs a maintenance decision). Codified in
      `terraform/secrets-hardening.tf`.
- See `docs/as-built/85-secrets-management.md`.

## Observability (in-cluster Prometheus + Grafana + Loki)
- [x] **In-boundary metrics + dashboards** via the
      `prometheus-community/kube-prometheus-stack` Helm release `kps` (ns
      `monitoring`, ECR-mirrored images). Prometheus (2/2), Grafana (3/3), and
      the operator (1/1) are healthy.
- [x] **Coder Prometheus metrics enabled** (`CODER_PROMETHEUS_ENABLE=true`,
      `CODER_PROMETHEUS_ADDRESS=0.0.0.0:2112`, agent stats on). A headless
      `coder-metrics` Service + ServiceMonitor scrapes the control plane;
      Prometheus `up{job="coder-metrics"}` is `1`.
- [x] **Six Coder Grafana dashboards** (from `github.com/coder/observability`)
      render live data at `https://grafana.usgov.coderdemo.io` (valid TLS,
      HTTP 200). Grafana admin password lives in AWS Secrets Manager
      (`usgov-coderdemo/observability/grafana`) and is synced by ESO.
- [x] **In-cluster logs via Loki + Promtail** (hand-rolled manifests
      `deploy/observability/loki.yaml` + `promtail.yaml`, ECR-mirrored
      `grafana/loki:3.5.9` and `grafana/promtail:3.5.9`). Single-binary Loki
      stores on a 10Gi gp3 PVC (filesystem, tsdb schema v13, 168h retention); a
      Promtail DaemonSet tails `/var/log/pods` on every node and pushes pod logs
      to `loki.monitoring.svc:3100`, covering namespaces `coder`,
      `coder-workspaces`, `gitlab`, `keycloak`, `monitoring`, and
      `external-secrets`. A Grafana datasource ConfigMap
      (`deploy/observability/loki-datasource.yaml`, uid `loki`) provisions it via
      the sidecar, so the Coder dashboards' log panels (workspace-detail "Logs",
      provisionerd, workspaces) resolve instead of showing a datasource error.
      Prometheus scrapes both (`up{job="loki"}` and `up{job="promtail"}` are
      `1`).
- [x] **`coder-status` dashboard adapted to this stack**: the upstream
      "Observability Tools" row (distributed Loki, Grafana Agent, config
      reloaders, storage/CPU/RAM) was replaced with Prometheus, Loki, and
      Promtail `up` panels; "Workspace Builds" repointed to
      `coderd_workspace_latest_build_status` and "Postgres" to a real
      `coderd_db_tx_duration_seconds` signal (no postgres_exporter runs).
- [x] **Merged AI Governance dashboard** (`deploy/observability/dashboards-ai-governance.yaml`,
      uid `ai-governance`, ns `monitoring`) covers the AI Gateway (AI Bridge) and
      the Agent Firewall (Boundary) in one view, replacing the two add-on
      dashboards. AI Gateway panels use `coder_aibridged_*` (configured providers,
      reload health, provider inventory) plus AI Bridge Loki logs
      (`{namespace="coder"} |~ "aibridged"`); Agent Firewall panels use
      `agent_boundary_log_proxy_batches_forwarded_total` plus Boundary Loki logs
      (`{namespace="coder-workspaces"} |= "boundary"`). All ten query panels
      verified HTTP 200 via Grafana `/api/ds/query`; usage panels read `0` until
      live AI traffic occurs (placeholder Anthropic key).
- [x] **Grafana Keycloak SSO (one SSO)**: Grafana signs in via the same realm
      (`coder`) through a confidential OIDC client `grafana`
      (`scripts/setup-grafana-oidc.py`, PKCE; secret in ASM
      `usgov-coderdemo/observability/grafana-oauth`, ESO-synced). Group
      membership maps to org role: `/platform` -> Grafana `Admin`, others ->
      `Viewer`; local admin kept as break-glass. Verified per persona
      (`austen.platform` Admin, `dana.dev` Viewer).
- [x] **Structured JSON server logs** (`CODER_LOGGING_JSON=/dev/stderr`,
      `CODER_LOGGING_HUMAN=/dev/null`) make coderd SIEM-ready; audit logging is
      entitled + on (`/audit`). Promtail also ships these lines to the
      in-cluster Loki, so they are queryable in Grafana.
- [ ] AWS-native managed variant (AMP + AMG, CloudWatch -> Security Lake) is the
      production target, planned only. See
      [`docs/plans/observability-aws-native.md`](docs/plans/observability-aws-native.md)
      and issues #13-#20.
- See `docs/as-built/55-observability.md` and `deploy/observability/README.md`.

## Planned (design + issues, nothing applied)
- [ ] **GitOps control plane** (Argo CD, sourced from the in-cluster GitLab,
      app-of-apps over the existing `deploy/` paths, adopt-in-place):
      [`docs/plans/gitops-control-plane.md`](docs/plans/gitops-control-plane.md),
      issues #6-#12.
- [ ] **Per-workload GitOps adoption** + non-Kubernetes app state (Coder API via
      Argo Jobs, Keycloak via keycloak-config-cli, AWS stays Terraform):
      [`docs/plans/gitops-adoption.md`](docs/plans/gitops-adoption.md),
      issues #21-#29.
- [ ] **AWS-native observability** (AMP/AMG, CloudWatch/Firehose/S3/Athena,
      optional Security Lake):
      [`docs/plans/observability-aws-native.md`](docs/plans/observability-aws-native.md),
      issues #13-#20.

## Out of scope (demo)
OpenShift, Istio.
