# Day-2 operations runbook

Operational reference for the GovCloud Coder demo. Status source of truth:
[`STATUS.md`](../../STATUS.md). All commands are run from the repo root
`/home/coder/demoenv-workspace/usgov-coderdemo` unless noted. The shell is
`sh`, so source files with `.`, not `source`.

## Live endpoints

Verified live (read-only) at authoring time. Codes are the raw HTTP status of
an unauthenticated `GET /`.

| Service | URL | Live check | Notes |
|---|---|---|---|
| Coder | `https://dev.usgov.coderdemo.io` | `200` (`/api/v2/buildinfo` -> `v2.34.1+2e8d80a`) | Owner password login or "Sign in with Keycloak". |
| Keycloak | `https://auth.usgov.coderdemo.io` | `302` (redirect to login) | Realm `coder`; admin console at `/admin`, master realm, user `admin`. |
| GitLab | `https://gitlab.usgov.coderdemo.io` | `302` (redirect to login) | Root login; embedded Postgres. |
| Kiali | `https://kiali.usgov.coderdemo.io/kiali` | Keycloak SSO (`/kiali/` -> `200`) | Istio mesh dashboard; OpenID login via realm `coder`, anonymous access disabled. |
| Grafana | `https://grafana.usgov.coderdemo.io` | `302` (`/` -> `/login`; `/login` -> `200`) | Observability dashboards; Keycloak SSO or break-glass admin. See [`55-observability.md`](55-observability.md). |
| Registry | `https://registry.usgov.coderdemo.io` | `401` (`/v2/`, auth required) | GitLab Container Registry, fronted by the Istio gateway. See [`50-gitlab-scm.md`](50-gitlab-scm.md). |

Re-check any endpoint without printing secrets:

```sh
. ~/.config/usgov-coderdemo/env >/dev/null 2>&1
for h in dev auth gitlab; do
  printf '%s -> ' "$h"
  curl -sS -o /dev/null -m 20 -w '%{http_code}\n' "https://$h.usgov.coderdemo.io"
done
```

## Source environment + kubeconfig

```sh
cd /home/coder/demoenv-workspace/usgov-coderdemo
. ~/.config/usgov-coderdemo/env          # AWS profile/region and GitLab root password
export KUBECONFIG=./kubeconfig           # cluster usgov-coderdemo
kubectl get nodes                        # sanity check
```

## Logging into the Coder API / CLI

> **CODER_URL gotcha.** When this runs inside a Coder workspace, the agent
> ambiently exports `CODER_URL=https://dev.coder.com` (the **host** Coder, not
> this demo). Always target the demo explicitly with
> `https://dev.usgov.coderdemo.io`; do not reuse `$CODER_URL`. The helper
> scripts use a separate `DEMO_CODER_URL` for exactly this reason
> (`scripts/set-appearance.sh`).

Locate a Coder CLI binary:

```sh
ls -t /tmp/coder.*/coder | head -1       # host CLI cached in the workspace
# in-pod binary, if exec'ing into the coder pod: /opt/coder
```

CLI login against the demo:

```sh
CODER_URL=https://dev.usgov.coderdemo.io "$(ls -t /tmp/coder.*/coder | head -1)" login https://dev.usgov.coderdemo.io
```

API login (owner credentials from `generated-secrets.env`, never echo them):

```sh
. ~/.config/usgov-coderdemo/generated-secrets.env
TOKEN=$(curl -sS https://dev.usgov.coderdemo.io/api/v2/users/login \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"$CODER_ADMIN_EMAIL\",\"password\":\"$CODER_ADMIN_PASSWORD\"}" \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["session_token"])')
# Use it: curl -H "Coder-Session-Token: $TOKEN" https://dev.usgov.coderdemo.io/api/v2/users/me
```

Reference: org id `5de29a6d-8836-4643-a42b-2cb807c8e3e2` (facts sheet).

## Credentials map

Where each secret lives. Do not print values.

