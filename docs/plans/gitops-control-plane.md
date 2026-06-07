# Plan: GitOps control plane for the GovCloud Coder demo

Status: PLANNING ONLY. This document is a design proposal for LATER adoption.
Nothing in this plan has been applied. No change has been made to the cluster,
AWS, Coder, Keycloak, GitLab, or git as part of writing it. The investigation
behind it was read-only (`kubectl get`, `helm list`, repo reads). The goal is to
improve maintainability by moving the in-cluster state from imperative CLI steps
to a declarative, auditable GitOps controller, without disrupting the live demo.

Scope of this document: the GitOps **control plane and bootstrap** only (which
controller, where it syncs from, how it is installed and reconciled, how it
integrates with the existing secrets stack, and the non-disruptive adoption
strategy). A sibling plan covers the **per-workload adoption details** and the
non-Argo application state (Coder and Keycloak API configuration, Terraform
reconciliation). This document deliberately stays at the control-plane level and
does not duplicate per-workload adoption steps.

## 1. Current state (confirmed live, read-only)

Captured against EKS cluster `usgov-coderdemo` (k8s 1.36) on 2026-06-07 with
`. ~/.config/usgov-coderdemo/env && export KUBECONFIG=./kubeconfig`.

No GitOps controller exists yet. `kubectl get ns`, `kubectl get crd`, and
`helm list -A` show no Argo or Flux namespaces or CRDs.

In-cluster state is split between Helm releases and `kubectl`-applied manifests:

| Mechanism | Object | Namespace |
|---|---|---|
| Helm | `coder` (rev 4) | `coder` |
| Helm | `ingress-nginx` (rev 1) | `ingress-nginx` |
| Helm | `aws-load-balancer-controller` (rev 1) | `kube-system` |
| Helm | `external-secrets` (rev 1) | `external-secrets` |
| kubectl | Keycloak Deployment/Service/Ingress + realm import | `keycloak` |
| kubectl | GitLab StatefulSet/Service/Ingress (embedded Postgres) | `gitlab` |
| kubectl | 2 Coder provisioner Deployments (`alpha`, `bravo`) | `coder` |
| kubectl | `ClusterSecretStore` + 9 `ExternalSecret` objects | cluster + app ns |
| kubectl | workspace RBAC (`coder-workspace-perms`) | `coder-workspaces` |
| kubectl | `gp3` default StorageClass | cluster |

A monitoring stack is being added to the cluster now; it should be folded into
the same GitOps model once it lands, as a new app under `gitops/apps`.

The AWS substrate (VPC, EKS, node group and IAM, RDS, ECR, IRSA roles, Route53,
ACM, KMS) is Terraform and stays Terraform. Secrets are sourced from AWS Secrets
Manager (ASM) and synced into Kubernetes by the External Secrets Operator (ESO)
via IRSA role `usgov-coderdemo-external-secrets`; the `ClusterSecretStore`
`aws-secretsmanager` reports `Valid`/`Ready`. No secret material is in git.

GovCloud has no ECR pull-through cache, so every image is mirrored into private
ECR by `scripts/mirror-images.sh` from `scripts/images.txt`.

Repo facts: remote `github.com/coder/usgov-coderdemo`, working branch
`feat/app-platform-deploy`. A historical `gitops/` placeholder is referenced in
`docs/repo-layout.md` (labelled "OCP Argo apps") but does not exist on disk; this
plan defines the `gitops/` tree from scratch.

## 2. Goals and non-goals

Goals:

- One declarative source of truth for in-cluster state, reconciled by a
  controller, replacing the ad hoc `helm`/`kubectl` steps.
- Strictly in-boundary: the controller syncs from the in-cluster GitLab at
  `gitlab.usgov.coderdemo.io`, not from github.com. No github.com egress on the
  reconcile path.
- Non-disruptive adoption of the already-running releases and manifests. The
  live demo keeps working throughout; adoption is verified with
  `argocd app diff` before any sync.
- No secrets in git. The controller manages `ExternalSecret` references only;
  ESO continues to own the actual Kubernetes Secrets from ASM.

Non-goals (for this control-plane plan):

