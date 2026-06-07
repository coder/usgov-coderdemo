# Plan: per-workload GitOps adoption and non-Kubernetes app state

Status: PLAN ONLY. Nothing changes now. This is a design for a LATER, deliberate
adoption. Every step below is non-disruptive by construction: the live resources
keep running and a GitOps controller adopts them in place.

Scope boundary with the sibling plan: a separate effort designs the GitOps
**control plane** (the Argo CD vs Flux choice, the in-cluster GitLab as the git
source, bootstrap, app-of-apps, and repo layout). This document assumes that
control plane exists and instead designs, per workload, **how each live workload
is adopted into GitOps without disruption**, plus **how to handle the state a
GitOps controller cannot natively reconcile**. Control-plane bootstrap issues are
not duplicated here.

This plan uses Argo CD terminology (Application, sync waves, PreSync/PostSync
hooks, resource tracking) because it is the most common choice and the sibling
plan is leaning that way; the same techniques map to Flux (Kustomization,
HelmRelease, dependsOn, health gates, and Flux Kustomize health checks).

Grounding: `STATUS.md`, `docs/as-built/` (read in full), and the live `deploy/`,
`scripts/`, and `terraform/` trees. Investigation was read-only; the cluster was
not reachable from the planning workspace (no in-boundary AWS CLI), so live diffs
are part of the execution steps, not this plan.

## 1. What we are adopting

Three classes of state, handled differently:

1. **Helm releases** (4): `coder`, `ingress-nginx`,
   `aws-load-balancer-controller`, `external-secrets`. These are CLI-installed
   Helm releases. GitOps adopts them in place.
2. **kubectl-applied manifests**: keycloak (kustomize), gitlab (StatefulSet), the
   2 Coder provisioner Deployments, the ExternalSecrets + ClusterSecretStore,
   workspace RBAC, the `gp3` StorageClass, plus the **new** in-cluster monitoring
   stack. Most are already YAML in git; a few are live-only and must be authored
   into git before adoption.
3. **State a GitOps controller cannot natively reconcile**: Coder application
   config applied through the Coder API, Keycloak realm config applied through the
   Keycloak Admin API, and the AWS substrate (Terraform). Each gets a dedicated
   strategy in section 6.

## 2. Per-workload adoption table

Source chart facts come from `versions.lock.yaml`, `deploy/CONVENTIONS.md`,
`deploy/platform/README.md`, and `docs/as-built/`. "Type" is how the GitOps
controller renders the source (Helm, Kustomize, or plain directory of manifests).