| Secret | Location | Contents |
|---|---|---|
| AWS profile / region, GitLab root password | `~/.config/usgov-coderdemo/env` | `GITLAB_ROOT_PASSWORD`, AWS profile/region; Docker Hub creds for mirroring. Source before AWS commands. |
| Generated app credentials | `~/.config/usgov-coderdemo/generated-secrets.env` (gitignored, mode 600) | Coder owner (`CODER_ADMIN_EMAIL` / `CODER_ADMIN_PASSWORD`), Keycloak admin, Keycloak `demo` user, DB passwords, Coder<->Keycloak OIDC client secret, GitLab OAuth app id/secret (`GITLAB_CODER_OAUTH_*`). |
| RDS master | AWS Secrets Manager `usgov-coderdemo/rds/master` | JSON `username`,`password`,`host`,`port`; master user `dbadmin`. |
| Coder k8s Secrets (ns `coder`) | k8s | `coder-db` (key `url`), `coder-oidc` (key `client-secret`), `coder-ai` (key `ANTHROPIC_API_KEY`, currently a placeholder), `coder-external-auth` (keys `gitlab-client-id`, `gitlab-client-secret`). |
| Keycloak k8s Secrets (ns `keycloak`) | k8s | `keycloak-db` (`username`/`password`), `keycloak-admin` (`username`/`password`). |
| GitLab k8s Secret (ns `gitlab`) | k8s | `gitlab-secrets` (`initial_root_password`). |

Sources: `deploy/platform/README.md`, `deploy/coder/`, `deploy/keycloak/`,
`deploy/gitlab/`, `STATUS.md`, facts sheet.

> **AI provider key is in the database, not a k8s Secret.** Since v2.34 the AI
> Gateway providers live in the Coder DB. Rotate the Anthropic key in the UI at
> `/ai/settings`, not by editing the `coder-ai` Secret. Editing a seeded
> `CODER_AI_GATEWAY_PROVIDER_*` env var or the secret after first boot makes
> coderd refuse to start (drift guard) (`deploy/coder/README.md`).

## Helm upgrade pattern (Coder)

```sh
helm upgrade coder ~/.cache/helm/repository/coder_helm_2.34.1.tgz \
  --namespace coder \
  --values deploy/coder/values.yaml \
  --timeout 6m
kubectl -n coder rollout status deploy/coder
```

Caution: the `CODER_AI_GATEWAY_PROVIDER_*` env vars in `values.yaml` only seed
the DB on first startup. A later upgrade that changes any of those values (or
the `coder-ai` secret) breaks startup unless you first reconcile the change in
`/ai/settings`. Treat them as one-time seed config (`deploy/coder/README.md`).

## Pushing a template

The single template is `claude-code` (`coder-templates/claude-code/`). From the
repo root, targeting the demo Coder:

```sh
# First time: create the template.
coder templates push claude-code \
  --directory coder-templates/claude-code \
  --variable namespace=coder-workspaces

# Subsequent updates push a new version.
coder templates push claude-code \
  --directory coder-templates/claude-code
```

Variables: `namespace` (default `coder-workspaces`), `workspace_image`
(default ECR-mirrored `enterprise-base`), `use_kubeconfig` (default `false`).
The provisioner is in-process in coderd, so leave `use_kubeconfig=false`
(`coder-templates/claude-code/README.md`).

## Mirroring images

ECR has no pull-through cache in GovCloud, so upstream images are copied in with
`crane`. The image list is `scripts/images.txt`.

```sh
. ~/.config/usgov-coderdemo/env          # Docker Hub + AWS creds, region
scripts/mirror-images.sh                 # add --dry-run to preview
```

Currently mirrored: `ghcr.io/coder/coder:v2.34.1`,
`quay.io/keycloak/keycloak:26.6.3`, `docker.io/gitlab/gitlab-ce:19.0.1-ce.0`,
`docker.io/codercom/enterprise-base:ubuntu-noble-20260601`, plus
`postgres:18-alpine` for db bootstrap (`scripts/images.txt`, `STATUS.md`).