- Per-workload adoption mechanics and runtime app config (Coder/Keycloak API,
  license JWT, appearance banner, AI provider DB seed, GitLab OAuth app). Owned
  by the sibling plan.
- Moving the AWS substrate into GitOps. That stays Terraform.
- Enabling auto-sync, self-heal, or prune before the demo. Deferred by design
  (see Section 9).
- Relocating existing manifests. Files stay where they are in `deploy/`; the
  GitOps layer only adds Argo `Application` objects that point at those paths
  (see Section 6).

## 3. Decision: Argo CD vs Flux

**Decision: adopt Argo CD. Commit to it for this environment.** The tradeoff is
recorded below so the choice can be revisited if the end customer standardizes on
a Flux-based reference architecture.

Why Argo CD here:

1. **The UI is a demo asset.** This is a customer-facing demo platform whose
   whole point is to show a governed, in-boundary developer platform. Argo CD
   ships a first-class web UI that visualizes the application tree, sync state,
   and drift. That dashboard is itself a demo artifact: it makes the "everything
   is declarative and reconciled from in-boundary git" story visible on screen.
   Flux is intentionally UI-less in its core (third-party UIs exist but are a
   separate install and less prominent).
2. **It reuses the existing Keycloak SSO.** Argo CD can authenticate its UI and
   API against the Keycloak realm `coder` over OIDC, reinforcing the same
   in-boundary identity story already used by Coder. One more relying party on
   the existing IdP, no new auth path.
3. **App-of-apps maps cleanly onto incremental, non-disruptive adoption.** Argo
   CD's `Application` and `AppProject` model, plus `argocd app diff`, lets us
   adopt one existing release or manifest set at a time and prove the diff is
   benign before syncing. This matches the careful adoption posture this live
   environment requires.
4. **Broad adoption and operator familiarity** lower the support burden for a
   demo that platform engineers will run and extend.

The case for Flux (the recorded tradeoff):

- **DoD Platform One Big Bang uses Flux.** If this demo needs to align with a
  customer's Big Bang reference architecture, Flux would be the native choice and
  would reduce friction with that ecosystem. This is the single strongest reason
  to revisit the decision, and it is a real one for a GovCloud, DoD-adjacent
  audience.
- Flux has a **smaller footprint** (fewer components, so fewer images to mirror
  into ECR) and a GitOps-native, Kustomize-first multi-tenancy model.

Resolution: pick Argo CD now for the demo's UI value, SSO reuse, and adoption
ergonomics. If Big Bang alignment becomes a hard requirement for a specific
engagement, treat that as the trigger to re-evaluate Flux. Record this as a
reversible decision, not a permanent platform standard.

Version note: pin to a currently supported Argo CD release. As of late May 2026
the supported minor lines are v3.4, v3.3, and v3.2; v3.1 reached end of life on
2026-05-06. Plan on the latest v3.4.x patch at adoption time and confirm the
exact patch then.

## 4. Target architecture