| Workload | Type | Source (chart/version + values, or manifest path) | Adoption method | Diff and landmine notes |
|---|---|---|---|---|
| coder | Helm | chart `coder` 2.34.0 (repo `helm.coder.com/v2`), values `deploy/coder/values.yaml`, ns `coder`, live revs v1..v4 | Argo Application, Helm source, in place | AI Gateway provider env vars are **seed-once** with a drift guard (`docs/as-built/30-coder-control-plane.md`): editing a seeded `CODER_AI_GATEWAY_PROVIDER_*` value or the `coder-ai` secret makes coderd refuse to start. Freeze that env block and manage providers through the DB/API. License, appearance banner, and IdP sync are DB state, not Helm (section 6). SA `coder` carries the Bedrock IRSA annotation; keep it. |
| ingress-nginx | Helm | chart `ingress-nginx` 4.15.1 (repo `kubernetes.github.io/ingress-nginx`), values `deploy/platform/ingress-nginx-values.yaml`, ns `ingress-nginx`, live rev v1 | Argo Application, Helm source, in place | The controller `Service` (type LoadBalancer) **owns the live internet-facing NLB** that all DNS aliases point to. A recreate of that Service re-provisions a new NLB and breaks `dev`/`auth`/`gitlab`/`*` DNS. The benign-diff gate must show **zero** change on the Service `.spec` and its six `aws-load-balancer-*` annotations. Add `ignoreDifferences` for Service `.status` and any LB-controller-mutated fields. |
| aws-load-balancer-controller | Helm | chart `aws-load-balancer-controller` (`eks-charts`), ns `kube-system`, live rev v1, **no values file committed** | Author values, then Argo Application, Helm source, in place | **No committed values file** (installed with CLI flags). Reconstruct desired values from the live release (`helm get values`) before adoption: `clusterName`, `region=us-gov-west-1`, `vpcId`, image from the ECR mirror, and the controller `serviceAccount` + its IRSA role (role name unverified in the as-built ledger; capture it live). Owns CRDs `TargetGroupBinding` and `IngressClassParams`; use ServerSideApply so the large CRDs do not hit the last-applied annotation limit. It actively reconciles the ingress-nginx NLB, so adopt it before or together with ingress-nginx. |
| external-secrets | Helm | chart `external-secrets` 2.6.0 (repo `external-secrets`), values `deploy/platform/external-secrets/values.yaml`, ns `external-secrets`, live components controller+webhook+cert-controller | Argo Application, Helm source, in place | Chart sets `installCRDs: true` and `crds.createClusterSecretStore: true`. The ClusterSecretStore also exists in the manifests file (next row), so pick **one** owner to avoid a fight: let the operator Application own only the operator + CRDs, and let a separate Application own the `ClusterSecretStore` + `ExternalSecret` CRs. Use ServerSideApply for CRDs. |
| ClusterSecretStore + 9 ExternalSecrets | Kustomize/dir | `deploy/platform/external-secrets/secretstore-and-externalsecrets.yaml` | Argo Application, in place | Already declarative and git-friendly. CRs must sync **after** the ESO operator + CRDs are healthy (sync wave). ESO already owns the 9 target Secrets with `creationPolicy: Owner`; adoption is metadata-only. ASM is the source of truth, no secret material in git. |
| keycloak | Kustomize | `deploy/keycloak/` (deployment, service, ingress + `configMapGenerator` of `realm-coder.json`, `disableNameSuffixHash: true`) | Argo Application, Kustomize source, in place | ConfigMap name `keycloak-realm-coder` is stable (hash suffix disabled), so adoption is clean. `start --import-realm` only imports on first boot and skips an existing realm, so groups/mapper/persona users are **not** reconciled by re-apply; that is realm API state (section 6.2). |
| gitlab | dir | `deploy/gitlab/statefulset.yaml`, `service.yaml`, `ingress.yaml`, ServiceAccount | Argo Application, in place | StatefulSet with `volumeClaimTemplates` (3 RWO gp3 PVCs holding the only copy of GitLab + embedded Postgres data). **Never** use `Replace=true` and never delete/recreate: that orphans or destroys the data PVCs. Pod template and `volumeClaimTemplates` selectors are immutable; ServerSideApply with annotation tracking avoids touching them. |
| coder-provisioner-alpha / -bravo | dir | `deploy/coder/provisioners.yaml` (2 Deployments, ns `coder`) | Argo Application, in place | Clean. They consume `coder-provisioner-{alpha,bravo}` secrets (ESO from ASM) and the org-scoped provisioner key. The key is create-once API state (section 6.1). Labels are `app.kubernetes.io/*`, fine under annotation tracking. |
| workspace RBAC | dir | `deploy/platform/workspace-rbac.yaml` (Role + RoleBinding in `coder-workspaces`) | Argo Application, in place | Clean, low risk. The Coder Helm chart also makes a same-named Role in ns `coder`; keep them in separate Applications so the two `coder-workspace-perms` Roles do not collide. |
| gp3 StorageClass | dir | **Live only; not in git** (`kubectl apply` during build) | Author manifest from live, then Argo Application | Reconstruct from `kubectl get sc gp3 -o yaml` (strip runtime fields), keep the `storageclass.kubernetes.io/is-default-class` annotation. Cluster-scoped, key fields immutable; adopt in place, never delete/recreate (would interrupt dynamic provisioning). |
| namespaces | dir | Partly created via Helm `--create-namespace` / ad hoc | Author manifests or use `CreateNamespace=true` | `coder`, `coder-workspaces`, `keycloak`, `gitlab`, `ingress-nginx`, `external-secrets`, plus a new `monitoring`. Author explicit Namespace manifests so ownership is unambiguous and labels (for example `pod-security`) are declarative. |
| monitoring (Prometheus/Grafana) | Helm | **New, greenfield** (`kube-prometheus-stack`), ns `monitoring` | Install **fresh under GitOps**, not an adoption | Being added now. Install it through the GitOps controller from day one so there is no CLI release to adopt later. Needs ECR-mirrored images, gp3-backed PVCs, a Grafana admin secret via ESO/ASM, and (if exposed) a `grafana.usgov.coderdemo.io` ingress under the existing wildcard cert. |

