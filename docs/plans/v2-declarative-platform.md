# Plan: v2.0 fully declarative platform (usgov-coderdemo)

Status: PLANNING ONLY. This document is a design proposal for LATER adoption.
Nothing here has been applied to the live cluster, AWS, Coder, Keycloak,
GitLab, or git as part of writing it. The investigation behind it was
read-only (repo reads and `grep`). It does not run Terraform, `kubectl`,
`helm`, the AWS CLI, or any application API write.

## 1. Purpose: v1.0 MVP vs v2.0 target

The live deployment is **v1.0 MVP**. It works for the Thursday 2026-06-11
demo, but it is not maintainable. It grew overnight across four uncoordinated
control planes with no reconciler, so the live state and git have drifted, and
several domains have more than one writer. The as-built reality is recorded in
[`../as-built/CONTROL_PLANE_OWNERSHIP.md`](../as-built/CONTROL_PLANE_OWNERSHIP.md)
and [`../as-built/80-iac-vs-imperative.md`](../as-built/80-iac-vs-imperative.md).

**v2.0** is the convergence target: every domain has exactly one authoritative
writer, every change is auditable in git, and a fresh demo enclave can be stood
up and torn down declaratively by any member of the team. v2.0 does not add new
product features. It removes the imperative steps and the parallel sources of
truth that make v1.0 a snowflake.

This plan is the umbrella that sequences and connects the existing, narrower
plans. It deliberately does not duplicate them; it references them:

- GitOps controller and bootstrap:
  [`gitops-control-plane.md`](gitops-control-plane.md).
- Per-workload GitOps adoption and non-Kubernetes app state:
  [`gitops-adoption.md`](gitops-adoption.md).
- AWS-native observability and audit:
  [`observability-aws-native.md`](observability-aws-native.md).
- Istio service mesh adoption: [`istio-implementation.md`](istio-implementation.md).

The drift gate that proves convergence is the existing read-only checker
[`../../scripts/verify-drift.py`](../../scripts/verify-drift.py).

## 2. Current-state recap and the worst drift

For the full domain map, see
[`../as-built/CONTROL_PLANE_OWNERSHIP.md`](../as-built/CONTROL_PLANE_OWNERSHIP.md).
v1.0 spans four uncoordinated control planes:

1. **Terraform** (`terraform/`, S3 backend) owns the VPC, IRSA, RDS, and the
   ASM secret containers. It is clean for those primitives.
2. **Hand-applied Helm values and raw manifests** under `deploy/*`, applied by
   `helm` and `kubectl` with no reconciler.
3. **Imperative `python`/`sh` scripts** in `scripts/` that seed API-owned
   objects straight into app databases (Coder templates, providers, users,
   roles; GitLab projects, CI variables, tokens, webhooks; Keycloak realm,
   clients, MFA).
4. **Secrets split-brain**: AWS Secrets Manager (`usgov-coderdemo/*`) is the
   intended source of truth synced by ESO into Kubernetes, but
   `~/.config/usgov-coderdemo/generated-secrets.env` is an un-synced parallel
   source of truth used by setup scripts.

The worst drift to fix first, in priority order:

- **EKS compute is declared but diverged.** `terraform/eks.tf` declares EKS
  Auto Mode (`compute_config.enabled = true`, node pools `general-purpose` and
  `system`, managed block storage and load balancing), but the live cluster
  runs standard EKS with a CLI-created managed node group `mng` on a CLI-created
  node role. Terraform would try to re-enable Auto Mode on the next apply, which
  is why no one runs apply. This is the single most dangerous divergence.
- **Node-group capacity is CLI-only.** Desired size is changed with
  `aws eks update-nodegroup`, invisible to git.
- **All Route53 records are CLI-only.** Every host (`dev`, `auth`, `gitlab`,
  `grafana`, `kiali`, wildcard) was pointed at the NLB with `aws route53`, and
  re-pointed during the Istio cutover, with nothing in Terraform.
- **The Coder to Keycloak OIDC client secret exists in four uncoordinated
  copies with no reconciler.** Script-driven OIDC setup regenerates Keycloak
  client secrets on each run and pushes to ASM, but relying parties only pick up
  the new value after a pod restart and ESO refresh.

## 3. Target architecture: one authoritative writer per domain