```
                IN-BOUNDARY (GovCloud, no github.com on the reconcile path)
  +-------------------------------------------------------------------------+
  |                                                                         |
  |  operator / in-boundary CI                                              |
  |     |  git push (mirror from github.com origin, done off the           |
  |     |  reconcile path)                                                  |
  |     v                                                                   |
  |  In-cluster GitLab  (gitlab.usgov.coderdemo.io / gitlab.gitlab.svc)     |
  |  project: platform/usgov-coderdemo  (authoritative for GitOps)          |
  |     |   ^                                                               |
  |     |   |  webhook (push) -> /api/webhook ; poll fallback (~3m)         |
  |     |   |  read-only deploy token (read_repository)                     |
  |     v   |                                                               |
  |  +--------------------- ns: argocd ---------------------------------+   |
  |  |  Argo CD                                                         |   |
  |  |  application-controller / repo-server / server(UI+API) /         |   |
  |  |  applicationset-controller / redis / dex(optional)               |   |
  |  |  images: ECR mirror (quay/argoproj/argocd, redis, dex)           |   |
  |  |  UI/API auth: Keycloak realm `coder` (OIDC)                       |   |
  |  +-----------------------------+------------------------------------+   |
  |        | renders + applies (helm template / kustomize / manifests)  |   |
  |        v                                                             |   |
  |  app-of-apps root  ->  AppProjects  ->  child Applications           |   |
  |        |                                                             |   |
  |        +--> platform: ingress-nginx, aws-load-balancer-controller,   |   |
  |        |             external-secrets, gp3 StorageClass, ws RBAC     |   |
  |        +--> coder: coder (Helm) + provisioners                       |   |
  |        +--> keycloak (manifests)                                     |   |
  |        +--> gitlab (manifests)                                       |   |
  |        +--> secrets-config: ClusterSecretStore + ExternalSecrets     |   |
  |        +--> argocd (self-management)                                 |   |
  |                                                                      |   |
  |  ExternalSecrets (in git, references only)                           |   |
  |        |  reconciled by Argo CD                                      |   |
  |        v                                                             |   |
  |  ESO (IRSA: usgov-coderdemo-external-secrets) --> reads ASM          |   |
  |        |  writes/owns                                                |   |
  |        v                                                             |   |
  |  Kubernetes Secrets (NOT in git, NOT pruned by Argo)                 |   |
  |                                                                      |   |
  +----------------------------------------------------------------------+   |
  |                                                                          |
  |  AWS Secrets Manager (usgov-coderdemo/*)  <-- source of truth, secrets   |
  |  ECR (image mirror, no pull-through)                                     |
  |  Terraform substrate: VPC, EKS, RDS, IRSA, Route53, ACM, KMS            |
  +--------------------------------------------------------------------------+
```

Key properties: the reconcile loop (GitLab to Argo CD to cluster) is entirely
in-cluster. The only out-of-boundary touch is the operator mirroring the repo
from github.com into GitLab, and that happens off the reconcile path. Secret
material never enters git; Argo manages references, ESO owns the Secrets.

## 5. In-boundary source: the in-cluster GitLab

The canonical repo lives at `github.com/coder/usgov-coderdemo`, which is out of
boundary. The architecture goal is strictly in-boundary, so Argo CD must sync
from the in-cluster GitLab, not from github.com.

### 5.1 Authoritative source and mirroring direction

- Create a GitLab project, for example `platform/usgov-coderdemo`, on the
  in-cluster GitLab. This project becomes the **authoritative source for what
  Argo CD reconciles**.
- github.com remains the public collaboration mirror. The mirror direction is
  **github.com to GitLab** (push into GitLab), performed by an operator or an
  in-boundary CI runner that has github read access. Do not use GitLab's "pull
  mirror" feature pointed at github.com, because that would put github.com egress
  back on the platform's critical path, defeating the boundary goal.
- Document the push step as a release action (for example a `git push gitlab`
  to a second remote) so the in-boundary source is updated deliberately and the
  reconcile loop never depends on github.com reachability.

### 5.2 Repo URL the controller uses

Two valid options; pick one and be consistent with the deploy token host:

- **In-cluster Service URL (recommended):**
  `http://gitlab.gitlab.svc.cluster.local/platform/usgov-coderdemo.git`. Keeps
  all reconcile traffic inside the cluster, avoids the NLB hairpin, and needs no
  TLS trust configuration (GitLab serves plain HTTP on the Service port behind
  the bundled NGINX). Simplest and most in-boundary.
- **Public hostname over the NLB hairpin:**
  `https://gitlab.usgov.coderdemo.io/platform/usgov-coderdemo.git`. Uses the
  valid ACM TLS path but adds an NLB round trip; only choose this if you want
  Argo to validate the public certificate.

Recommendation: use the in-cluster Service URL for the Argo repo definition.

### 5.3 Repository credentials (deploy token)

- Mint a **GitLab project deploy token** scoped to `read_repository` on
  `platform/usgov-coderdemo` (read-only; the controller never pushes).
- Store the deploy token in ASM (for example `usgov-coderdemo/argocd/gitlab-repo`
  with keys `username` and `password`), consistent with the existing
  ASM-plus-ESO pattern. An `ExternalSecret` then materializes a Kubernetes Secret
  in the `argocd` namespace carrying the Argo repository label
  `argocd.argoproj.io/secret-type: repository` with `url`, `username`, and
  `password`. This keeps the credential out of git and rotation in ASM.