## 3. Helm release adoption: the ownership and label landmines

A Helm CLI install and a GitOps controller track ownership differently, and the
gap is where adoption breaks if done naively.

### 3.1 How the two systems mark ownership

- **Helm CLI** records release state in a Secret
  `sh.helm.release.v1.<name>.<rev>` (labels `owner=helm`), and stamps every
  rendered object with `app.kubernetes.io/managed-by: Helm` plus the annotations
  `meta.helm.sh/release-name` and `meta.helm.sh/release-namespace`.
- **Argo CD** renders a Helm chart with `helm template` (no Tiller, no release
  Secret) and applies the output. By default it tracks ownership with the label
  `app.kubernetes.io/instance`.

### 3.2 The label collision (the main landmine)

Helm charts already set `app.kubernetes.io/instance` to the release name, and
many charts put that label inside **immutable** selectors
(`Deployment.spec.selector`, `StatefulSet.spec.selector`, Service selectors). If
Argo's default label tracking writes a different `app.kubernetes.io/instance`
value, it will try to mutate an immutable selector and the sync fails, or it will
fight the chart on every reconcile.

Mitigation (set once on the GitOps control plane, so noted here only as a
dependency): switch Argo's resource tracking to the annotation method
(`application.resourceTrackingMethod: annotation`, tracking via
`argocd.argoproj.io/tracking-id`). Argo then never touches
`app.kubernetes.io/instance`. This is mandatory before adopting any of the four
Helm releases.

### 3.3 The stale Helm release Secret

After Argo adopts a release via `helm template`, the old
`sh.helm.release.v1.<name>.*` Secrets remain but are inert (`helm list` may still
show the release; it is no longer the source of truth). Keep them until adoption
is verified for rollback, then delete them to avoid two apparent owners.

### 3.4 CRDs

`external-secrets` and `aws-load-balancer-controller` ship CRDs. CRDs are large
and exceed the client-side last-applied-configuration annotation limit, so adopt
them with **ServerSideApply=true**. Decide explicitly whether the chart manages
CRDs (`installCRDs: true` for ESO today) or whether CRDs are split into their own
Application; do not let two Applications both own a CRD.

### 3.5 Verifying a benign diff before the first sync

For each release, before flipping the Application to a synced/managed state:

1. Render exactly what GitOps will apply:
   `helm template <name> <chart> --version <X> -n <ns> -f <values.yaml>`.
2. Server-side dry-run diff against live: `kubectl diff -f rendered.yaml`
   (or `argocd app diff <app>` once the Application exists, unsynced).
3. **Accept only metadata diffs**: the `managed-by` label flipping from `Helm`,
   the added `argocd.argoproj.io/tracking-id` annotation, and removal of the
   `meta.helm.sh/*` annotations.
4. **Block on any spec diff**: zero change to the ingress-nginx Service `.spec`
   and its `aws-load-balancer-*` annotations, to any Deployment/StatefulSet
   selector or pod template, to image tags, to replica counts, to CRD specs, and
   to StorageClass parameters. A spec diff means the committed values do not match
   the live release and must be reconciled in git first.
5. Add `ignoreDifferences` (with `RespectIgnoreDifferences=true`) for fields that
   controllers or webhooks mutate: the ingress-nginx Service `.status`,
   LB-controller-added annotations, and ESO-managed Secret `data`.
6. Sync with **ServerSideApply=true** and **Replace=false**.

### 3.6 Per release

- **coder**: values already match the live release in `deploy/coder/values.yaml`.
  The only behavioral trap is the seed-once AI provider env block plus drift
  guard; freeze it (or remove it after providers are managed in the DB, per
  `docs/as-built/30-coder-control-plane.md`). DB-only state (license, banner, IdP
  sync) is section 6.1.
- **ingress-nginx**: the highest-risk adoption because the Service owns the NLB.
  Gate hard on a zero Service-spec diff.
