# As-built: Kubernetes platform layer

The shared cluster platform that every app depends on: namespaces, ingress and
the NLB, storage, workspace RBAC, and the platform-owned Secrets. Grounded in
repo files and read-only `kubectl` output captured 2026-06-07 against EKS
cluster `usgov-coderdemo` (k8s 1.36). Mutating steps were performed during the
overnight build; `deploy/platform/README.md` is the reproducible record.

## Namespaces and what runs in each

Live `kubectl get ns` plus `kubectl get pods -A -o wide`:

| Namespace | Workloads (live) |
|---|---|
| `coder` | Coder control plane `coder` (Deployment, 1 replica) |
| `coder-workspaces` | Workspace pods (e.g. `coder-8e0c3f4a-...`, 1/1 Running) |
| `gitlab` | `gitlab-0` (StatefulSet, embedded Postgres/Redis) |
| `keycloak` | `keycloak` (Deployment, 1 replica) |
| `ingress-nginx` | `ingress-nginx-controller` (2 replicas), out of the DNS path, kept for rollback (issue #34) |
| `istio-system` | Istio mesh: `istiod`, `istio-ingressgateway` (2, the live edge NLB), `kiali`. See [25-istio-service-mesh.md](25-istio-service-mesh.md) |
| `kube-system` | `aws-load-balancer-controller` (2), `aws-node`/vpc-cni, `coredns` (2), `kube-proxy`, `ebs-csi-controller` (2) + `ebs-csi-node` (DaemonSet) |

The `coder` and `coder-workspaces` namespaces are split on purpose: the control
plane runs in `coder`, while it provisions workspace pods into
`coder-workspaces` (see workspace RBAC below and
`coder-templates/claude-code/main.tf`).

## Ingress: the Istio gateway is the live L7 edge

> **Live edge: Istio.** The L7 edge is now the Istio ingress gateway behind its
> own internet-facing NLB, not ingress-nginx. One `Gateway` plus per-host
> `VirtualService` objects route every public host (`dev`/workspace apps,
> `auth`, `gitlab`, `grafana`, `kiali`), TLS still terminates at the NLB with
> the same ACM wildcard cert, and the gateway normalizes `x-forwarded-proto:
> https` to every backend. All Route53 records point at the gateway NLB.
> ingress-nginx still runs but is out of the DNS path, kept only for rollback;
> its decommission is tracked in issue #34. See
> [25-istio-service-mesh.md](25-istio-service-mesh.md) for the gateway, NLB/TLS
> design, per-host routing, and the mTLS model. The nginx detail below documents
> the still-running rollback path.

## Ingress (rollback path): NLB, aws-load-balancer-controller, ingress-nginx

Two controllers cooperate:

- `aws-load-balancer-controller` (Helm release in `kube-system`, 2 replicas)
  provisions and manages the NLB for the ingress-nginx controller Service.
- `ingress-nginx` (Helm chart `4.15.1`, 2 controller replicas) is the in-cluster
  ingress. Every app `Ingress` uses `ingressClassName: nginx`.

The ingress-nginx controller Service is `type: LoadBalancer` and is opted in to
the LB controller (not the in-tree provider) via
`aws-load-balancer-type: external`. Live annotations on the Service
(`kubectl get svc -n ingress-nginx ingress-nginx-controller`):

| Annotation | Value |
|---|---|
| `aws-load-balancer-type` | `external` |
| `aws-load-balancer-scheme` | `internet-facing` |
| `aws-load-balancer-nlb-target-type` | `ip` |
| `aws-load-balancer-backend-protocol` | `tcp` |
| `aws-load-balancer-ssl-cert` | `arn:aws-us-gov:acm:us-gov-west-1:430737322961:certificate/7f4fc566-8efd-4aa5-b6ba-3b0c9a535d12` |
| `aws-load-balancer-ssl-ports` | `443` |
| `aws-load-balancer-cross-zone-load-balancing-enabled` | `true` |

These match `deploy/platform/ingress-nginx-values.yaml`. Public subnets are
auto-discovered through the `kubernetes.io/role/elb=1` subnet tag.

TLS terminates at the NLB. Both Service ports forward to the controller's plain
HTTP container port (live `.spec.ports`): port `443` -> `targetPort: http` and
port `80` -> `targetPort: http`. So the NLB decrypts on 443 and forwards plain
TCP to nginx HTTP, and traffic from nginx to pods is also plain HTTP. To avoid
an http->https redirect loop on an L4 NLB that does not inject a trustworthy
`X-Forwarded-Proto`, the controller config sets `ssl-redirect: "false"` and
`use-forwarded-headers: "true"`, plus websocket-friendly timeouts and
`proxy-body-size: "0"` (`deploy/platform/ingress-nginx-values.yaml`).

Two IngressClasses exist live: `nginx` (`k8s.io/ingress-nginx`, used by all app
ingresses) and `alb` (`ingress.k8s.aws/alb`, shipped by the LB controller, not
used by any app). All three app ingresses (`coder`, `gitlab`, `keycloak`)
resolve to the same NLB address (live `kubectl get ingress -A`).

Hairpin: the Route53 names resolve to the public gateway NLB, and in-cluster
requests to those public hostnames route back through the NLB with valid TLS.
This lets Coder's server-side OIDC calls to Keycloak and workspace agent
connections work without split-horizon DNS (`deploy/platform/README.md`,
`STATUS.md`).

## Storage

Live `kubectl get sc`:

| StorageClass | Provisioner | Default | Binding | Encrypted | Expansion |
|---|---|---|---|---|---|
| `gp3` | `ebs.csi.aws.com` | yes | `WaitForFirstConsumer` | `true` | `true` |
| `gp2` | `kubernetes.io/aws-ebs` (in-tree) | no | `WaitForFirstConsumer` | n/a | `false` |

`gp3` is the platform-created default and is the class every workload uses
(`gp3` parameters `type=gp3`, `encrypted=true`; live `kubectl get sc gp3 -o
yaml`). `gp2` is the legacy in-tree class that ships with the cluster and is not
used. GitLab's three PVCs and the workspace home PVC request `gp3`
(`deploy/gitlab/statefulset.yaml`, `coder-templates/claude-code/main.tf`).

Note: `deploy/gitlab/README.md` mentions an EKS Auto Mode class `auto-ebs-sc`,
but that is superseded; the committed `statefulset.yaml` and the live cluster
both use `gp3` (Auto Mode was disabled).

## Workspace RBAC

`deploy/platform/workspace-rbac.yaml` declares a `Role` + `RoleBinding` named
`coder-workspace-perms` in the `coder-workspaces` namespace, binding the
`coder/coder` ServiceAccount. The rules grant, on `pods` and
`persistentvolumeclaims` (core API) and `deployments` (`apps`):
`create, delete, deletecollection, get, list, patch, update, watch`.

This is needed because the Coder Helm chart's `serviceAccount.workspacePerms`
only creates the equivalent Role in the release namespace (`coder`), but
workspaces run in `coder-workspaces`. Live state confirms the Role exists in
both namespaces (`kubectl get role,rolebinding -n coder` and
`-n coder-workspaces`):

| Namespace | Role | RoleBinding | Origin |
|---|---|---|---|
| `coder` | `coder-workspace-perms` | `coder` | Coder Helm chart (`serviceAccount.workspacePerms: true`) |
| `coder-workspaces` | `coder-workspace-perms` | `coder-workspace-perms` | `deploy/platform/workspace-rbac.yaml` (applied imperatively) |

## Platform-owned Kubernetes Secrets

The platform layer creates the application Secrets imperatively so they never
touch git; the committed `secrets.example.yaml` files document the exact
names/keys (`deploy/platform/README.md`, `deploy/coder/secrets.example.yaml`).
The four Secrets in the `coder` namespace and their consumers:

| Secret | Keys | Consumed by | How |
|---|---|---|---|
| `coder-db` | `url` | Coder control plane | `CODER_PG_CONNECTION_URL` (full libpq URL to the `coder` RDS database, `sslmode=require`) |
| `coder-oidc` | `client-secret` | Coder control plane | `CODER_OIDC_CLIENT_SECRET` for Keycloak realm `coder`, client `coder` |
| `coder-ai` | `ANTHROPIC_API_KEY` | Coder AI Gateway, provider `anthropic` | `CODER_AI_GATEWAY_PROVIDER_0_KEY` (Anthropic-direct; the Bedrock provider uses IRSA and needs no key) |
| `coder-external-auth` | `gitlab-client-id`, `gitlab-client-secret` | Coder external auth | `CODER_EXTERNAL_AUTH_0_CLIENT_ID` / `_SECRET` for in-cluster GitLab git auth |

Source: `deploy/coder/values.yaml` (env `valueFrom.secretKeyRef`) and
`deploy/coder/secrets.example.yaml`.

For completeness, the other app namespaces own their own Secrets, also created
imperatively (`deploy/platform/README.md`, `deploy/keycloak/README.md`,
`deploy/gitlab/README.md`):

| Secret | Namespace | Consumed by |
|---|---|---|
| `keycloak-db` (`username`,`password`) | `keycloak` | Keycloak `KC_DB_USERNAME`/`KC_DB_PASSWORD` |
| `keycloak-admin` (`username`,`password`) | `keycloak` | Keycloak bootstrap admin |
| `gitlab-secrets` (`initial_root_password`) | `gitlab` | GitLab `GITLAB_INITIAL_ROOT_PASSWORD` (first boot only) |

## Coder ServiceAccount and IRSA

The Helm chart creates ServiceAccount `coder` in the `coder` namespace and
annotates it for IRSA. Live annotation (`kubectl get sa coder -n coder`):
`eks.amazonaws.com/role-arn:
arn:aws-us-gov:iam::430737322961:role/usgov-coderdemo-coder-bedrock`. This is
how the AI Gateway Bedrock provider authenticates without static AWS keys
(`deploy/coder/values.yaml`; the role and policy are documented in
`docs/as-built/10-infrastructure.md`).

## Helm releases vs applied manifests

Live Helm releases (`kubectl get secret -A -l owner=helm`):

| Release | Namespace | Revisions |
|---|---|---|
| `coder` | `coder` | v1..v4 |
| `ingress-nginx` | `ingress-nginx` | v1 |
| `aws-load-balancer-controller` | `kube-system` | v1 |

Keycloak and GitLab are not Helm releases; they are plain manifests applied with
`kubectl apply` (`kubectl apply -k deploy/keycloak/`, `kubectl apply -f
deploy/gitlab/*.yaml`). See `docs/as-built/80-iac-vs-imperative.md` for the full
declarative-vs-imperative ledger.