- Bootstrap ordering matters: ESO and the repo-credential `ExternalSecret` must
  exist before Argo CD first tries to pull from GitLab. ESO is already installed,
  so the only new prerequisite is the repo-cred `ExternalSecret`.

### 5.4 Change delivery: webhook plus poll

- Configure a GitLab **project webhook** to Argo CD's `/api/webhook` endpoint for
  push-triggered sync (low latency for demos). Protect it with a webhook secret,
  also delivered via ASM/ESO.
- Keep Argo's **polling reconcile** as the fallback (default around 3 minutes) so
  reconciliation still happens if a webhook is missed. For a demo, polling alone
  is acceptable; the webhook is a nice-to-have for snappy syncs.

## 6. Repo layout for GitOps (no files moved yet)

Add a `gitops/` tree that contains only Argo CD objects (the controller install
and the `Application`/`AppProject`/`ApplicationSet` definitions). The existing
manifests and Helm values stay exactly where they are under `deploy/`; each
`Application` points its `source.path` at the current `deploy/...` location. This
is the "adopt in place, do not relocate" principle, so the diff between git and
the live cluster stays minimal during adoption.

Proposed layout:

```
gitops/
  bootstrap/
    argocd/                       # Argo CD install (Helm values for the chart,
                                  # image repos overridden to the ECR mirror)
    root-app.yaml                 # app-of-apps root Application
    projects/
      platform.yaml               # AppProject: platform infra
      apps.yaml                   # AppProject: coder/keycloak/gitlab
      argocd.yaml                 # AppProject: argocd self-management
  apps/
    platform/
      ingress-nginx.yaml          # Application -> deploy/platform ingress-nginx values
      aws-load-balancer-controller.yaml
      external-secrets.yaml       # Application -> ESO Helm release
      storageclass-gp3.yaml       # Application -> gp3 StorageClass manifest
      workspace-rbac.yaml         # Application -> deploy/platform/workspace-rbac.yaml
    secrets/
      secretstore-externalsecrets.yaml  # Application -> deploy/platform/external-secrets
    coder/
      coder.yaml                  # Application -> deploy/coder (Helm: chart + values.yaml)
      provisioners.yaml           # Application -> deploy/coder/provisioners.yaml
    keycloak/
      keycloak.yaml               # Application -> deploy/keycloak (kustomize)
    gitlab/
      gitlab.yaml                 # Application -> deploy/gitlab/*.yaml
```

Pattern choice:

- **App-of-apps (recommended to start).** A single root `Application`
  (`gitops/bootstrap/root-app.yaml`) enumerates the child `Application` objects
  under `gitops/apps`. Explicit, easy to reason about, easy to adopt one child at
  a time, and easy to keep some children on manual sync while others advance.
- **ApplicationSet (alternative, for later scale).** A git-directory generator
  over `gitops/apps/*` removes the per-app boilerplate. Good once the set of apps
  stabilizes and you want uniform policy. Note it as the evolution path, not the
  starting point, because per-app policy variation is exactly what we want during
  adoption.

`AppProject` boundaries: define at least three projects so each app set is
restricted to its source repo (the one GitLab project) and its destination
namespaces. Least privilege at the project layer is what makes a broad
controller safe (see Section 8).

How Helm releases are represented: each existing Helm release becomes an
`Application` whose `source` is the chart (mirrored chart or repo) with
`helm.valueFiles` pointing at the committed `deploy/<app>/values.yaml`. Argo
renders the chart with `helm template` and applies the result; it does not call
`helm install`. The implications of that are covered in Section 9.

## 7. Bootstrap: installing and self-reconciling the controller

### 7.1 Image mirroring to ECR (no pull-through in GovCloud)

Add the Argo CD component images to `scripts/images.txt` and mirror them with the
existing `scripts/mirror-images.sh` (crane to private ECR). Argo CD is a handful
of images:

- `quay.io/argoproj/argocd:<v3.4.x>` (one image backs the application-controller,
  repo-server, server/UI, applicationset-controller, and notifications).
- A Redis image used by the chart (commonly `docker.io/library/redis:<tag>`;
  confirm the exact repo/tag the chosen chart version pins).
- `ghcr.io/dexidp/dex:<tag>` only if Dex is used for SSO bundling. If Argo CD is
  pointed straight at Keycloak OIDC, Dex can be omitted, removing one image.

Override the chart's image repositories to the ECR mirror paths
(`<registry>/quay/argoproj/argocd`, `<registry>/docker-hub/library/redis`,
`<registry>/ghcr/dexidp/dex`) following the existing mirror path convention.
These ECR pulls work with the node role's `AmazonEC2ContainerRegistryReadOnly`,
so no new IRSA is required just to pull Argo's images.

### 7.2 Install method and self-management

- **First install is imperative**, like everything else in this build: install
  Argo CD via its Helm chart into namespace `argocd`, with images pointed at the
  ECR mirror. Use server-side apply for the install. The official Argo CD install
  guidance calls for `--server-side --force-conflicts` because the CRDs exceed
  the client-side apply size limit; the same constraint applies when Argo manages
  CRD-bearing charts (see Section 9).
- **Then Argo CD manages Argo CD.** Add an `argocd` `Application` (under the
  `argocd` AppProject) whose source is `gitops/bootstrap/argocd`. After the
  initial bootstrap, all future Argo CD config and upgrades flow through git like
  any other app. This is the standard self-management pattern and closes the loop
  so the controller is not itself a snowflake.
- The app-of-apps `root-app.yaml` is applied once by hand during bootstrap;
  thereafter it reconciles itself and its children from git.

### 7.3 RBAC and IRSA

- **Controller RBAC:** the application-controller needs permission to reconcile
  across the managed namespaces (`coder`, `coder-workspaces`, `keycloak`,
  `gitlab`, `ingress-nginx`, `external-secrets`, `kube-system` for the LB
  controller, and cluster-scoped objects like the StorageClass and
  ClusterSecretStore). The Argo install ships a ClusterRole for this. Constrain
  the blast radius at the `AppProject` layer instead of widening or narrowing the
  ClusterRole: each project allowlists only its destination namespaces and the
  single GitLab source repo.
- **UI/API RBAC:** wire Argo CD's UI and API to Keycloak OIDC (realm `coder`) and
  map a platform-admin group to the Argo `admin` role via `policy.csv`; everyone
  else defaults to read-only. This reuses the in-boundary IdP and avoids a
  separate Argo local-admin password as the standing credential.
- **IRSA:** Argo CD core needs no AWS credentials to reconcile manifests, so no
  new IRSA role is required for the controller itself. The only AWS dependency is
  pulling images from ECR, already covered by the node role. (If a future
  ApplicationSet cloud generator or an image updater against ECR is added, that
  would need its own IRSA role; out of scope here.)

## 8. Secrets and ESO integration

The hard rule is unchanged: no secret material in git. GitOps and the existing
ESO/ASM stack divide responsibility cleanly:

- **Argo CD manages the references.** The `ClusterSecretStore` and the nine
  `ExternalSecret` objects (`deploy/platform/external-secrets/...`) contain only
  pointers to ASM, no secret values, so they are safe to keep in git and
  reconcile with Argo.
- **ESO owns the actual Kubernetes Secrets.** ESO writes them with
  `creationPolicy: Owner` from ASM via IRSA. Those Secrets are not in git and
  must not be managed or pruned by Argo.
- **Keep Argo and ESO from fighting over Secrets.** Because the Kubernetes
  Secrets are not rendered from git, Argo will not track them under normal
  operation. The risk is namespace-level pruning or orphaned-resource handling
  deleting an ESO-owned Secret. Mitigations: keep `prune: false` during adoption
  (Section 9); set `AppProject` `orphanedResources` to `warn`, never delete; and
  if needed add `Secret` to Argo's resource exclusions for the managed
  namespaces. Argo 3.x already ships sensible default `resource.exclusions`;
  extend them rather than reduce them.