- **aws-load-balancer-controller**: reconstruct the missing values from the live
  release first (section 2). Adopt before/with ingress-nginx since it reconciles
  that NLB.
- **external-secrets**: split operator+CRDs from the CRs; ServerSideApply for the
  CRDs.

## 4. kubectl-applied manifest adoption

These are plain manifests or kustomize; Argo renders them natively. Adoption is
metadata-only (add the tracking annotation, set the Application to own them).

- **keycloak (kustomize)**: point an Application at `deploy/keycloak/`. Clean
  because the generated realm ConfigMap has a stable name. Realm content drift is
  handled in section 6.2, not by this Application.
- **gitlab (StatefulSet)**: protect the data PVCs. Annotation tracking +
  ServerSideApply, `Replace=false`, and a sync policy that never prunes the PVCs.
  Treat the StatefulSet selector and `volumeClaimTemplates` as immutable.
- **coder provisioner Deployments**: straightforward; depend on the ESO-synced
  provisioner-key secrets existing first (sync wave after ESO).
- **workspace RBAC**: straightforward Role/RoleBinding adoption.
- **gp3 StorageClass and namespaces**: author the missing manifests into git from
  the live objects first (section 2), then adopt. Cluster-scoped, immutable key
  fields, adopt in place.

## 5. ESO and ASM secrets slot into GitOps cleanly

The secrets layer is already the GitOps-friendly part of the stack
(`docs/as-built/85-secrets-management.md`):

- The 9 `ExternalSecret` CRs and the `ClusterSecretStore` are declarative YAML in
  `deploy/platform/external-secrets/secretstore-and-externalsecrets.yaml`, with no
  secret material in git. They commit as-is.
- ASM is the source of truth; ESO authenticates with IRSA (no static keys) and
  owns the 9 target Secrets with `creationPolicy: Owner`. A GitOps controller
  reconciles the CRs; ESO reconciles the actual secret data out of band. Set
  Argo to **ignore the managed Secret `data`** so it never shows spurious drift on
  values it cannot see.
- Ordering: the ESO operator and its CRDs must be healthy before the
  `ClusterSecretStore`/`ExternalSecret` CRs sync, and the target Secrets must
  exist before the apps that mount them. Express this with sync waves: ESO
  operator (wave 0), CRs (wave 1), apps (wave 2+).
- This makes secrets the cleanest workloads to adopt and a good early proof that
  the GitOps plumbing works before touching the NLB-bearing workloads.

## 6. State a GitOps controller cannot natively reconcile

Argo and Flux reconcile Kubernetes API objects. They do not natively reconcile
state that lives behind an application API or in AWS. Three areas, each with a
recommendation.

### 6.1 Coder application config (Coder API + DB state)

In scope: organizations, group/role IdP sync settings, AI providers, templates,
appearance banner, provisioner keys, and the license. None of these are
Kubernetes objects; they live in the Coder database and are set through the Coder
API. Existing idempotent automation already covers most of it:
`scripts/setup-coder-idp-sync.py` (orgs, groups, org/group/role sync, discover
then PATCH), `scripts/set-appearance.sh` (PUT `/api/v2/appearance`).

Options considered:

- **Argo PreSync/PostSync Jobs running the existing scripts** (packaged as a
  container image, hooks gated by sync waves).
- A Terraform/Crossplane Coder provider. A community `coderd` Terraform provider
  exists and can manage some surfaces (orgs, groups, roles, templates, users) but
  does not cover appearance or AI providers, and it adds a second state store and
  a separate apply lifecycle alongside Terraform-for-AWS.
- Keep it as a CI pipeline (for example in-boundary GitLab CI).

Recommendation, **per surface** (one size does not fit all):

