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

## Foundations
- [x] GovCloud creds (`demoenv-usgov`, acct 430737322961)
- [x] Service quotas verified healthy
- [x] ACM cert issued + sufficient (`*.usgov.coderdemo.io`)
- [x] Route53 zone `Z06701704WFETYIRU5C8` + NS delegation LIVE
- [x] DNS: `dev` / `auth` / `gitlab` / `*` alias A records -> ingress NLB
- [ ] Bedrock Claude Sonnet 4.5 model access (needs Anthropic agreement via the
      account PAIRED with GovCloud) — still gated
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
- [x] Coder (`dev.`) v2.34.0 — licensed (AI Governance add-on + premium, entitled+enabled); OIDC SSO live
- [x] AI Gateway providers (DB-managed): `anthropic` (direct, enabled) + `anthropic-bedrock` (IRSA, enabled)
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

## Single sign-on + demo super admin
- [x] **One SSO across the stack**: Coder, GitLab, and Grafana all authenticate
      against the Keycloak realm `coder`. Grafana via generic OAuth
      (`scripts/setup-grafana-oidc.py`); GitLab via OmniAuth `openid_connect`
      (`scripts/setup-gitlab-oidc.py`, in `deploy/gitlab/statefulset.yaml`).
- [x] **GitLab CE caveat**: CE has no OIDC group-to-role mapping (an EE
      feature), so GitLab persona users + the instance admin attribute are
      provisioned explicitly by `scripts/setup-gitlab-users.py`
      (`pat.platform` -> admin; others regular).
- [x] **Unified super admin**: the SSO identity `pat.platform` is super admin in
      all three (Coder site Owner via `scripts/grant-coder-owner.py` plus
      org-admin in every org, GitLab Administrator, Grafana org Admin). Pat is a
      member of all three Coder orgs (added to the `/alpha` and `/bravo` Keycloak
      groups in `scripts/setup-keycloak-hierarchy.py`), so the org switcher shows
      Platform, Alpha, and Bravo. Sign in with "Keycloak" on each app.
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

## Observability (in-cluster Prometheus + Grafana)
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
- [x] **Grafana Keycloak SSO (one SSO)**: Grafana signs in via the same realm
      (`coder`) through a confidential OIDC client `grafana`
      (`scripts/setup-grafana-oidc.py`, PKCE; secret in ASM
      `usgov-coderdemo/observability/grafana-oauth`, ESO-synced). Group
      membership maps to org role: `/platform` -> Grafana `Admin`, others ->
      `Viewer`; local admin kept as break-glass. Verified per persona
      (`pat.platform` Admin, `dana.dev` Viewer).
- [x] **Structured JSON server logs** (`CODER_LOGGING_JSON=/dev/stderr`,
      `CODER_LOGGING_HUMAN=/dev/null`) make coderd SIEM-ready; audit logging is
      entitled + on (`/audit`).
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
