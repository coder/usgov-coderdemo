# As-built: secrets management (External Secrets Operator + AWS Secrets Manager)

Runtime secrets are sourced from **AWS Secrets Manager** (ASM) and synced into
Kubernetes by the **External Secrets Operator** (ESO), which authenticates to
ASM with **IRSA** (no static AWS keys). ASM is the source of truth; no secret
material is committed to git, and the app control-plane manifests are unchanged
because ESO produces Kubernetes Secrets with the same names and keys the apps
already reference.

This replaces the earlier bootstrap approach (secrets generated into a local
gitignored file and applied as plain `kubectl create secret`). That file
(`~/.config/usgov-coderdemo/generated-secrets.env`) is retained only as the
break-glass bootstrap source for setup scripts; it is gitignored.

## Flow

```
AWS Secrets Manager (usgov-coderdemo/*)
        |  GetSecretValue / DescribeSecret  (IRSA: usgov-coderdemo-external-secrets)
        v
External Secrets Operator (ns external-secrets)
  ClusterSecretStore "aws-secretsmanager"  ->  ExternalSecret (per app secret)
        |  writes/owns
        v
Kubernetes Secret (coder, keycloak, gitlab, gitlab-runner, monitoring, istio-system ns)  ->  consumed by app pods (secretKeyRef)
```

## What runs where

| Piece | Detail |
|---|---|
| ESO | Helm chart `external-secrets` 2.6.0, ns `external-secrets` (controller + webhook + cert-controller, all 1/1). Image from the ECR mirror `ghcr/external-secrets/external-secrets:v2.6.0`. Values: `deploy/platform/external-secrets/values.yaml`. |
| IRSA role | `usgov-coderdemo-external-secrets`. Trust: `system:serviceaccount:external-secrets:external-secrets`. Policy: `secretsmanager:GetSecretValue` + `DescribeSecret` on `arn:aws-us-gov:secretsmanager:us-gov-west-1:430737322961:secret:usgov-coderdemo/*` only. Codified in `terraform/secrets-hardening.tf`. |
| Store | `ClusterSecretStore/aws-secretsmanager` (AWS SecretsManager, region us-gov-west-1, `auth.jwt.serviceAccountRef` -> the ESO controller SA). Status `Valid`. |
| ExternalSecrets | 14 total: 12 in `deploy/platform/external-secrets/secretstore-and-externalsecrets.yaml`, plus `deploy/istio/observability/externalsecret-kiali-oauth.yaml` (Istio mesh) and `deploy/gitlab-runner/externalsecret.yaml` (GitLab CI runners). Each `dataFrom.extract`, `creationPolicy: Owner`, `refreshInterval: 1h`. |

## ASM secret layout

Each ASM secret is a JSON object whose keys match the target Kubernetes Secret
keys. ESO `extract` materializes them 1:1.

| ASM secret | JSON keys | Kubernetes Secret (ns/name) |
|---|---|---|
| usgov-coderdemo/coder/db | url | coder/coder-db |
| usgov-coderdemo/coder/oidc | client-secret | coder/coder-oidc |
| usgov-coderdemo/coder/ai | ANTHROPIC_API_KEY | coder/coder-ai |
| usgov-coderdemo/coder/external-auth | gitlab-client-id, gitlab-client-secret | coder/coder-external-auth |
| usgov-coderdemo/coder/provisioner-alpha | key | coder/coder-provisioner-alpha |
| usgov-coderdemo/coder/provisioner-bravo | key | coder/coder-provisioner-bravo |
| usgov-coderdemo/keycloak/admin | username, password | keycloak/keycloak-admin |
| usgov-coderdemo/keycloak/db | username, password | keycloak/keycloak-db |
| usgov-coderdemo/gitlab/secrets | initial_root_password, root_password | gitlab/gitlab-secrets |
| usgov-coderdemo/gitlab/oidc | client-secret | gitlab/gitlab-oidc |
| usgov-coderdemo/gitlab/runner | runner-token, runner-registration-token | gitlab-runner/gitlab-runner-auth |
| usgov-coderdemo/observability/grafana | admin-user, admin-password | monitoring/grafana-admin |
| usgov-coderdemo/observability/grafana-oauth | client-secret | monitoring/grafana-oauth |
| usgov-coderdemo/observability/kiali-oauth | oidc-secret | istio-system/kiali |