- **The Argo repo credential is itself a secret**, handled the same in-boundary
  way: deploy token in ASM, surfaced into the `argocd` namespace by an
  `ExternalSecret` carrying the Argo repository label (Section 5.3). This keeps
  the one credential Argo needs out of git and rotatable in ASM, and it means the
  whole platform, including the GitOps controller's own inputs, follows one
  secrets pattern.

## 9. Non-disruptive adoption strategy (the careful part)

This is a live environment. Adoption must not restart or revert running
workloads. The strategy is to install the controller, point Applications at the
existing state with all automation off, prove the diff is benign, and only then
consider enabling automation, after the demo.

### 9.1 Sync policy phases

1. **Phase 0: install only.** Argo CD running; no child Application syncing yet
   (Applications created with automated sync disabled, or not created at all).
2. **Phase 1: adopt with everything off.** For each existing release or manifest
   set, create an `Application` pointing at the GitLab source with:
   - manual sync (no `automated`),
   - `prune: false`,
   - `selfHeal: false`.
   The app will report `OutOfSync` or `Synced` but will not change anything.
3. **Phase 2: verify the diff is benign.** Run `argocd app diff <app>` and
   confirm the only differences are metadata Argo adds (its tracking
   annotation/labels), not spec changes. If the diff shows real spec drift,
   reconcile the git source to match live before going further (do not sync to
   "fix" live).
4. **Phase 3: adopt in place.** Once the diff is benign, let Argo take ownership
   (a manual sync that only adds tracking metadata). Still no prune, no self-heal,
   no auto-sync.
5. **Phase 4 (after the demo): enable automation per app.** Turn on `automated`,
   then `selfHeal`, then `prune`, one app at a time, lowest-risk first, watching
   each. Auto-sync is deliberately deferred until after the demo.

### 9.2 Order of adoption (lowest risk first)

1. Leaf, stateless manifests with no Helm bookkeeping: `gp3` StorageClass,
   workspace RBAC, and the `ClusterSecretStore`/`ExternalSecret` set.
2. The plain `kubectl`-applied app manifests: Keycloak, GitLab, the Coder
   provisioner Deployments. These were applied with `kubectl`, so there is no
   competing Helm release to reconcile.
3. The Helm releases last: `external-secrets`, `aws-load-balancer-controller`,
   `ingress-nginx`, then `coder`. These carry the ownership and values landmines
   below, so they are adopted only after the no-Helm items prove the workflow.

### 9.3 Landmines when adopting CLI-installed Helm releases

These are the specific traps and how to defuse each:

- **Ownership metadata (Helm vs Argo).** Argo does not use Helm to install; it
  runs `helm template` and applies the output, taking ownership via its tracking
  annotation/label. After adoption, the old Helm release Secret
  (`sh.helm.release.v1...`) is orphaned bookkeeping: both Helm and Argo believe
  they own the objects. Plan: let Argo become the owner, verify the app is
  `Healthy`/`Synced`, then clean up the stale Helm release record (for example
  `helm uninstall --keep-resources`, or simply leave the orphaned release Secret
  and stop using `helm upgrade`). Decide and document which tool is authoritative
  per release; do not run `helm upgrade` against an Argo-managed release.
- **Values drift.** `coder` is at Helm revision 4. Live values set across those
  upgrades may not all be captured in `deploy/coder/values.yaml`. Before
  adoption, capture live values (`helm get values coder -n coder`) and reconcile
  them into the committed values file so the rendered manifest matches live.
  Otherwise `argocd app diff` shows spurious changes and a sync would revert real
  live configuration. Repeat for each Helm release.
- **CRDs.** ESO and the AWS load balancer controller install CRDs. Argo CD has
  known CRD-size handling caveats: large CRDs exceed the client-side apply
  annotation limit, which is why the official install itself requires
  `--server-side --force-conflicts`. Use `ServerSideApply=true` for CRD-bearing
  apps, keep CRDs out of prune, and be deliberate about `Replace`. ESO CRDs in
  particular are large; server-side apply is the safe default.
