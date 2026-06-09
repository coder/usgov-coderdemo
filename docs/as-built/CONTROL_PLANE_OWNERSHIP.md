# Control-plane ownership (usgov-coderdemo)

As-built map of who writes what. The goal is ONE authoritative writer per
domain; everything else consumes or verifies. Run `scripts/verify-drift.py`
to check live state against this map. This documents the CURRENT reality,
including known drift; the convergence path is in
`docs/plans/gitops-control-plane.md` and the chat plan for this work.

## Rules

- One authoritative writer per domain (the "source of truth" column).
- AWS Secrets Manager (`usgov-coderdemo/*`) is authoritative for secret
  VALUES. Terraform manages secret CONTAINERS and IAM, not raw values, to keep
  values out of tfstate. External Secrets Operator (ESO, IRSA) mirrors ASM into
  Kubernetes Secrets; k8s Secrets are consumers, never sources.
- `~/.config/usgov-coderdemo/generated-secrets.env` is a bootstrap artifact and
  a KNOWN parallel source of truth. Target state: derive it from ASM, never
  seed live systems from it as canonical. Do not treat it as authoritative.
- Placeholders must FAIL verification, never satisfy an "exists" check.
- No `kubectl set env`, `coder ... edit`, `gitlab-rails`, or API-only seeding
  as a silent source of truth. If used for break-glass, record it in git/docs
  immediately.

## Domain map

| Domain | Source of truth | Writer / mechanism | In git? | Drift status |
|---|---|---|---|---|
| AWS network/IAM/IRSA/RDS | Terraform (`terraform/`, S3 backend) | `terraform apply` | yes | clean |
| EKS compute (cluster + nodes) | Terraform (intended) | live cluster is standard EKS with CLI node group `mng`; `eks.tf` declares Auto Mode | no | DRIFT: live diverged from TF |
| Node-group capacity | (should be Terraform) | `aws eks update-nodegroup` CLI | no | DRIFT: CLI-only (e.g. desiredSize) |
| Route53 DNS records | (should be Terraform) | `aws route53` CLI | no | DRIFT: CLI-only |
| ECR repos + mirrored images | git `images.txt` (list) | `scripts/mirror-images.sh` (crane) | partial | repos/content not in git |
| Secret values | ASM `usgov-coderdemo/*` | bootstrap + `scripts/migrate-secrets-to-asm.py` + per-secret reconcilers | values not in git (by design) | parallel copy in `generated-secrets.env` |
| k8s Secret objects | ASM via ESO | `deploy/platform/external-secrets/*` + per-app ExternalSecrets | yes (CRDs) | clean (verify-drift checks fingerprints) |
| coderd server config | `deploy/coder/values.yaml` | Helm, applied via CLI | yes | applied by hand, no reconciler |
| AI Gateway providers + models | Coder DB; desired state `deploy/coder/ai-providers.yaml` | `scripts/reconcile-ai-providers.py` (API, sends/diffs `model_config`). `values.yaml` env is a FROZEN one-time seed | yes (desired) | DB authoritative; reconcile to converge |
| Coder Agents MCP servers | Coder DB | `POST /api/experimental/mcp/servers` (supported path); `deploy/datastore-mcp/` for the server | partial (server in git) | DB-only registration; gateway-injected MCP removed |
| Coder Agents chat spend-limits | Coder DB | `scripts/demo-chat-spend-limits.py` (API `/api/experimental/chats/usage-limits`) | script only | DB-only effect |
| Coder templates | `coder templates push` | CLI; HCL in `coder-templates/` and `deploy/gitlab-runner/.../template` | partial | pushes/edits imperative |
| Coder runtime settings (banner, owner, idpsync, license) | Coder DB | `scripts/set-appearance.sh`, `grant-coder-owner.py`, `setup-coder-idp-sync.py` | script only | DB-only effect |
| GitLab project + CI vars + runner | GitLab DB | `scripts/setup-gitlab-ci-runners.py` (gitlab-rails + API); runner via Helm `deploy/gitlab-runner` | partial | users/CI/webhooks live-only |
| Keycloak realm + clients | Keycloak DB | `deploy/keycloak/realm-coder.json` (kustomize import) + `setup-keycloak-hierarchy.py`, `setup-*-oidc.py` | partial | script deltas not re-exported |
| Observability / Grafana dashboards | `deploy/observability/*` | `kubectl apply` + Helm; OIDC via script | yes (dashboards) | applied by hand |
| Ingress | `deploy/platform` (ingress-nginx) + `deploy/istio` | Helm / manifests via CLI | yes | applied by hand |
| GitOps reconciler | none yet | planned (`docs/plans/gitops-control-plane.md`) | n/a | no reconciler exists |