## Setting the classification banner

The green `UNCLASSIFIED - USGOVCLOUD` banner (`#007a33`) is a runtime DB setting
(premium-gated), not Helm. Reproduce idempotently:

```sh
scripts/set-appearance.sh                # reads admin creds from generated-secrets.env
```

The script targets `DEMO_CODER_URL` (default `https://dev.usgov.coderdemo.io`),
logs in as the owner, PUTs `/api/v2/appearance`, then reads it back to confirm
(`scripts/set-appearance.sh`).

## Checking pod health

```sh
export KUBECONFIG=./kubeconfig
kubectl get pods -A | grep -Ev 'Running|Completed'    # anything unhealthy
kubectl -n coder get pods
kubectl -n coder rollout status deploy/coder
kubectl -n keycloak rollout status deploy/keycloak
kubectl -n gitlab rollout status statefulset/gitlab
kubectl -n ingress-nginx get pods                     # expect 2 controller replicas
kubectl -n coder-workspaces get pods                  # active workspace pods
kubectl -n monitoring get pods                        # Prometheus, Grafana, Loki, Promtail
kubectl -n gitlab-runner get pods                     # CI runner manager

# Logs and recent events when a pod is unhappy:
kubectl -n <ns> logs <pod> --tail=200
kubectl -n <ns> get events --sort-by=.lastTimestamp | tail -30
```

Expected namespaces: `coder`, `coder-workspaces`, `external-secrets`, `gitlab`,
`gitlab-runner`, `ingress-nginx`, `istio-system`, `keycloak`, `monitoring`. Coder
and Keycloak run 1 replica each; the `coder` namespace also runs the two external
per-org provisioner daemons (`coder-provisioner-alpha`, `coder-provisioner-bravo`);
GitLab is the `gitlab-0` StatefulSet; `gitlab-runner` runs the CI runner manager;
`monitoring` runs the kube-prometheus-stack plus Loki and Promtail; the Istio
ingress gateway runs 2 replicas in `istio-system` alongside `istiod` and `kiali`;
ingress-nginx still runs 2 controller replicas but is out of the DNS path (facts
sheet, `STATUS.md`). Verified live this session.

## Istio service mesh (day-2 + rollback)

The live L7 edge is the Istio ingress gateway, not ingress-nginx. Full detail is
in [`25-istio-service-mesh.md`](25-istio-service-mesh.md).

Where things live:

- Gateway + control plane: ns `istio-system`. The ingress gateway sits behind its
  own internet-facing NLB (the ACM cert is attached there); `istiod` is the
  control plane. Show the gateway NLB hostname (the `EXTERNAL-IP`):

  ```sh
  export KUBECONFIG=./kubeconfig
  kubectl -n istio-system get svc istio-ingressgateway -o wide
  ```

- Meshed namespaces: `coder`, `keycloak`, `gitlab` (sidecar-injected);
  `coder-workspaces` is intentionally NOT injected. Confirm with
  `kubectl get ns -L istio-injection`.

Reaching Kiali: browse `https://kiali.usgov.coderdemo.io/kiali` and sign in with
Keycloak SSO (OpenID, realm `coder`; anonymous access is disabled).

Checking mTLS:

- In Kiali, use the Security view (the lock badges on the graph) to confirm the
  service-to-service edges are mutual TLS.
- From Prometheus or Grafana, mutual-TLS request volume is
  `istio_requests_total{connection_security_policy="mutual_tls"}`.

Rolling back the mesh:

- Drop mesh-wide STRICT back to PERMISSIVE (keeps the sidecars, allows plaintext
  again) by re-applying the same-named `PeerAuthentication`:

  ```sh
  kubectl apply -f deploy/istio/security/peerauthentication-permissive.yaml
  ```

- Per-host edge rollback to nginx: repoint that host's Route53 ALIAS from the
  Istio gateway NLB back to the ingress-nginx NLB
  `k8s-ingressn-ingressn-e16fe3cd33-...`. nginx is still running for exactly this
  reason; its decommission is tracked in issue #34.