| Coder surface | Mechanism | Why / idempotency / secrets |
|---|---|---|
| Orgs + group/role IdP sync | **Argo PostSync Job** running `setup-coder-idp-sync.py` | Already idempotent (discover then PATCH). Runs after coderd is healthy. Admin creds come from an ESO-synced Secret, never git. |
| Appearance banner | **Argo PostSync Job** running `set-appearance.sh` | Idempotent PUT. Premium-gated; depends on the license being present. Creds via ESO. |
| AI providers | **Argo PostSync Job** that reconciles via the Coder API, reading the key from ASM via ESO at runtime | DB is authoritative with a seed-once env drift guard, so the safe path is API-managed and the Helm provider env frozen. The real `sk-ant-...` key stays in ASM, injected at Job runtime, never in git. |
| Provisioner keys | **One-time bootstrap Job** ("create only if absent in ASM"), key written back to ASM for ESO to sync | Not a reconcile loop: re-creating a key rotates it. Guard on absence to stay idempotent. |
| Templates (`coder templates push`) | **CI pipeline** (in-boundary GitLab CI) on the template repo | A versioned build-and-publish action, not a declarative reconcile; fits CI better than a hook. Pin the template version in git. |
| License (JWT) | **Out-of-band runbook**, value in ASM | Runtime JWT applied by CLI/UI; treat as deliberate break-glass, not reconciled. |

Net recommendation: **Argo PostSync (and one bootstrap) Jobs for the reconcilable
DB state, CI for templates, runbook for the license.** This reuses the existing,
proven idempotent scripts; keeps all secrets in ASM/ESO and out of git; and
respects the AI provider drift guard by managing providers through the API rather
than the frozen Helm env. Revisit a `coderd` Terraform provider later only if the
managed surface grows enough to justify a second state store.

Secret-handling implication to call out: the Jobs need a Coder admin session.
Source those admin credentials from an ESO-synced Secret (ASM), scope them
tightly, and prefer a dedicated automation account over the break-glass owner.

### 6.2 Keycloak realm config (Keycloak Admin API)

In scope: the realm import, the group tree, the group-membership protocol mapper
on the `coder` client, and the 8 persona users. Today these are created by the
imperative `scripts/setup-keycloak-hierarchy.py`, and `start --import-realm` only
seeds the realm on first boot (it skips an existing realm), so none of this is
reconciled after day one.

Options considered: keycloak-config-cli as an Argo Job, the Keycloak Operator, or
realm import on boot.

Recommendation: **keycloak-config-cli as an Argo PostSync Job.** It applies a
git-committed, declarative realm config and reconciles the realm to that desired
state on every run (managed import), covering the realm, groups, the mapper, and
users, which boot-time import cannot. It replaces the imperative hierarchy script
with a declarative file. Secrets (the OIDC client secret, persona passwords) are
injected via ESO-synced env and variable substitution, never committed.

- Why not the **Keycloak Operator**: the live Keycloak is a plain Deployment, not
  operator-managed. Adopting the Operator means re-platforming the Keycloak
  instance itself (it manages the workload and realm import CRs), which is a much
  larger change than the realm-config problem we are solving. Its
  `KeycloakRealmImport` is also import-shaped, not full reconcile.
- Why not **realm import on boot**: it only runs on first boot and skips an
  existing realm, so it cannot reconcile drift or apply post-hoc groups, mappers,
  or users. That is exactly the current gap.

Execution notes: mirror the keycloak-config-cli image into ECR; run it as a Job
with admin creds from ESO; commit the realm config with placeholders plus env
substitution. Order it after the keycloak Deployment is healthy.

### 6.3 AWS substrate and the imperative reconciliation backlog (Terraform)

This stays **Terraform**, not GitOps. See `docs/as-built/80-iac-vs-imperative.md`
for the full ledger and backlog. A GitOps controller cannot create the cluster,
node group, IRSA roles, Route53 records, ASM secrets, or EKS envelope encryption;
it runs **inside** the cluster those things create.

Ordering relative to GitOps (the key cross-reference):

1. **Terraform first.** Fold the imperative backlog into Terraform: standard EKS
   (drop Auto Mode), the `mng` node group and `usgov-coderdemo-mngnode` role, the
   four EKS addons and the EBS CSI IRSA role, the `gp3`-backing addon, the Route53
   alias records, the ECR repos, and the IRSA roles GitOps depends on (the ESO
   role `usgov-coderdemo-external-secrets`, the LB controller role, the coder
   Bedrock role). The ESO role was created by CLI, so **import it into Terraform
   state before apply** rather than recreating it (recreating breaks ESO auth).
   Route53 alias records point at the live NLB; adopt them into Terraform without
   delete/recreate so DNS never drops.
2. **Then the GitOps control plane bootstrap** (sibling plan).
3. **Then per-workload adoption** (this plan).

