# Swarm status

**Updated:** 2026-06-08 (overnight, Phase-2 demo-finishing wave)
**Phase 1:** PASS (stack live; see STATUS.md and docs/as-built/)
**Phase 2 wave:** IN PROGRESS
**Orchestrator session:** Coder Agent (root), on behalf of @ausbru87

## Orchestrator adaptations (read first)
- This harness has no separate model picker (no "Opus 4.8 Xhigh / Sonnet / Haiku"
  labels). Sub-agents inherit the orchestrator model. The intent is honored via
  sub-agent types: `type=general` for authoring/apply, `type=explore` reserved
  for repo-local read-only tracing. Reasoning-heavy design tasks are run as
  `type=general` sub-agents with explicit read-only constraints.
- Only root provisions workspaces and mutates the cluster. Sub-agents author and
  do read-only investigation; they do NOT run git or mutate the cluster.
- Risk posture for a LIVE env the night before the practice run: reversible
  applies are done with verification; high-blast-radius live mutations (anything
  that can crash coderd, change auth surfaces, or swap working dashboards) are
  AUTHORED + STAGED with exact apply commands and a go/no-go flag, not blind
  applied unattended. See "Go/no-go for live applies" below.

## Fold-in (recreate coderdemo/coder-templates, UBI CI): DONE
- PASS. Pipeline #8 green: Kaniko built ubi9-base-workspace + ubi9-node-workspace
  (tags 9.7, 9.7-9e06f79b, latest) to the coderdemo/coder-templates Container
  Registry; push-template succeeded on retry (first attempt hit a transient
  github 504 during provider fetch); claude-code-ci active version refreshed in
  Coder org "coder" at 2026-06-08T06:14:31Z; runner online as the coderdemo
  group runner. PR #37 marked ready for review.

## Phase-2 workstreams (this wave)
| WS | Title | Status | Branch | Notes |
|----|-------|--------|--------|-------|
| 20 | AI providers declarative reconciler | APPLIED / PASS | ws-2x/phase2 | Real anthropic+openai keys live via API; 4 model presets; aibridge anthropic+openai routes return HTTP 200; coderd 2/2 no restart; re-run is no-op |
| 21 | envdocs.usgov.coderdemo.io (KC-gated) | APPLIED + VERIFIED | ws-2x/phase2 | Live: 302 gate to Keycloak (client_id=envdocs), built MkDocs site serves 200 behind the gate with Mermaid; routed via ingress-nginx NLB + more-specific Route53 record |
| 22 | Agent Firewall (Boundary) feasibility | GO (read-only complete) | ws-2x/phase2 | AL2023 kernel 6.18 supports landjail/nsjail in-pod, no AMI change; AI Governance add-on licensed; WS-22b enablement staged default-off |
| 23 | GitLab -> Coder Agent attribution + PM persona | AUTHORING (SA running) | ws-2x/phase2 | Design + PM persona + webhook authored as STAGED; security-sensitive, needs user review before apply |
| 24 | Upstream coder/observability dashboards | APPLIED (additive) | ws-2x/phase2 | New aibridge (uid ai-gateway, 33 panels) + boundary (uid agent-firewall, 16 panels) provisioned and verified; old combined ai-governance dashboard retained pending a delete decision |
| 25 | Workspace template family + e2e acceptance | AUTHORED / STAGED | ws-2x/phase2 | 5 EKS templates authored, terraform fmt clean; root pushes/tests live |

## Connectivity / live checks done
| Check | Status | Notes |
|-------|--------|-------|
| Coder API admin login | PASS | https://dev.usgov.coderdemo.io reachable, token issued |
| coderdemo/coder-templates pipeline | PASS | #8 green end to end |
| Registry images | PASS | ubi9-base + ubi9-node tags present |

## Go/no-go for live applies (need orchestrator/user confirmation before apply)
- WS-20 apply: DONE. Enabled anthropic + openai providers via the AI Providers
  API with real keys (never touched the seeded CODER_AI_GATEWAY_PROVIDER_* Helm
  env). Verified: 4 model presets, aibridge anthropic + openai routes HTTP 200,
  coderd stayed 2/2 with 0 restarts, re-run is a no-op.
- WS-21 apply: DONE. New public subdomain envdocs.usgov.coderdemo.io live and
  gated by oauth2-proxy against Keycloak realm coder. Additive (own namespace,
  new OIDC client, new Route53 record); did not touch existing hosts. Verified
  302 gate plus 200 site behind the gate. Routes via ingress-nginx (issue #34
  decommission would require moving envdocs to Istio first).
- WS-24 apply: delete custom dashboard, apply upstream aibridge+boundary
  dashboards. Reversible via git; verify panels 200 after.
- WS-23 apply: webhook -> Coder Agents API as the assigned developer; new PM
  persona (additive). Security-sensitive (impersonation/token); review the
  design before apply.
- WS-22: NO live apply tonight (read-only); decision pending sub-agent findings.

## Active locks / warnings
- versions.lock.yaml is authoritative (Coder 2.34.0, k8s 1.36, KC 26.6.3, GitLab
  CE 19.0.1). Do not bump Coder.
- Do not regress Phase-1 hardening: CODER_DISABLE_PATH_APPS=true, UNCLASSIFIED
  banner, GitHub login disabled, GitLab-only external auth, Keycloak+local SSO.
- decisions-locked.md is Phase-1 era; where it conflicts with the Phase-2
  tasking (realm name "coder", GitLab now on EKS, single coderd replica), the
  live system + Phase-2 prompt are authoritative.

## Next wave
- Collect Wave A sub-agent handoffs; review authored artifacts; commit per-WS.
- Wave B (root, serialized, <=2 EKS mutators): WS-20 apply (go/no-go), WS-21
  build+publish, WS-24 deploy+rename, WS-23 design+persona+handler.
- Wave C: WS-24c panel verification; WS-25 push+test templates; WS-25c
  super-admin + full e2e acceptance.

## Retry log
| WS | Attempt | Result |
|----|---------|--------|
| recreation push-template | 2 | PASS (attempt 1 transient github 504) |
