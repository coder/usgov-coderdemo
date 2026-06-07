# As-built: declarative (Terraform) vs imperative (CLI/Helm/kubectl/SQL/API)

A complete ledger of what is managed by Terraform versus what was done by hand
during the overnight build. Grounded in `terraform/*.tf`, `deploy/*`,
`scripts/*`, `STATUS.md`, and read-only live output captured 2026-06-07.

Bottom line: the AWS substrate primitives (VPC, RDS, base IAM, IRSA OIDC +
Bedrock role, the EKS cluster object) are Terraform. Everything inside or on top
of the cluster (node group, addons, storage, ingress, DNS records, DB
roles/schemas, ECR repos and image content, all Kubernetes objects, Keycloak,
GitLab, Coder, and runtime config) was applied imperatively. The Terraform
`helm` and `kubernetes` providers are declared in `terraform/versions.tf` but no
`helm_release` or `kubernetes_*` resources exist, so no in-cluster object is
under Terraform control.

## Declarative (Terraform, `terraform/`, PR #4 merged)

| Resource | Terraform source | Notes |
|---|---|---|
| VPC `10.0.0.0/16`, IGW | `vpc.tf` | `aws_vpc.this`, `aws_internet_gateway.this` |
| 3 public + 3 private subnets, tagged for ELB | `vpc.tf` | `aws_subnet.public/private` |
| 1 NAT gateway + EIP, route tables, associations | `vpc.tf` | single NAT by design (EIP quota/cost) |
| EKS cluster `usgov-coderdemo` (k8s 1.36) | `eks.tf` | declared as Auto Mode; live cluster is standard (see drift note) |
| EKS deployer access entry + cluster-admin association | `eks.tf` | `aws_eks_access_entry.deployer` + policy association |
| Cluster IAM role `usgov-coderdemo-cluster` + 5 policies | `iam-eks.tf` | Auto Mode compute/storage/LB/networking policies, still attached |
| Auto Mode node role `usgov-coderdemo-node` + 2 policies | `iam-eks.tf` | provisioned but unused (node group uses a different role) |
| IAM OIDC provider for the cluster | `irsa.tf` | `aws_iam_openid_connect_provider.eks` |
| Coder Bedrock IRSA role `usgov-coderdemo-coder-bedrock` + inline `bedrock-invoke` | `irsa.tf` | trust limited to `coder:coder` SA |
| RDS subnet group, security group | `rds.tf` | SG allows tcp/5432 from `10.0.0.0/16` |
| RDS instance `usgov-coderdemo-pg` (PG 18.4, Multi-AZ) + master password | `rds.tf` | `random_password.db` |
| Secrets Manager `usgov-coderdemo/rds/master` + version | `rds.tf` | master `dbadmin` creds JSON |
| Outputs (`.substrate-outputs.json`) | `outputs.tf` | includes `ecr_registry` as a derived string only |
| S3/DynamoDB state backend config | `backend.tf` | bucket + lock table are bootstrap inputs, not managed here |

Inputs referenced but NOT managed by this Terraform (pre-existing, passed by
ID/ARN in `variables.tf`): the Route53 hosted zone `Z06701704WFETYIRU5C8` and
the ACM certificate `7f4fc566-8efd-4aa5-b6ba-3b0c9a535d12`. The `ecr_registry`
output is a constructed string; the ECR repositories themselves are not
Terraform resources (created by the mirror script, see below).

### Terraform-vs-live drift (declared but diverged)

- `eks.tf` declares Auto Mode (`compute_config.enabled = true`,
  `node_pools = ["general-purpose","system"]`, managed `block_storage` and
  `elastic_load_balancing`). Live `aws eks describe-cluster` shows all three
  disabled. The cluster runs as standard EKS. Reason: the GovCloud
  `AWSServiceRoleForAmazonEKS` SLR lacks `iam:AddRoleToInstanceProfile` /
  `iam:TagInstanceProfile`, so Auto Mode NodeClass validation never succeeds
  (`deploy/platform/README.md`, `STATUS.md`).
- The cluster IAM role keeps the Auto Mode compute/storage/LB policies even
  though those functions are now self-managed.

## Imperative (CLI / Helm / kubectl / SQL / API)

