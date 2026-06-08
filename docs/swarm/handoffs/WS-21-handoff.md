# WS-21 handoff

- **Status:** APPLIED + VERIFIED (root applied 2026-06-08; gate and content confirmed live)

## Applied result (root, 2026-06-08)
Ran `python3 scripts/setup-envdocs.py` (full install). Created Keycloak client
`envdocs` + groups mapper (HTTP 201), created ASM `usgov-coderdemo/envdocs/oauth`
(client-secret + generated cookie-secret), mirrored nginx/mkdocs-material/
oauth2-proxy into ECR, applied deploy/envdocs/ (namespace, envdocs-site
ConfigMap, ExternalSecret, envdocs Deployment, oauth2-proxy Deployment, both
Ingresses), and upserted the Route53 alias
`envdocs.usgov.coderdemo.io -> ingress-nginx NLB` (more specific than the Istio
wildcard). ESO synced `envdocs/envdocs-oauth` within the wait window. Both pods
are 1/1 Running and rolled out.

Verified live:
- `GET https://envdocs.usgov.coderdemo.io/` -> 302 `/oauth2/start` (gated).
- `/oauth2/start` -> 302 to `auth.usgov.coderdemo.io/realms/coder/.../auth` with
  `client_id=envdocs` and the correct `redirect_uri` (OIDC wiring correct).
- Behind the gate (internal probe of the envdocs Service) the built MkDocs site
  serves HTTP 200, title `usgov-coderdemo Environment Docs`; diagram pages embed
  Mermaid (`/architecture/` 3 refs, `/access-and-auth/` 2 refs).

Note (non-blocking hardening): oauth2-proxy v7.7.1 does not send a PKCE
`code_challenge` by default, so the S256 flow on the confidential `envdocs`
client is not exercised. The client uses a client secret, so this is optional;
to enable PKCE add `--code-challenge-method=S256` to the oauth2-proxy args.

Rollback: `kubectl delete namespace envdocs`; delete the Keycloak `envdocs`
client; delete the Route53 A record `envdocs.usgov.coderdemo.io`; optionally
delete ASM `usgov-coderdemo/envdocs/oauth` and the three mirrored ECR tags.

- **Agent:** WS-21 (envdocs site, Keycloak-gated)
- **Timestamp:** 2026-06-08
- **Git commit:** (root applies + commits; none made by this agent)
- **Branch:** ws-2x/phase2

## Reference commits copied
| Repo | SHA |
|------|-----|
| (none; nothing copied from reference clones) | |

## Outputs (required for downstream)
| Key | Value |
|-----|-------|
| Site URL | https://envdocs.usgov.coderdemo.io |
| Gate | Keycloak realm `coder`, any authenticated user (no group restriction) |
| OIDC client | `envdocs` (confidential, PKCE S256), redirect `https://envdocs.usgov.coderdemo.io/oauth2/callback` |
| ASM secret | `usgov-coderdemo/envdocs/oauth` (keys `client-secret`, `cookie-secret`) |
| K8s namespace | `envdocs` (Istio injection disabled) |
| K8s Secret (ESO) | `envdocs/envdocs-oauth` |
| Route53 | A ALIAS `envdocs.usgov.coderdemo.io` -> ingress-nginx NLB (zone target `ZMG1MZ2THAWF1`, hosted zone `Z06701704WFETYIRU5C8`) |
| ECR images | `docker-hub/library/nginx:1.27-alpine`, `docker-hub/squidfunk/mkdocs-material:9.7.6`, `quay/oauth2-proxy/oauth2-proxy:v7.7.1` |
| Installer | `scripts/setup-envdocs.py` (idempotent) |

## EXACT ordered apply commands (root)

```sh
. ~/.config/usgov-coderdemo/env
export KUBECONFIG=/home/coder/demoenv-workspace/usgov-coderdemo/kubeconfig
export PATH="$HOME/.local/bin:$PATH"
cd /home/coder/demoenv-workspace/usgov-phase2

# 0. (optional) review the plan, read-only, mutates nothing
python3 scripts/setup-envdocs.py --plan

# 1. full idempotent install, in order:
#    OIDC client `envdocs` -> ASM (client-secret + generated cookie-secret)
#    -> mirror 3 images into ECR (crane) -> generate envdocs-site ConfigMap
#    -> apply deploy/envdocs/ -> upsert Route53 alias to the ingress-nginx NLB
python3 scripts/setup-envdocs.py

# 2. wait for the rollout
kubectl -n envdocs rollout status deploy/oauth2-proxy --timeout=180s
kubectl -n envdocs rollout status deploy/envdocs --timeout=180s

# 3. confirm ESO synced the gate secret and the ingresses exist
kubectl -n envdocs get externalsecret envdocs-oauth
kubectl -n envdocs get ingress
```

