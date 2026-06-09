# WS-21: Environment docs site (Keycloak-gated)

| Field | Value |
|---|---|
| **Workstream** | WS-21 envdocs |
| **Phase** | 2 |
| **Branch** | `ws-2x/phase2` |
| **Target** | `https://envdocs.usgov.coderdemo.io` |
| **Gate** | Keycloak realm `coder`, any authenticated user (no group restriction) |
| **Status** | PARTIAL (authored + locally verified; root applies) |

## Goal

Publish the environment documentation as an in-boundary MkDocs Material site at
`https://envdocs.usgov.coderdemo.io`, gated by Keycloak SSO so any authenticated
realm `coder` user can read it. Author the manifests, the idempotent installer,
the content, and the docs-as-code policy. Do not apply to the cluster, create the
live OIDC client, add DNS, or commit; the orchestrator (root) does that.

## Design

- **Auth gate:** oauth2-proxy in auth-only mode (`upstream=static://200`) behind
  ingress-nginx external-auth annotations (`auth-url`, `auth-signin`). A new
  confidential Keycloak OIDC client `envdocs` (standard flow, PKCE S256) gates
  the site. Allow policy is `email_domains=*` (any authenticated realm user).
- **Why ingress-nginx, not Istio:** the live DNS path is the Istio gateway; the
  Route53 wildcard `*.usgov.coderdemo.io` aliases to the Istio NLB. ingress-nginx
  is retained but out of the DNS path. An explicit `envdocs` Route53 alias to the
  ingress-nginx NLB (more specific than the wildcard) routes this host through
  ingress-nginx, where the external-auth annotations live. Both NLBs carry the
  same `*.usgov.coderdemo.io` ACM cert, so TLS is valid.
- **Static site:** MkDocs Material built in-cluster by an init container
  (`squidfunk/mkdocs-material`) from a ConfigMap generated out of `docs/envdocs/`,
  served by nginx. Material bundles its assets; Mermaid renders client-side in the
  reader's browser.
- **Secrets:** the OIDC client secret and an oauth2-proxy cookie secret go to AWS
  Secrets Manager (`usgov-coderdemo/envdocs/oauth`) and sync via ESO into the
  `envdocs-oauth` Kubernetes Secret. This mirrors `scripts/setup-grafana-oidc.py`.
- **Images:** three upstream images mirrored into ECR (no GovCloud pull-through):
  `nginx:1.27-alpine`, `squidfunk/mkdocs-material:9.7.6`,
  `oauth2-proxy:v7.7.1`.

## Deliverables (authored)

- `docs/envdocs/` MkDocs site: `mkdocs.yml` plus 10 pages (overview,
  architecture with 3 Mermaid diagrams, six component pages, access/auth gate,
  demo runbook). Builds clean with `mkdocs build --strict`.
- `deploy/envdocs/` manifests: `namespace.yaml`, `externalsecret.yaml`,
  `deployment.yaml` (init build + nginx + Service), `oauth2-proxy.yaml`
  (Deployment + Service), `ingress.yaml` (two Ingresses), `README.md`.
- `scripts/setup-envdocs.py`: idempotent installer (OIDC client + ASM + ECR
  mirror + ConfigMap + manifests + Route53), with `--plan`, `--skip-mirror`,
  `--skip-apply`, `--skip-dns`.
- `CLAUDE.md` and `docs/DOCS-POLICY.md`: docs-as-code policy and the
  `make docs-check` snippet.

## Verification performed (read-only, no cluster mutation)

- `mkdocs build --strict` succeeds; 11 pages, 5 Mermaid blocks emitted.
- All 5 Mermaid diagrams render via `@mermaid-js/mermaid-cli` (caught and fixed a
  `;` statement-separator issue in one sequence diagram).
- `scripts/setup-envdocs.py --plan` resolves the ECR registry, ASM state, the
  three image targets, the manifest list, and the Route53 alias target (the
  ingress-nginx NLB `...k8s-ingressn...`, zone `ZMG1MZ2THAWF1`).
- All five manifests pass `kubectl apply --dry-run=client`.
- The `envdocs-site` ConfigMap generation yields the 11 expected keys.

## Not done (root)

Run the apply path of `scripts/setup-envdocs.py`, which creates the live OIDC
client, writes ASM, mirrors images, applies manifests, and upserts the Route53
alias. Then commit. See `docs/swarm/handoffs/WS-21-handoff.md`.