| Action | Mechanism | Evidence |
|---|---|---|
| Disable EKS Auto Mode (compute/storage/ELB) | `aws eks update-cluster-config` | `deploy/platform/README.md`; live `describe-cluster` all `false` |
| Node IAM role `usgov-coderdemo-mngnode` + 5 managed policies | AWS CLI/IAM | live `aws iam list-attached-role-policies` |
| Managed node group `mng` (3x m5.xlarge, AL2023, static 2/3/4) | `aws eks create-nodegroup` (CLI) | live `aws eks describe-nodegroup`; `deploy/platform/README.md` |
| EBS CSI IRSA role `usgov-coderdemo-ebs-csi` + trust + `AmazonEBSCSIDriverPolicy` | AWS CLI/IAM | live IAM; `deploy/platform/README.md` |
| Bind EBS CSI addon to the IRSA role | `aws eks update-addon --service-account-role-arn` | `deploy/platform/README.md` |
| Self-managed addons: `vpc-cni`, `kube-proxy`, `coredns`, `aws-ebs-csi-driver` | `aws eks create-addon` | live `aws eks list-addons` (TF sets `bootstrap_self_managed_addons=false`) |
| Default `gp3` StorageClass (encrypted, WaitForFirstConsumer) | `kubectl apply` | live `kubectl get sc gp3 -o yaml` |
| `aws-load-balancer-controller` (kube-system) | Helm | live Helm release `aws-load-balancer-controller.v1` |
| `ingress-nginx` chart 4.15.1 (+ internet-facing NLB) | Helm | live Helm release `ingress-nginx.v1`; `deploy/platform/ingress-nginx-values.yaml` |
| Route53 alias A records `dev`/`auth`/`gitlab`/`*` -> NLB | AWS CLI | live `aws route53`; `deploy/platform/README.md` |
| RDS roles + databases (`coder`, `keycloak`) | in-cluster SQL Job (`postgres:18-alpine`) | `deploy/platform/README.md` |
| ECR repositories + image mirroring (5 images) | `scripts/mirror-images.sh` (crane) + `scripts/images.txt` | live `aws ecr describe-repositories` |
| k8s Secrets `coder-db`, `coder-oidc`, `coder-ai`, `coder-external-auth` | `kubectl create secret` | `deploy/coder/secrets.example.yaml`; `deploy/platform/README.md` |
| k8s Secrets `keycloak-db`, `keycloak-admin`, `gitlab-secrets` | `kubectl create secret` | `deploy/keycloak/README.md`, `deploy/gitlab/README.md` |
| Workspace RBAC in `coder-workspaces` | `kubectl apply -f deploy/platform/workspace-rbac.yaml` | live `kubectl get role -n coder-workspaces` |
| Keycloak Deployment/Service/Ingress + realm `coder` import | `kubectl apply -k deploy/keycloak/` | `deploy/keycloak/*`; live pod `keycloak` |
| GitLab StatefulSet/Service/Ingress (embedded Postgres) | `kubectl apply -f deploy/gitlab/*` | `deploy/gitlab/*`; live pod `gitlab-0` |
| Coder control plane | Helm release `coder` (4 revisions) + `deploy/coder/values.yaml` | live Helm release `coder.v1..v4` |
| Coder AI Gateway providers (`anthropic`, `anthropic-bedrock`) | env-seeded once, then DB-authoritative | `deploy/coder/values.yaml`; `STATUS.md` |
| Coder classification banner (`UNCLASSIFIED - USGOVCLOUD`) | `scripts/set-appearance.sh` (runtime DB setting) | `scripts/set-appearance.sh`; `STATUS.md` |
| Coder AI Governance add-on license | `coder licenses add` / UI (runtime JWT in DB) | `deploy/coder/README.md`; `STATUS.md` |
| GitLab instance-wide OAuth app (id/secret -> `coder-external-auth`) | GitLab API / Rails console | `STATUS.md`; `deploy/coder/secrets.example.yaml` |
| Coder template `claude-code` push | `coder templates push` | `coder-templates/claude-code/main.tf`; `STATUS.md` |

Unverified detail: the `aws-load-balancer-controller` almost certainly uses its
own IRSA role, but the exact role name was not checked live, so it is left
unverified here.

Abandoned artifact: `deploy/platform/nodepool.yaml` is an Auto Mode
NodeClass/NodePool workaround that was not applied to the standard cluster; it
remains in the repo for history only.

## Reconciliation backlog (to fold into Terraform)

This mirrors the `STATUS.md` "Deviations to reconcile into Terraform" list and
expands it with every imperative item found above. Ordered roughly by layer.

1. Flip `terraform/eks.tf` from Auto Mode to standard EKS (disable
   `compute_config`, `storage_config.block_storage`, and
   `kubernetes_network_config.elastic_load_balancing`); drop the unused Auto
   Mode policies from the cluster role if no longer needed.
2. Add a managed node group `mng` (3x m5.xlarge, `AL2023_x86_64_STANDARD`,
   static min2/desired3/max4, private subnets) as
   `aws_eks_node_group`.
3. Add node role `usgov-coderdemo-mngnode` with its five managed policies;
   decide whether to remove the now-unused `usgov-coderdemo-node` role.
4. Add the EBS CSI IRSA role `usgov-coderdemo-ebs-csi` and manage the four EKS
   addons as `aws_eks_addon` (with the CSI addon's `service_account_role_arn`).
5. Manage the `gp3` default StorageClass (kubernetes provider or a bootstrap
   manifest).
6. Manage `aws-load-balancer-controller` and `ingress-nginx` (and the LB
   controller IRSA role) via the `helm` provider; capture the NLB annotations.
7. Manage Route53 alias A records (`dev`, `auth`, `gitlab`, `*`) ->
   ingress NLB as `aws_route53_record` (alias to the NLB).
8. Codify RDS role/database creation (`coder`, `keycloak`) instead of the ad hoc
   SQL Job, or document it as an explicit post-apply step.
9. Manage ECR repositories as `aws_ecr_repository` (the registry host is already
   an output); keep image mirroring (`scripts/mirror-images.sh`) as an explicit
   pipeline step since image content is not Terraform's job.
10. Decide a source of truth for Kubernetes Secrets (`coder-db`, `coder-oidc`,
    `coder-ai`, `coder-external-auth`, `keycloak-db`, `keycloak-admin`,
    `gitlab-secrets`); keep real values out of git.
11. Manage workspace RBAC (`coder-workspaces` Role/RoleBinding) declaratively.
12. Manage Keycloak (Deployment/Service/Ingress + realm import) and GitLab
    (StatefulSet/Service/Ingress) manifests under a GitOps or Terraform path.
13. Manage the Coder Helm release and `values.yaml` declaratively; note that AI
    Gateway provider env vars only seed the DB once, so treat them as one-time
    seed config and manage providers in the DB afterward.
14. Treat these as runtime/out-of-band, not Terraform: the AI Governance license
    JWT, the appearance banner DB setting, the GitLab OAuth app, and the Coder
    template push. Document them as runbook steps.

Note: the Route53 hosted zone and ACM certificate are pre-existing inputs and do
not need to be created by Terraform; only the records inside the zone are part of
the backlog.