| Domain | v2.0 source of truth | Writer / mechanism | Consumers | Change from v1.0 |
|---|---|---|---|---|
| AWS network, IAM, IRSA, RDS, ECR repos | Terraform (`terraform/`, S3 backend) | `terraform apply` (in CI) | everything | unchanged, already clean |
| EKS cluster + node group + node capacity | Terraform | `terraform apply` after import; reconcile or remove the Auto Mode declaration | k8s control plane | was CLI + drifted Auto Mode declaration |
| Route53 DNS records | Terraform (`aws_route53_record`) | `terraform apply` after import | clients, ingress | was `aws route53` CLI only |
| EKS Secrets envelope encryption (KMS/etcd) | Terraform | `terraform apply` (explicit maintenance decision) | etcd | not enabled; staged in `secrets-hardening.tf` |
| Secret VALUES | AWS Secrets Manager `usgov-coderdemo/*` | bootstrap + reconcilers write to ASM; values never in tfstate or git | ESO, apps | `generated-secrets.env` demoted to derived cache |
| Secret CONTAINERS + IAM | Terraform | `terraform apply` (containers and IRSA only, no raw values) | ASM, ESO | unchanged by design |
| k8s Secret objects | ASM via ESO | `deploy/platform/external-secrets/*` reconciled by Argo CD | app pods | ESO already owns; Argo owns the references |
| In-cluster Helm releases + raw manifests (`deploy/*`) | git, reconciled by Argo CD | Argo CD app-of-apps, auto-sync OFF then ON per domain | cluster | was hand `helm`/`kubectl`, no reconciler |
| Argo CD itself | git | Argo CD self-managed app-of-apps | cluster | new in v2.0 |
| Coder API config (templates, users, roles, providers, runtime settings) | git desired-state | Terraform `coderd` provider where mature, else thin idempotent verify/plan/apply reconciler reading ASM | Coder DB | was imperative scripts seeding the DB |
| GitLab API config (projects, CI vars, tokens, webhooks) | git desired-state | Terraform `gitlab` provider where mature, else thin reconciler reading ASM, tokens written back to ASM | GitLab DB | was `gitlab-rails` + API scripts |
| Keycloak realm + clients + MFA | git desired-state JSON | `keycloak-config-cli` (or Terraform `keycloak` provider) reading ASM, generated client secrets written back to ASM | Keycloak DB | was realm import + script deltas, not re-exported |
| Drift detection | n/a (read-only) | `scripts/verify-drift.py` as a CI gate | humans, CI | was run by hand |

Invariants that hold across every domain:

- Raw secret values stay out of git and out of tfstate. Terraform manages secret
  containers and IAM only, matching `terraform/secrets-hardening.tf`.
- A reconciler reads secret values only from ASM, and writes any token it
  generates back to ASM, never to a local file as canonical.
- `generated-secrets.env` becomes a derived, gitignored cache rehydrated from
  ASM. It is never the input that seeds a live system.
- No `kubectl set env`, `coder ... edit`, or `gitlab-rails` as a silent writer.
  Any break-glass use is recorded in git and docs immediately.

## 4. Sequenced migration plan

The order is chosen so each phase leaves the live demo working and produces a
clean drift report before the next phase begins. Phases 1 through 4 each end at
a `verify-drift.py` checkpoint.

### Phase 0: guardrails before any change

- Wire `scripts/verify-drift.py --json` into CI as a non-blocking report first,
  then promote it to a blocking gate at the end of Phase 4 (see Section 4,
  Phase 4, and the backlog).
- Extend the checker with the two detectors v2.0 needs: a placeholder-secret
  detector across all synced secrets (partially present today as the Anthropic
  shape check) and a live-vs-git config comparison for the API-owned domains.
- Capture a baseline: record current live values for each Helm release
  (`helm get values`), the live node group config, and the live Route53 record
  set, into git as the desired-state starting point. This is read-only capture,
  not apply.

### Phase 1: Terraform owns all infrastructure

One domain at a time, import the live resource, confirm a no-op plan, then
manage it. Terraform import is required for every resource below because each
exists live but is absent from or diverged in state.

1. **Resolve the EKS Auto Mode declaration.** Decide between two options and
   record it in Section 6: either remove the Auto Mode `compute_config` and
   model the standard cluster plus the `mng` node group in Terraform, or invest
   in making Auto Mode work (blocked today by the GovCloud
   `AWSServiceRoleForAmazonEKS` SLR lacking `iam:AddRoleToInstanceProfile` and
   `iam:TagInstanceProfile`). The pragmatic v2.0 choice is to drop Auto Mode and
   manage the standard cluster and node group, because that matches live.