Twelve of these ExternalSecrets live in
`deploy/platform/external-secrets/secretstore-and-externalsecrets.yaml`. The
Kiali OAuth secret ships with the Istio mesh
(`deploy/istio/observability/externalsecret-kiali-oauth.yaml`, target Secret
`kiali` key `oidc-secret`) and the GitLab Runner auth token ships with the CI
runners (`deploy/gitlab-runner/externalsecret.yaml`). All reference the one
`aws-secretsmanager` ClusterSecretStore.

`usgov-coderdemo/rds/master` (the RDS master credential) predates this and is
managed by Terraform; the apps do not read it.

## Migration (one time, idempotent)

`scripts/migrate-secrets-to-asm.py` reads the live Kubernetes Secrets (the prior
source of truth) and writes each as a JSON ASM secret. Values are passed to the
AWS CLI via mode-600 temp files, never on the command line. ESO then adopted the
existing Secrets in place.

## Verification (performed)

- ClusterSecretStore `aws-secretsmanager`: `Ready=True reason=Valid` (IRSA to
  ASM works). It is the only store object; no namespaced `SecretStore` exists
  (`kubectl get secretstore,clustersecretstore -A`).
- All 14 ExternalSecrets: `SecretSynced=True` (`kubectl get externalsecret -A`),
  spanning namespaces `coder`, `keycloak`, `gitlab`, `gitlab-runner`,
  `monitoring`, and `istio-system`.
- For the 9 control-plane Secrets that pre-dated ESO, the operator adopted them
  in place with byte-identical data (sha256 of the data map matched before and
  after for all 9), so running pods were not disrupted. ESO now owns them
  (`reconcile.external-secrets.io/managed=true`, ownerReference to the
  ExternalSecret). The five added later (`gitlab-oidc`, `gitlab-runner-auth`,
  `grafana-admin`, `grafana-oauth`, and the Kiali `kiali-oauth`) were created
  directly as ESO-owned, not adopted.
- Recovery proven: deleting `coder/coder-ai` caused ESO to rebuild it from ASM
  within seconds with the identical value.

## Operational notes

- **Rotation:** update the value in ASM (or `put-secret-value`). ESO refreshes
  the Kubernetes Secret within `refreshInterval` (1h) or immediately if the
  Secret is deleted. Pods that read a secret as an env var (`secretKeyRef`) only
  pick up a new value on restart; roll the relevant Deployment after rotation.
- **Least privilege:** the ESO role can only read `usgov-coderdemo/*` and cannot
  write to ASM. Rotation is a separate, deliberate action.
- **No secrets in git:** only `deploy/*/secrets.example.yaml` placeholders are
  committed. Real values live in ASM; the local `generated-secrets.env` is
  gitignored and outside the repo.

## Still on the backlog

- **EKS Secrets envelope encryption with a customer-managed KMS key.** Today the
  cluster uses only the default AWS-managed etcd encryption
  (`encryptionConfig=null`). `terraform/secrets-hardening.tf` defines the CMK and
  documents the `encryption_config` to add to the cluster. Enabling it is
  IRREVERSIBLE and triggers a re-encrypt, so it is intentionally not applied yet;
  it needs an explicit maintenance decision.
- **Fold the live ESO IAM role into a Terraform apply** (created via CLI; import
  before apply). See `docs/as-built/80-iac-vs-imperative.md`.

## Reproduce

```
. ~/.config/usgov-coderdemo/env
export KUBECONFIG=./kubeconfig
# 1. mirror the ESO image (already in scripts/images.txt)
scripts/mirror-images.sh
# 2. ESO IAM role: see terraform/secrets-hardening.tf (or the CLI in git history)
# 3. install ESO
helm upgrade --install external-secrets external-secrets/external-secrets \
  --version 2.6.0 -n external-secrets --create-namespace \
  -f deploy/platform/external-secrets/values.yaml
# 4. seed ASM from the current cluster secrets
python3 scripts/migrate-secrets-to-asm.py
# 5. store + ExternalSecrets
kubectl apply -f deploy/platform/external-secrets/secretstore-and-externalsecrets.yaml
```