- **Resource tracking method.** Prefer annotation-based resource tracking so Argo
  does not mutate `spec` or label selectors on adoption. Label-based tracking can
  touch immutable selector fields and trigger churn; annotation tracking avoids
  that. Confirm the controller is set to annotation tracking before adopting.
- **`helm template` vs `helm install` semantics.** Chart hooks, `lookup`
  functions, and `.Release.IsInstall` can render differently under
  `helm template`. Verify the rendered output of each chart matches what is live
  before syncing, especially for charts that branch on install-vs-upgrade.

## 10. Scope: what GitOps manages vs what stays Terraform or scripts

| Layer | Owner after this plan |
|---|---|
| In-cluster Helm releases (coder, ingress-nginx, aws-load-balancer-controller, external-secrets) | GitOps (Argo CD) |
| In-cluster manifests (keycloak, gitlab, provisioners, workspace RBAC, gp3 SC, ClusterSecretStore + ExternalSecrets) | GitOps (Argo CD) |
| The new monitoring stack (once it lands) | GitOps (Argo CD), as a new `gitops/apps` app |
| Argo CD itself | GitOps (self-managed app-of-apps) |
| AWS substrate (VPC, EKS cluster, node group + IAM, RDS, ECR repos, IRSA roles, Route53, ACM, KMS) | Terraform |
| Image mirroring into ECR (crane) | Script (`scripts/mirror-images.sh`), a pipeline step; image content is not Argo's job |
| DB roles/schemas (`coder`, `keycloak`) | Script / one-time job (or fold into Terraform later) |
| Runtime app config: Coder license JWT, appearance banner, AI provider DB seed, GitLab OAuth app, Keycloak realm runtime config, IdP sync, Coder template push | Out-of-band / runtime (sibling plan), NOT GitOps |
| Kubernetes Secrets material | ESO from ASM (referenced, never stored, by GitOps) |

Boundary with the sibling plan: this document stops at the control plane and
bootstrap. The per-workload adoption details (how each Coder/Keycloak/GitLab
workload is cut over, and how the non-Argo application state and Terraform
reconciliation are handled) are owned by the sibling plan and are not duplicated
here.

## 11. Risks and open questions

- **Mirror discipline.** The in-boundary GitLab is only as current as the last
  github-to-GitLab push. A missed push means Argo reconciles stale desired state.
  Mitigation: make the push a required release step or an in-boundary CI job.
- **Single GitLab as a dependency.** GitLab uses embedded Postgres on one PVC
  with no managed backup. If GitLab is down, Argo cannot fetch new desired state
  (already-synced state keeps running). Acceptable for a demo; note it.
- **Coder values reconciliation effort.** Capturing four revisions of live Coder
  values into the committed values file is the most error-prone adoption task and
  should get the most diff scrutiny.
- **Open question:** confirm the exact Redis image/tag the chosen Argo CD chart
  version pins, and whether Dex is needed or Keycloak OIDC is wired directly
  (affects the image mirror list).
- **Open question:** confirm whether the monitoring stack should be adopted as
  part of the first GitOps cut or after the four Helm releases, given it is being
  installed imperatively right now.

## 12. Implementation roadmap (maps to the GitHub issues)

1. Choose and install the Argo CD control plane (namespace, Helm, ECR images,
   self-managed app-of-apps root).
2. Mirror Argo CD component images into ECR (`scripts/images.txt`).
3. Stand up the in-cluster GitLab project, push the repo into it, and configure
   Argo repo credentials (deploy token via ASM/ESO) plus webhook and poll.
4. Scaffold the `gitops/` app-of-apps and `AppProject` layout, with Applications
   referencing the existing `deploy/` paths (no files moved).
5. Argo CD bootstrap RBAC, Keycloak SSO for the UI, and least-privilege
   AppProjects.
6. Secrets/ESO integration guardrails (no secrets in git; prune and
   orphaned-resource protections; server-side apply for CRDs).
7. Non-disruptive adoption runbook with `argocd app diff` verification (values
   reconcile, ownership and CRD landmines, staged ordering, defer auto-sync).

These map one-to-one to the `gitops`-labelled GitHub issues filed alongside this
plan.