2. **Import the node group and its IAM role.**
   `terraform import` the `mng` node group and `usgov-coderdemo-mngnode` role,
   then move node capacity (desired/min/max) into Terraform so
   `aws eks update-nodegroup` is retired.
3. **Import Route53 records.** Model every host as `aws_route53_record` aliases
   to the active ingress NLB and import them, retiring the `aws route53` CLI
   path. The hosted zone `Z06701704WFETYIRU5C8` and the ACM certificate stay as
   passed-in inputs.
4. **Import the ESO IAM role** following the note already in
   `terraform/secrets-hardening.tf`
   (`terraform import aws_iam_role.external_secrets usgov-coderdemo-external-secrets`).
5. Leave the KMS/etcd envelope-encryption resources staged but not enabled;
   enabling is irreversible and is an explicit maintenance decision (Section 6).

Checkpoint: `terraform plan` reports no changes for the imported resources, and
`verify-drift.py` shows no infra regressions.

### Phase 2: AWS Secrets Manager as the only value source

1. Inventory every value currently read from `generated-secrets.env` and
   confirm each has an ASM home (use `scripts/migrate-secrets-to-asm.py` for any
   gap). ASM is authoritative for values; Terraform owns only containers and IAM.
2. Demote `generated-secrets.env` to a derived cache: add a small step that
   regenerates it from ASM for local convenience, and stop every setup script
   from treating it as the canonical input. Keep it gitignored.
3. Close the four-copy Coder to Keycloak OIDC client-secret gap by making one
   reconciler the single writer: it reads or rotates the secret in Keycloak,
   writes the one value to ASM, and lets ESO mirror it into the relying-party
   namespaces, then triggers the dependent pod restarts. No other copy is
   authoritative.
4. Turn on the placeholder-secret detector in `verify-drift.py` as a FAIL
   condition so a placeholder can never satisfy an "exists" check.

Checkpoint: `verify-drift.py` drift and placeholder groups are all PASS, and no
live system is seeded from `generated-secrets.env`.

### Phase 3: Argo CD reconciles deploy/*

Follow [`gitops-control-plane.md`](gitops-control-plane.md) for the controller
install and in-boundary GitLab source, and
[`gitops-adoption.md`](gitops-adoption.md) for the per-workload mechanics. The
v2.0-specific posture:

- Install Argo CD with **auto-sync OFF and `prune: false`**, adopt in place
  (no files moved), and enable sync for a domain only after `argocd app diff`
  is benign.
- Adoption order, lowest risk first (from the adoption plan): leaf manifests
  (gp3 StorageClass, workspace RBAC, ClusterSecretStore and ExternalSecrets),
  then `kubectl`-applied app manifests (Keycloak, GitLab, Coder provisioners),
  then the Helm releases (`external-secrets`,
  `aws-load-balancer-controller`, `ingress-nginx`, then `coder`), then Argo CD
  self-management.
- ESO keeps owning Kubernetes Secrets; Argo manages only the references and must
  never prune ESO-owned Secrets.

Checkpoint: every `deploy/*` app is `Synced` and `Healthy` under Argo with a
benign diff, before auto-sync is enabled per domain.

### Phase 4: API-owned config becomes declarative

Replace the imperative seeding scripts with either a Terraform provider (where
mature) or a thin idempotent `verify | plan | apply` reconciler driven by a git
desired-state file, reading secret values from ASM and writing generated tokens
back to ASM. Per-app decision:

- **Coder.** Use the Terraform `coderd` provider for templates, users, groups,
  and roles where it is mature enough. Keep runtime settings that the provider
  does not cover (appearance banner, license, AI providers) on a thin reconciler
  driven by git YAML; the AI-provider reconciler already exists
  (`scripts/reconcile-ai-providers.py` with `deploy/coder/ai-providers.yaml`)
  and is the model to generalize. Retire `set-appearance.sh`,
  `grant-coder-owner.py`, and `setup-coder-idp-sync.py` as silent writers.
- **GitLab.** Prefer the Terraform `gitlab` provider for projects, CI/CD
  variables, project access tokens, and webhooks, since that provider is mature.
  The provider runs in-boundary from CI with an admin token sourced from ASM, and
  any generated token is written back to ASM. Retire `gitlab-rails` writes;
  document the one bootstrap gap (first root password) as a known bootstrap-only
  step.