## Known gaps / remaining actions

1. **Real Anthropic key not set.** The `anthropic` provider holds a placeholder
   (`sk-ant-REPLACE_ME_...`). AI requests return `502 "all configured keys
   failed authentication"` until a real `sk-ant-...` key is pasted into the
   `anthropic` provider at `/ai/settings` (UI, not the `coder-ai` secret). No
   real Anthropic key exists anywhere in the environment (`STATUS.md`, facts
   sheet).
2. **Bedrock Claude Sonnet 4.5 (enabled, not a gap).** The `anthropic-bedrock`
   provider is enabled and verified on v2.34.1: `InvokeModel` on
   `us-gov.anthropic.claude-sonnet-4-5-20250929-v1:0` is ACTIVE in
   `us-gov-west-1` and returns HTTP 200 via IRSA (no key). The earlier v2.34.0
   SigV4 `403` (proxy headers carried into signing) was fixed by
   coder/coder#26019, shipped via backport #26053. `amazon.nova-pro-v1:0` is the
   small-fast model (`STATUS.md`, `deploy/coder/ai-providers.yaml`).
3. **IdP sync is built (not a gap).** Keycloak realm `coder` now carries the
   org/team/role group tree, the full-path `groups` claim mapper on the `coder`
   client, and Coder runs organization + group + role sync on every login
   (`scripts/setup-keycloak-hierarchy.py`, `scripts/setup-coder-idp-sync.py`).
   Verified live via the persona logins in
   [`45-idp-sync-personas.md`](45-idp-sync-personas.md); this supersedes the
   earlier "no group/role sync" note.
4. **Provisioners: built-in plus per-org external.** The default org is served by
   the built-in provisioner daemons inside the coderd pod. Each tenant org now
   also runs its own external provisioner daemon (`coder-provisioner-alpha`,
   `coder-provisioner-bravo` in ns `coder`, both `Running` and verified live)
   authenticated with an org-scoped provisioner key (Secret
   `coder-provisioner-<org>`), so no shared `daemon_psk` is used
   (`deploy/coder/provisioners.yaml`,
   [`45-idp-sync-personas.md`](45-idp-sync-personas.md)).
5. **Terraform reconciliation backlog.** Several pieces were applied
   imperatively (CLI/Helm/kubectl/API) and are not yet in `terraform/`: Auto
   Mode disabled plus standard node group `mng` and node role
   `usgov-coderdemo-mngnode`; EBS CSI IRSA role and addon SA role; self-managed
   addons and the `gp3` StorageClass; ingress-nginx and
   aws-load-balancer-controller via Helm; RDS roles/dbs created via SQL; ECR
   image mirroring; Route53 records; k8s Secrets; Keycloak realm import; the
   Coder Helm release plus runtime appearance banner and DB-seeded AI providers;
   the GitLab OAuth app minted via API; and the Coder template push. The Istio
   service mesh (gateway + STRICT mTLS + namespace injection + Route53 cutover +
   Kiali) was likewise applied imperatively this session. See `STATUS.md`
   "Deviations to reconcile into Terraform" and
   [`80-iac-vs-imperative.md`](80-iac-vs-imperative.md).

Out of scope for the demo: OpenShift (`STATUS.md`). Istio is now the live edge
([`25-istio-service-mesh.md`](25-istio-service-mesh.md)); observability
([`55-observability.md`](55-observability.md)) and identity sync
([`45-idp-sync-personas.md`](45-idp-sync-personas.md)) have also been built.

## Related documents

- [`00-overview.md`](00-overview.md): executive and architecture overview, the
  three core flows, and the component map.
- Layer deep-dives `10` through `80` in this directory.
- [`STATUS.md`](../../STATUS.md): canonical build status.

---

*As-built runbook authored by Coder Agents. Read-only; grounded in repo files
and `STATUS.md`.*
