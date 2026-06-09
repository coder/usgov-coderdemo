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
| 23 | GitLab -> Coder Agent attribution + PM persona | AUTHORED / STAGED (security review required) | ws-2x/phase2 | Tasks API on-behalf-of ownership (POST /api/v2/tasks/{user}, owner=assignee, verified in reference source); GitLab issue webhook gated by coder-task label; PM persona + receiver authored; NOT applied |
| 24 | Upstream coder/observability dashboards | APPLIED (additive) | ws-2x/phase2 | New aibridge (uid ai-gateway, 33 panels) + boundary (uid agent-firewall, 16 panels) provisioned and verified; old combined ai-governance dashboard retained pending a delete decision |
| 25 | Workspace template family + e2e acceptance | PUSHED + CONFIGURED (coder + alpha) | ws-2x/phase2 | All 5 imported (plan passed) with display-name/icon/routing-description in orgs coder and alpha; fixed platform-engineer heredoc bug and the 128-char description limit; build/C4 still needs a one-time GitLab OAuth (manual) |

## Follow-on wave (2026-06-09, post WS-20..25)
A follow-on wave landed on `ws-2x/phase2` (DRAFT PR #38): the Coder control plane
bump v2.34.0 -> v2.34.1 (Bedrock SigV4 proxy-header fix, backport #26053;
provisioners alpha/bravo rebuilt), enabling the anthropic-bedrock provider
(verified HTTP 200), curating the Coder Agents model picker to 4 models (effort
high + per-model cost), registering the read-only `datastore` MCP server (the
gateway-injected MCP was removed), and configuring chat spend-limits (default
$500/mo, alpha $100, bravo $250, user patrickplatform $50). GitLab MCP was
dropped (CODAGT-570). All applied live and pushed.

## Connectivity / live checks done
| Check | Status | Notes |
|-------|--------|-------|
| Coder API admin login | PASS | https://dev.usgov.coderdemo.io reachable, token issued |
| coderdemo/coder-templates pipeline | PASS | #8 green end to end |
| Registry images | PASS | ubi9-base + ubi9-node tags present |
| WS-20 aibridge anthropic + openai routes | PASS | both POST routes HTTP 200 with real completions |
| WS-21 envdocs gate + content | PASS | 302 to Keycloak (client_id=envdocs); built site 200 behind gate with Mermaid |
| WS-24 dashboards provisioned | PASS | ai-gateway + agent-firewall loaded by Grafana, no errors |
| WS-25 template import (coder + alpha) | PASS | all 5 plan-validated and imported; metadata applied |

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
- WS-24 apply: DONE (additive). New ai-gateway + agent-firewall dashboards
  provisioned and verified. OPEN DECISION for the morning: delete the old
  combined `coder-dashboard-ai-governance` (the two new dashboards supersede it):
  `kubectl delete configmap coder-dashboard-ai-governance -n monitoring`.
- WS-25: DONE (push + metadata) in orgs coder and alpha. REMAINING (manual): a
  one-time in-boundary GitLab OAuth login by the owner, then build one workspace
  per template and run the C4 connectivity check.
- WS-23 apply: NOT applied. Webhook -> Coder Tasks API as the assigned developer
  (owner=assignee) + a PM persona (additive). Security-sensitive; the security
  review checklist in docs/swarm/handoffs/WS-23-handoff.md must be approved
  first.
- WS-22: read-only complete, decision GO. WS-22b enablement (agent firewall on
  claude-code, default-off) is staged for review.

## Active locks / warnings
- versions.lock.yaml baseline (k8s 1.36, KC 26.6.3, GitLab CE 19.0.1). Coder was
  bumped 2.34.0 -> 2.34.1 in the 2026-06-09 follow-on wave (Bedrock SigV4 fix);
  v2.34.1 is now authoritative.
- Do not regress Phase-1 hardening: CODER_DISABLE_PATH_APPS=true, UNCLASSIFIED
  banner, GitHub login disabled, GitLab-only external auth, Keycloak+local SSO.
- decisions-locked.md is Phase-1 era; where it conflicts with the Phase-2
  tasking (realm name "coder", GitLab now on EKS, single coderd replica), the
  live system + Phase-2 prompt are authoritative.

## Remaining for the user (morning)
- WS-25 e2e: complete a one-time GitLab OAuth login as the owner, then build one
  workspace per template (orgs coder/alpha) and run
  scripts/validate-connectivity.sh --track a; confirm app URLs load (JupyterLab
  for data-scientist). Templates are imported and ready.
- WS-23: review the security checklist, then apply the PM persona
  (scripts/setup-pm-persona.py --apply) and the attribution receiver/webhook if
  desired.
- WS-24: decide whether to delete the old ai-governance dashboard (command
  above).
- WS-22b: decide whether to enable the agent firewall on claude-code
  (default-off).
- PR #38 (draft) collects every Phase-2 artifact for review.

## Retry log
| WS | Attempt | Result |
|----|---------|--------|
| recreation push-template | 2 | PASS (attempt 1 transient github 504) |
| WS-25 ai-agent-generic push (coder) | many | PASS after github recovered (earlier 504 outage) |
| WS-25 platform-engineer push (coder) | 2 | PASS after fixing the heredoc `$${...}` escaping |
| WS-25 java/platform push (alpha) | 2 | PASS on spaced retry (intermittent github 504) |
| WS-25 templates edit (4 of 5) | 2 | PASS after shortening descriptions to <=128 chars |