- **Keycloak.** Use `keycloak-config-cli` driven by the git realm JSON (as
  proposed in the adoption plan), reading admin credentials from ASM. Generated
  client secrets are written back to ASM so relying parties converge through ESO.
  The Terraform `keycloak` provider is the alternative if the team prefers one
  IaC tool; record the choice in Section 6.

Each reconciler must support a read-only `verify`/`plan` mode so it can run in
the drift gate without mutating state. Add the live-vs-git config comparison to
`verify-drift.py` for these three domains.

Checkpoint: `verify-drift.py` runs as a **blocking CI gate**; a red gate blocks
merge.

## 5. Repeatable team workflow: stand up and tear down an enclave

The point of v2.0 is that Austen's team can create and destroy a demo enclave
declaratively, not by repeating the overnight imperative build. The workflow is
ordered by dependency.

### Stand up a fresh enclave

1. **Inputs.** Provide a hosted zone, an ACM certificate, an S3/DynamoDB state
   backend, and an ASM prefix for the new enclave. These are the only
   pre-existing inputs.
2. **Infrastructure.** `terraform apply` builds VPC, EKS cluster and node group,
   IRSA, RDS, ECR repos, ESO IAM role, and the ASM secret containers. No Auto
   Mode. No CLI node group.
3. **Images.** Run `scripts/mirror-images.sh` from `scripts/images.txt` to
   populate ECR (GovCloud has no pull-through cache). This is a documented
   bootstrap step, not a reconciler.
4. **Secret values.** Generate or import the value set into ASM (the only value
   source). Optionally rehydrate the derived `generated-secrets.env` cache from
   ASM for local convenience.
5. **GitOps bootstrap.** Install Argo CD (imperative first install, per the
   control-plane plan), push the repo to the in-cluster GitLab source, and apply
   the app-of-apps root. Argo then reconciles all `deploy/*` apps. ESO mirrors
   ASM into Kubernetes Secrets.
6. **API-owned config.** Run the Coder, GitLab, and Keycloak reconcilers (or
   `terraform apply` for the provider-managed parts) against the git
   desired-state. Generated tokens land back in ASM.
7. **Verify.** Run `scripts/verify-drift.py`. A green report is the definition of
   "enclave is ready".

### Tear down an enclave

1. Run the reconcilers in `verify` mode to capture final desired-state if
   anything was changed by hand (it should not have been).
2. Remove the GitOps layer (delete the Argo CD app-of-apps, then the controller)
   so nothing tries to re-create workloads mid-teardown.
3. `terraform destroy` removes infrastructure, including the node group and
   Route53 records now that Terraform owns them.
4. Delete or schedule deletion of the enclave's ASM secrets and KMS keys
   (KMS keys honor their deletion window). Delete the ECR repos and images.
5. Remove the local derived `generated-secrets.env` cache.

Because infrastructure, secrets containers, manifests, and API config are each
declarative and single-writer, stand-up and teardown are repeatable and
auditable rather than a bespoke runbook.

## 6. Risks and open decisions

- **Terraform provider vs idempotent reconciler.** Providers give plan/apply,
  state, and drift detection for free, but couple the platform to provider
  maturity and to running `terraform apply` against app APIs. Thin reconcilers
  are simpler to reason about and run anywhere, but reimplement plan/diff and
  must be kept idempotent. Decision per app: GitLab leans provider (mature),
  Keycloak leans `keycloak-config-cli` (declarative realm is its purpose), Coder
  is a hybrid (provider for templates/users/roles, reconciler for runtime
  settings). Record the final choice per app before Phase 4.
- **EKS Auto Mode: reconcile or remove.** Removing the Auto Mode declaration and
  managing the standard cluster matches live and unblocks `terraform apply`
  soonest. Making Auto Mode work requires resolving the GovCloud SLR permission
  gap and a node migration, which is higher risk close to a demo. Default to
  remove; revisit Auto Mode as a later hardening item.
- **KMS/etcd envelope encryption.** Enabling envelope encryption on an existing
  cluster is irreversible and triggers a re-encrypt. The KMS key is already
  staged in `terraform/secrets-hardening.tf` but not wired into the cluster.
  Treat enablement as an explicit maintenance-window decision, ideally on a
  fresh enclave rather than the live demo cluster.
- **In-boundary GitLab as a hard dependency.** Argo CD syncs from the in-cluster
  GitLab. If GitLab is down, already-synced state keeps running but new desired
  state cannot be fetched. Acceptable for a demo; note it.