## Secret source-of-truth notes

- ASM is authoritative for secret values; ESO syncs to k8s. `verify-drift.py`
  compares ASM and k8s fingerprints per ExternalSecret and flags MISMATCH.
- The Anthropic API key was the known split (ASM/ESO placeholder vs real in the
  Coder DB). Live ASM `coder/ai` now holds the real key (ESO synced; verifier
  asserts `len>=60` and `sk-ant-` prefix). The Coder DB consumes it via the
  one-time Helm seed and the AI reconciler.
- Script-driven OIDC client secrets (GitLab/Grafana/Kiali) regenerate the
  Keycloak secret on each run and push to ASM; relying parties pick up the new
  value only after a pod restart and ESO refresh. The Coder<->Keycloak OIDC
  client secret has 4 uncoordinated copies and NO reconciler (gap to close).
- First-boot-only seeds (GitLab `initial_root_password`, Coder
  `CODER_AI_GATEWAY_PROVIDER_*`) look ASM-managed but the app DB is
  authoritative after first boot. Changing a seeded Coder AI env var later makes
  coderd fail to start (seed drift guard).

## AI Gateway specifics

- Enabled providers (verified live `GET /api/v2/ai/providers`): `anthropic`
  (direct, primary, demo default), `openai` (direct), and `anthropic-bedrock`
  (GovCloud, IRSA). All three serve via aibridge and back the Coder Agents
  model picker.
- `anthropic-bedrock` is now ENABLED and verified on v2.34.1 (HTTP 200 for the
  blocking, streaming, and anthropic-beta paths). It was disabled on v2.34.0 by
  a SigV4 403: the aibridge egress signed requests that still carried inbound
  Istio/Envoy proxy headers, so the canonical SignedHeaders never matched what
  Bedrock recomputed. Fixed by coder/coder#26019 (strip proxy headers before
  signing), shipped via backport #26053. Sonnet 4.5 foundation-model and the
  us-gov. inference profile are ACTIVE and the IRSA role allowlists both.
- Reconcile providers and model presets from `deploy/coder/ai-providers.yaml`
  with `scripts/reconcile-ai-providers.py` (sends/diffs `model_config`: cost
  plus provider_options reasoning effort).

## Coder Agents specifics

- Model picker: 4 enabled models (Opus 4.8 Direct; Sonnet 4.6 Direct, default;
  GPT 5.5 Direct; Sonnet 4.5 GovCloud Bedrock), each reasoning effort high with
  an estimated cost. Source of truth `deploy/coder/ai-providers.yaml`; managed
  via `/api/experimental/chats/model-configs`. See
  `docs/as-built/65-coder-agents.md`.
- Datastore MCP: read-only `datastore` server registered via the supported path
  (`POST /api/experimental/mcp/servers`; `deploy/datastore-mcp/`). The
  deprecated gateway-injected MCP was removed from `values.yaml`. GitLab MCP
  evaluated and dropped (CODAGT-570).
- Chat spend-limits: global default plus group/user overrides via
  `scripts/demo-chat-spend-limits.py`; hard HTTP 409 at or over the limit;
  design in `docs/plans/chat-spend-limits.md`.