Independent and deferred: **EKS Secrets envelope encryption with the
customer-managed KMS key** (`terraform/secrets-hardening.tf`) is irreversible and
gated on a maintenance window; it is orthogonal to GitOps and should not block
adoption.

This is a cross-reference and ordering dependency, not new GitOps work. It is
tracked as a single issue that points at the existing backlog.

## 7. Ordered adoption sequence

0. **Prerequisites** (not this plan's issues):
   - Sibling: GitOps control plane installed (Argo CD), in-cluster GitLab as the
     git source, app-of-apps, and **annotation resource tracking** set (section
     3.2).
   - Terraform: substrate backlog reconciled, ESO IRSA role imported, ASM secrets
     and IRSA roles and Route53 records present (section 6.3). CMK deferred.
1. **Close the git gaps**: author the `gp3` StorageClass and Namespace manifests
   from live, and reconstruct the `aws-load-balancer-controller` Helm values from
   the live release.
2. **Adopt foundational, no-data, no-LB objects**: namespaces, `gp3`
   StorageClass, workspace RBAC. Lowest risk, proves the plumbing.
3. **Adopt external-secrets**: operator + CRDs (wave 0), then the
   `ClusterSecretStore` + 9 `ExternalSecret` CRs (wave 1). Confirms secret
   plumbing before app adoption.
4. **Adopt aws-load-balancer-controller** (reconstructed values; it reconciles
   the NLB). Zero spec diff required.
5. **Adopt ingress-nginx** (the Service owns the live NLB). Hard gate on a zero
   Service-spec diff.
6. **Adopt keycloak and gitlab** (protect the gitlab data PVCs; never Replace).
7. **Adopt coder + the 2 provisioner Deployments** (freeze the AI provider seed
   env; benign diff only).
8. **Install the monitoring stack fresh under GitOps** (greenfield, not an
   adoption).
9. **Layer the non-Argo app-state controllers**: keycloak-config-cli Job (6.2),
   Coder API PostSync/bootstrap Jobs (6.1), CI for templates, runbook for the
   license.
10. For every step: render, diff, confirm benign, sync with ServerSideApply,
    verify health, then proceed. Keep the prior Helm release Secrets until each
    adoption is verified, then delete them.

## 8. Risks and rollback

- **NLB re-provision** (ingress-nginx / LB controller): the top risk. Mitigate
  with the zero Service-spec diff gate and annotation tracking; rollback is to
  unmanage the Application (leave resources in place) and re-pin DNS if needed.
- **StatefulSet data loss** (gitlab): never Replace or prune PVCs; rollback is to
  re-point the Application and re-attach the existing PVCs.
- **coderd refuses to start** (AI provider drift guard): freeze the seed env;
  manage providers through the API only.
- **Immutable selector mutation** (Helm label collision): fixed by annotation
  tracking before any Helm adoption.
- **Double CRD / ClusterSecretStore ownership**: assign exactly one Application
  per cluster-scoped object.

## 9. Issue map

These adoption work items are filed as GitHub issues on `coder/usgov-coderdemo`
(label `gitops`):

1. Adopt the `coder` Helm release into GitOps in place (chart 2.34.0).
2. Adopt the `ingress-nginx` Helm release into GitOps in place (chart 4.15.1; owns
   the NLB).
3. Adopt the `aws-load-balancer-controller` Helm release into GitOps (reconstruct
   values; CRDs).
4. Adopt the `external-secrets` Helm release plus the ClusterSecretStore and
   ExternalSecrets into GitOps (sync waves).
5. Adopt the kubectl-applied manifests into GitOps (keycloak, gitlab, provisioner
   Deployments, workspace RBAC, `gp3` StorageClass, namespaces).
6. Add the in-cluster monitoring stack (Prometheus/Grafana) GitOps-native.
7. Reconcile Coder API application state via Argo PostSync and bootstrap Jobs.
8. Reconcile the Keycloak realm via keycloak-config-cli as an Argo Job.
9. Cross-reference: Terraform AWS substrate reconcile as a GitOps prerequisite
   (ordering only; see `docs/as-built/80-iac-vs-imperative.md`).

---

*Planning document authored by Coder Agents. Read-only investigation; no cluster,
AWS, Coder, or Keycloak state was changed.*