- **Token write-back ordering.** A reconciler that rotates a secret in an app,
  writes it to ASM, and waits for ESO plus a pod restart has a brief window of
  inconsistency. Sequence rotations and restarts deliberately, and let the drift
  gate catch a missed convergence.
- **What stays imperative as bootstrap.** Image mirroring to ECR, the GitLab
  first root password, the very first Argo CD install, and the initial ASM value
  generation remain documented bootstrap steps. They run once per enclave and
  are not silent writers to a live system.

## 7. Issue backlog

Discrete, independently shippable work items, each mapped to a domain from
Section 3. These extend the existing plan issue ranges (control-plane #6-#12,
observability #13-#20, adoption #21-#29, istio #30); assign new numbers when
filed.

1. CI: run `scripts/verify-drift.py --json` as a non-blocking report on every
   PR. Domain: drift detection.
2. Drift gate: add a placeholder-secret detector across all synced secrets
   (generalize the Anthropic shape check) and make placeholders FAIL. Domain:
   drift detection / secret values.
3. Drift gate: add a live-vs-git config comparison for Coder, GitLab, and
   Keycloak API-owned config. Domain: drift detection.
4. Capture baseline desired-state: live Helm values, node group config, and the
   Route53 record set into git (read-only capture). Domain: multiple.
5. Terraform: decide and record the EKS Auto Mode resolution (remove vs invest),
   then model the standard cluster. Domain: EKS compute.
6. Terraform: import the `mng` node group and `usgov-coderdemo-mngnode` role and
   manage node capacity, retiring `aws eks update-nodegroup`. Domain: EKS
   compute.
7. Terraform: model and import all Route53 records as `aws_route53_record`
   aliases, retiring the `aws route53` CLI path. Domain: Route53 DNS.
8. Terraform: import the ESO IAM role per the `secrets-hardening.tf` note.
   Domain: secret containers + IAM.
9. Terraform: stage the KMS/etcd envelope-encryption decision and document the
   maintenance-window enablement procedure (do not enable yet). Domain: KMS/etcd.
10. Secrets: inventory `generated-secrets.env` consumers and confirm every value
    has an ASM home. Domain: secret values.
11. Secrets: demote `generated-secrets.env` to a derived, gitignored cache
    rehydrated from ASM; stop scripts from seeding live systems from it. Domain:
    secret values.
12. Secrets: build the single-writer reconciler for the Coder to Keycloak OIDC
    client secret, collapsing the four copies to one ASM-sourced value. Domain:
    Keycloak / Coder.
13. Argo CD: install with auto-sync OFF and `prune: false`, per
    `gitops-control-plane.md`. Domain: in-cluster manifests.
14. Argo CD: adopt leaf manifests (gp3 StorageClass, workspace RBAC,
    ClusterSecretStore and ExternalSecrets) with a benign diff, then enable sync.
    Domain: in-cluster manifests.
15. Argo CD: adopt `kubectl`-applied app manifests (Keycloak, GitLab, Coder
    provisioners). Domain: in-cluster manifests.
16. Argo CD: adopt the Helm releases in order (`external-secrets`,
    `aws-load-balancer-controller`, `ingress-nginx`, `coder`). Domain: in-cluster
    manifests.
17. Argo CD: enable self-management via the app-of-apps. Domain: Argo CD.
18. Coder: adopt the Terraform `coderd` provider for templates, users, groups,
    and roles. Domain: Coder API config.
19. Coder: generalize the AI-provider reconciler into a `verify|plan|apply`
    runtime-settings reconciler (banner, license, AI providers) driven by git
    YAML, retiring the imperative scripts. Domain: Coder API config.
20. GitLab: manage projects, CI/CD variables, project tokens, and webhooks with
    the Terraform `gitlab` provider, with credentials from ASM and generated
    tokens written back to ASM. Domain: GitLab API config.
21. Keycloak: manage the realm, clients, and MFA with `keycloak-config-cli`
    driven by git JSON, with generated client secrets written back to ASM.
    Domain: Keycloak API config.
22. CI: promote `verify-drift.py` to a blocking gate once Phases 1 through 4 are
    green. Domain: drift detection.
23. Workflow: write the declarative stand-up and teardown runbook for a fresh
    enclave (Section 5) and validate it on a throwaway enclave. Domain: multiple.
