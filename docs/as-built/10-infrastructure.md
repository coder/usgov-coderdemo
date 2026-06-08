# As-built: AWS GovCloud infrastructure

As-built record of the AWS GovCloud substrate for the Coder demo. Every row is
grounded in a repo file or a read-only command run against the live account on
2026-06-07. Values that could not be verified are marked "unverified".

## Account and region

| Fact | Value | Source |
|---|---|---|
| Partition | `aws-us-gov` | `terraform/providers.tf`, `versions.lock.yaml` |
| Account | `430737322961` | `.substrate-outputs.json`, live `aws sts`/IAM ARNs |
| Region | `us-gov-west-1` | `terraform/variables.tf` (`region`), `versions.lock.yaml` |
| Public domain | `usgov.coderdemo.io` | `terraform/variables.tf` (`domain`), `versions.lock.yaml` |
| Terraform state backend | S3 `usgov-coderdemo-tfstate-430737322961`, DynamoDB lock `usgov-coderdemo-tflock`, encrypted | `terraform/backend.tf` |

The backend S3 bucket and DynamoDB table are referenced by `backend.tf` but are
not declared in this Terraform; they are bootstrap inputs created out of band.

## Component summary

| Component | Identifier / key values | Source |
|---|---|---|
| VPC | `vpc-08a88ce74ae217bc7`, CIDR `10.0.0.0/16`, 3 AZ, 1 NAT gateway, 1 IGW | `terraform/vpc.tf`; live `aws ec2 describe-vpcs` |
| Public subnets | 3, `10.0.0.0/20` (1a), `10.0.16.0/20` (1b), `10.0.32.0/20` (1c), `map_public_ip_on_launch=true` | `terraform/vpc.tf`; live `aws ec2 describe-subnets` |
| Private subnets | 3, `10.0.48.0/20` (1a), `10.0.64.0/20` (1b), `10.0.80.0/20` (1c) | `terraform/vpc.tf`; live `aws ec2 describe-subnets` |
| NAT gateway | `nat-05f778038711165c0` in public subnet `subnet-081b77ab74f26fc2f`; egress path for `api.anthropic.com` | `terraform/vpc.tf`; live `aws ec2 describe-nat-gateways` |
| EKS cluster | `usgov-coderdemo`, k8s `1.36`, STANDARD (Auto Mode disabled), endpoint public+private | live `aws eks describe-cluster`; `terraform/eks.tf` |
| Cluster IAM role | `usgov-coderdemo-cluster` | `terraform/iam-eks.tf`; live IAM |
| Managed node group | `mng`: 3x `m5.xlarge`, `AL2023_x86_64_STANDARD`, ON_DEMAND, min2/desired3/max4, static, 20Gi disk, private subnets | live `aws eks describe-nodegroup`; `deploy/platform/README.md` |
| Node IAM role | `usgov-coderdemo-mngnode` (5 managed policies) | live IAM; `deploy/platform/README.md` |
| Unused node role | `usgov-coderdemo-node` (original Auto Mode role, left attached, unused) | `terraform/iam-eks.tf`; live IAM |
| Cluster addons | `vpc-cni`, `kube-proxy`, `coredns`, `aws-ebs-csi-driver` | live `aws eks list-addons` |
| EBS CSI IRSA role | `usgov-coderdemo-ebs-csi` (`AmazonEBSCSIDriverPolicy`) | live IAM; `deploy/platform/README.md` |
| Coder Bedrock IRSA role | `usgov-coderdemo-coder-bedrock`, inline policy `bedrock-invoke` | `terraform/irsa.tf`; live IAM |
| OIDC provider (IRSA) | `arn:aws-us-gov:iam::430737322961:oidc-provider/oidc.eks.us-gov-west-1.amazonaws.com/id/E9DB9E591C95ECB91F44EDCF38F146F2` | `terraform/irsa.tf`; `.substrate-outputs.json` |
| RDS instance | `usgov-coderdemo-pg`, PostgreSQL `18.4`, `db.m6g.large`, Multi-AZ, 50Gi gp3 encrypted, private | `terraform/rds.tf`; live `aws rds describe-db-instances` |
| RDS endpoint | `usgov-coderdemo-pg.crhk7w9eko3r.us-gov-west-1.rds.amazonaws.com:5432` | `.substrate-outputs.json`; live RDS |
| RDS security group | `sg-0f80f84106ca6502e`, ingress tcp/5432 from `10.0.0.0/16` | `terraform/rds.tf`; live RDS |
| RDS master secret | Secrets Manager `usgov-coderdemo/rds/master` (user `dbadmin`) | `terraform/rds.tf`; `.substrate-outputs.json` |
| ECR registry | `430737322961.dkr.ecr.us-gov-west-1.amazonaws.com` | `.substrate-outputs.json`; `terraform/outputs.tf` |
| ACM certificate | `arn:aws-us-gov:acm:us-gov-west-1:430737322961:certificate/7f4fc566-8efd-4aa5-b6ba-3b0c9a535d12` (`*.usgov.coderdemo.io` + apex) | `versions.lock.yaml`; `deploy/platform/ingress-nginx-values.yaml` |
| Route53 zone | `Z06701704WFETYIRU5C8` (`usgov.coderdemo.io`) | `terraform/variables.tf`; live `aws route53` |
| Edge NLB (live) | internet-facing NLB `k8s-istiosys-istioing-bf7bdca8c8-866d61e8e6f9204f.elb.us-gov-west-1.amazonaws.com` (Istio ingress gateway; all Route53 records alias here) | live `kubectl`/`aws elbv2`/`aws route53` |
| Ingress NLB (rollback) | internet-facing NLB `k8s-ingressn-ingressn-e16fe3cd33-c002102481951644.elb.us-gov-west-1.amazonaws.com` (ingress-nginx; out of the DNS path, kept for rollback, issue #34) | live `kubectl`/`aws elbv2` |

## VPC and egress

The VPC is a single `10.0.0.0/16` network spanning three AZ
(`us-gov-west-1a/1b/1c`). Each AZ has one public `/20` and one private `/20`
subnet. Public subnets carry `map_public_ip_on_launch=true` and are tagged
`kubernetes.io/role/elb=1`; private subnets are tagged
`kubernetes.io/role/internal-elb=1`. Both subnet sets are tagged
`kubernetes.io/cluster/usgov-coderdemo=shared` (`terraform/vpc.tf`).

A single NAT gateway (`nat-05f778038711165c0`) lives in a public subnet; the
private route table sends `0.0.0.0/0` through it. The public route table sends
`0.0.0.0/0` through the internet gateway. One NAT was a deliberate choice to
stay within the default Elastic IP quota and reduce cost
(`terraform/vpc.tf`). The NAT gateway is the only egress path out of the
boundary, used by the Anthropic-direct AI provider to reach `api.anthropic.com`.

## EKS cluster: standard, not Auto Mode

Live state shows the cluster running k8s `1.36` with Auto Mode fully disabled:

```
computeConfig.enabled            = false
storageConfig.blockStorage       = false
kubernetesNetworkConfig.elasticLoadBalancing.enabled = false
```

(`aws eks describe-cluster`). This is a deliberate divergence from
`terraform/eks.tf`, which still declares Auto Mode (`compute_config.enabled =
true`, `node_pools = ["general-purpose","system"]`, managed block storage and
elastic load balancing).

Why Auto Mode was abandoned: in this GovCloud account the AWS-managed
service-linked role `AWSServiceRoleForAmazonEKS` lacks
`iam:AddRoleToInstanceProfile` and `iam:TagInstanceProfile`, so Auto Mode
NodeClass validation never completes (the controller creates an instance
profile but never attaches the role, then wedges on `EntityAlreadyExists`).
The cluster was converted to standard EKS instead of fighting the SLR
(`deploy/platform/README.md`, `deploy/platform/nodepool.yaml`, `STATUS.md`).
The abandoned Auto Mode NodeClass/NodePool workaround remains in the repo at
`deploy/platform/nodepool.yaml` but is not applied to the standard cluster.

The cluster IAM role `usgov-coderdemo-cluster` still carries the five Auto Mode
policies (`AmazonEKSClusterPolicy`, `AmazonEKSComputePolicy`,
`AmazonEKSBlockStoragePolicy`, `AmazonEKSLoadBalancingPolicy`,
`AmazonEKSNetworkingPolicy`) from Terraform even though compute/storage/LB are
now self-managed (live `aws iam list-attached-role-policies`).

## Managed node group `mng`

| Attribute | Value |
|---|---|
| Instance type | `m5.xlarge` x3 |
| AMI type | `AL2023_x86_64_STANDARD` |
| Capacity type | `ON_DEMAND` |
| Scaling | min 2, desired 3, max 4 (static; no Karpenter, no cluster-autoscaler) |
| Disk | 20Gi |
| Subnets | the 3 private subnets |
| Node role | `usgov-coderdemo-mngnode` |
| Node version | `1.36` |

Source: live `aws eks describe-nodegroup --cluster-name usgov-coderdemo
--nodegroup-name mng`. Live nodes report `v1.36.1-eks-3385e9b` on Amazon Linux
2023 (`kubectl get nodes -o wide`).

The node role `usgov-coderdemo-mngnode` has five attached managed policies
(live `aws iam list-attached-role-policies`):

- `AmazonEKSWorkerNodePolicy`
- `AmazonEKS_CNI_Policy`
- `AmazonEC2ContainerRegistryReadOnly`
- `AmazonSSMManagedInstanceCore`
- `AmazonEBSCSIDriverPolicy`

The original Auto Mode node role `usgov-coderdemo-node` (from
`terraform/iam-eks.tf`) still exists but is unused (live `aws iam get-role`).

## EBS CSI driver and IRSA

`aws-ebs-csi-driver` runs as an EKS addon. Its controller could not reach IMDS
for credentials, so it uses IRSA: role `usgov-coderdemo-ebs-csi`, trusting the
cluster OIDC provider for service account `kube-system:ebs-csi-controller-sa`,
attached to `AmazonEBSCSIDriverPolicy` (one attached policy, no inline policies;
live `aws iam list-attached-role-policies` / `list-role-policies`). The addon
was bound to the role with `--service-account-role-arn`
(`deploy/platform/README.md`). The default StorageClass is `gp3` (documented in
the platform layer doc).

## Coder Bedrock IRSA role

Authored in `terraform/irsa.tf` (output `bedrock_role_arn`). The EKS OIDC
provider is registered as an IAM OIDC identity provider; the role trust policy
restricts `sts:AssumeRoleWithWebIdentity` to service account
`system:serviceaccount:coder:coder` with audience `sts.amazonaws.com`.

Inline policy `bedrock-invoke`, exact live actions and resources from
`aws iam get-role-policy --role-name usgov-coderdemo-coder-bedrock
--policy-name bedrock-invoke`:

- Actions: `bedrock:InvokeModel`, `bedrock:InvokeModelWithResponseStream`
- Resources:
  - `arn:aws-us-gov:bedrock:us-gov-west-1::foundation-model/anthropic.claude-sonnet-4-5-20250929-v1:0`
  - `arn:aws-us-gov:bedrock:us-gov-west-1::foundation-model/amazon.nova-pro-v1:0`
  - `arn:aws-us-gov:bedrock:us-gov-west-1:430737322961:inference-profile/us-gov.anthropic.claude-sonnet-4-5-20250929-v1:0`
  - `arn:aws-us-gov:bedrock:us-gov-east-1::foundation-model/anthropic.claude-sonnet-4-5-20250929-v1:0`

The `us-gov.` cross-region inference profile can route to both GovCloud
regions, so the underlying foundation model is allowlisted in both
`us-gov-west-1` and `us-gov-east-1`; Nova Pro is allowlisted in-region only
(`terraform/irsa.tf`).

## RDS PostgreSQL

| Attribute | Value |
|---|---|
| Identifier | `usgov-coderdemo-pg` |
| Engine | PostgreSQL `18.4` |
| Class | `db.m6g.large` |
| Storage | 50Gi gp3, encrypted, autoscale to 200Gi |
| Multi-AZ | true (standby instance; Multi-AZ DB clusters are unsupported in GovCloud) |
| Public access | false |
| Endpoint | `usgov-coderdemo-pg.crhk7w9eko3r.us-gov-west-1.rds.amazonaws.com:5432` |
| Default db / master | db `coder`, master user `dbadmin` |
| Security group | `sg-0f80f84106ca6502e` |
| TLS enforcement | `rds.force_ssl=1` |

Sources: `terraform/rds.tf`; live `aws rds describe-db-instances`. The security
group allows tcp/5432 from the VPC CIDR `10.0.0.0/16` only (`terraform/rds.tf`).
`rds.force_ssl=1` is set on the in-use parameter group `default.postgres18`
(live `aws rds describe-db-parameters`), so all clients connect with TLS
(`sslmode=require`).

Logical databases and roles were created imperatively after provisioning (not in
Terraform): role `coder` owns database `coder`, role `keycloak` owns database
`keycloak` (`deploy/platform/README.md`). GitLab does not use RDS; it runs the
Omnibus embedded PostgreSQL (`deploy/gitlab/README.md`,
`deploy/gitlab/statefulset.yaml`).

Master credentials are stored in Secrets Manager `usgov-coderdemo/rds/master`
as JSON (`username`, `password`, `host`, `port`); the secret is created by
Terraform (`terraform/rds.tf`, output `rds_secret_arn`).

## ECR registry and image mirror

Registry host: `430737322961.dkr.ecr.us-gov-west-1.amazonaws.com`
(`terraform/outputs.tf` is a derived value; the host is not a managed resource).
GovCloud has no ECR pull-through cache, so images are mirrored with `crane` by
`scripts/mirror-images.sh` reading `scripts/images.txt`. The script maps
upstream registries to ECR repository paths
(`docker.io -> docker-hub/...`, `ghcr.io -> ghcr/...`, `quay.io -> quay/...`)
and creates each repo IMMUTABLE with scan-on-push.

Mirrored repositories present live (`aws ecr describe-repositories`):

| ECR repository | Upstream (pinned) | Used by |
|---|---|---|
| `ghcr/coder/coder` | `ghcr.io/coder/coder:v2.34.0` | Coder control plane |
| `quay/keycloak/keycloak` | `quay.io/keycloak/keycloak:26.6.3` | Keycloak |
| `docker-hub/gitlab/gitlab-ce` | `docker.io/gitlab/gitlab-ce:19.0.1-ce.0` | GitLab |
| `docker-hub/codercom/enterprise-base` | `docker.io/codercom/enterprise-base:ubuntu-noble-20260601` | Workspace base image |
| `docker-hub/library/postgres` | `postgres:18-alpine` | DB bootstrap job |

Sources: `scripts/images.txt`, `scripts/mirror-images.sh`,
`deploy/*/README.md`; live `aws ecr describe-repositories`.

## DNS, ACM, and the NLB ingress path

Route53 hosted zone `Z06701704WFETYIRU5C8` holds these records (live
`aws route53 list-resource-record-sets`, re-verified 2026-06-08):

| Record | Type | Target |
|---|---|---|
| `usgov.coderdemo.io` | NS, SOA | delegation |
| `dev.usgov.coderdemo.io` | A (alias) | Istio gateway NLB |
| `auth.usgov.coderdemo.io` | A (alias) | Istio gateway NLB |
| `gitlab.usgov.coderdemo.io` | A (alias) | Istio gateway NLB |
| `grafana.usgov.coderdemo.io` | A (alias) | Istio gateway NLB |
| `kiali.usgov.coderdemo.io` | A (alias) | Istio gateway NLB |
| `*.usgov.coderdemo.io` | A (alias) | Istio gateway NLB |
| `_2632a7fd...usgov.coderdemo.io` | CNAME | ACM DNS validation |

All six service/wildcard records are alias A records pointing at the
internet-facing Istio gateway NLB
`k8s-istiosys-istioing-bf7bdca8c8-866d61e8e6f9204f.elb.us-gov-west-1.amazonaws.com`
(the live edge; each host resolves to its three public IPs, verified live
2026-06-08). The earlier ingress-nginx NLB
`k8s-ingressn-ingressn-e16fe3cd33-c002102481951644.elb.us-gov-west-1.amazonaws.com`
is no longer in any Route53 path; it is kept only for rollback (issue #34). The
`registry.usgov.coderdemo.io` host (GitLab Container Registry) has no dedicated
record and resolves through the `*` wildcard. The Route53 zone and the ACM
certificate pre-exist this Terraform (referenced by ID/ARN in
`terraform/variables.tf`); the records were created imperatively and cut over to
the gateway NLB at deploy time (`deploy/platform/README.md`,
`deploy/istio/README.md`).

Ingress path (live edge):

```
client --HTTPS 443--> Istio gateway NLB (TLS terminated, ACM *.usgov.coderdemo.io)
        --HTTP--> Istio ingress gateway --mTLS--> meshed app Services
```

The single ACM certificate `7f4fc566-8efd-4aa5-b6ba-3b0c9a535d12` covers the
apex and the single-level wildcard `*.usgov.coderdemo.io`, which matches the
Coder dashboard host, the workspace-app wildcard, and the
`auth`/`gitlab`/`grafana`/`kiali`/`registry` hosts (live ACM SANs:
`usgov.coderdemo.io`, `*.usgov.coderdemo.io`). TLS terminates at the NLB; the NLB
forwards plain HTTP to the Istio ingress gateway, which forwards to the meshed
app Services over mTLS (STRICT). The retained ingress-nginx rollback path (NLB to
nginx to pods, all plain HTTP) and the gateway NLB listener detail are covered in
`docs/as-built/20-platform-kubernetes.md` and
`docs/as-built/25-istio-service-mesh.md`.