Re-running step 1 is safe. The cookie secret is generated only once (reused from
ASM on later runs), so sessions survive re-runs. Crane skips image tags already
present in ECR. Route53 uses UPSERT.

Optional phased flags: `--skip-mirror` (images already in ECR), `--skip-apply`
(only refresh the OIDC client + ASM + DNS), `--skip-dns` (manifests only).

## PASS probe

```sh
# (a) UNAUTHENTICATED -> redirect toward Keycloak (auth.)
curl -sS -o /dev/null -w '%{http_code} -> %{redirect_url}\n' \
  https://envdocs.usgov.coderdemo.io/
#   expect: 302 -> https://envdocs.usgov.coderdemo.io/oauth2/start?rd=%2F

curl -sS -o /dev/null -w '%{http_code} -> %{redirect_url}\n' \
  'https://envdocs.usgov.coderdemo.io/oauth2/start?rd=%2F'
#   expect: 302 -> https://auth.usgov.coderdemo.io/realms/coder/protocol/openid-connect/auth?...

# (b) AUTHENTICATED realm `coder` user -> 200
#     Sign in via Keycloak in a browser (or drive a cookie-jar OIDC login like
#     scripts/verify-oidc-login.py). The site returns HTTP 200.

# (c) MERMAID renders: open the Architecture page in the browser; the topology,
#     SSO sequence, and workspace/AI flow diagrams render client-side.
```

DNS note: after the Route53 UPSERT, `envdocs.usgov.coderdemo.io` resolves to the
ingress-nginx NLB (more specific than the `*` wildcard, which points at the Istio
gateway). Allow a short propagation window.

## Validation (done by WS-21, read-only)

- [x] `mkdocs build --strict` clean (11 pages, 5 Mermaid blocks)
- [x] All 5 Mermaid diagrams render via mermaid-cli
- [x] `scripts/setup-envdocs.py --plan` resolves registry/ASM/images/manifests/DNS
- [x] All manifests pass `kubectl apply --dry-run=client`
- [x] `envdocs-site` ConfigMap generates the 11 expected keys
- [x] `python3 -m py_compile scripts/setup-envdocs.py`
- [x] dash-scan: no emdash / endash / spaced double-hyphen in authored files

## Validation (root, after apply)

- [ ] `kubectl -n envdocs get pods` shows `envdocs` and `oauth2-proxy` Running
- [ ] PASS probe (a), (b), (c) above
- [ ] `kubectl -n envdocs get externalsecret envdocs-oauth` is `SecretSynced=True`

## Blockers

- None. Apply requires Keycloak reachable, AWS creds (ASM/ECR/Route53/elbv2),
  `crane`, and `kubectl` (all present in the orchestrator environment).

## Notes for orchestrator

- The `envdocs-site` ConfigMap is generated by the script from `docs/envdocs/`,
  not committed. To publish a content change later: edit `docs/envdocs/`, re-run
  `python3 scripts/setup-envdocs.py --skip-mirror --skip-dns`, then
  `kubectl -n envdocs rollout restart deploy/envdocs`.
- The `groups` mapper on the `envdocs` client is emitted for parity only; the
  gate does not enforce groups.
- Rollback: `kubectl delete ns envdocs` removes the workloads; delete the Route53
  alias and the `envdocs` Keycloak client + ASM secret to fully revert.
- Files authored: `docs/envdocs/**`, `deploy/envdocs/**`,
  `scripts/setup-envdocs.py`, `CLAUDE.md`, `docs/DOCS-POLICY.md`,
  `docs/swarm/workstreams/WS-21-envdocs.md`, this handoff. The `make docs-check`
  target is documented in `docs/DOCS-POLICY.md` for adding to the root `Makefile`
  (not edited by this workstream).
