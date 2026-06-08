# Demo runbook (Coder employees)

This page is for Coder employees demoing the GovCloud environment. It assumes the
stack is live. For deeper detail, follow the links into the component pages.

!!! tip "One login administers everything"
    Sign in as the operator super admin `austen.platform`. It is Coder site
    Owner, GitLab instance admin, and Grafana org Admin, and is org-admin in all
    three Coder organizations. Its password is `SUPERADMIN_PASSWORD` in
    `~/.config/usgov-coderdemo/generated-secrets.env`. First Keycloak sign in
    forces WebAuthn passkey plus TOTP enrollment, so complete that once before the
    demo.

## The headline

Pitch: a self-contained developer platform where authentication, source control,
and AI all stay inside the AWS GovCloud boundary. One Keycloak SSO covers Coder,
GitLab, Grafana, Kiali, and even this docs site. Workspaces run Coder Agents with
Claude Code, and all model traffic flows through the governed AI Gateway.

## Suggested demo order

### 1. SSO and multi-tenancy (Coder)

1. Open `https://dev.usgov.coderdemo.io` and click "Sign in with Keycloak".
2. Sign in as `austen.platform`. Show the org switcher: Platform Engineering,
   Mission Partner Alpha, and Mission Partner Bravo. **Alpha is the demo org.**
3. In a second incognito window, sign in as `dana.dev` (password is
   `DEMO_USER_PASSWORD`). It lands only in Mission Partner Alpha, group
   developers, with no admin rights, and cannot see Bravo or Platform. This shows
   tenant isolation enforced by organization membership.
4. Optionally sign in as `morgan.isso` to show a read-only auditor spanning both
   Alpha and Bravo.

Identity detail: [Identity (Keycloak)](identity-keycloak.md).

### 2. GitLab to Coder Agent flow

1. As `austen.platform` (or `dana.dev` in Alpha), create a workspace from the
   `claude-code` template.
2. The build blocks on a "Login with GitLab" control. Complete the in-boundary
   GitLab OAuth flow against `https://gitlab.usgov.coderdemo.io`. This proves git
   auth never leaves the boundary: no github.com, no PATs or SSH keys in the
   workspace.
3. When the agent reports ready, open the workspace. Show Claude Code, AgentAPI,
   and code-server. Inside the workspace, `git clone` a project from GitLab using
   the agent's injected short-lived token.

Detail: [GitLab SCM](gitlab.md), [Coder control plane](coder-control-plane.md).

### 3. Governed AI (AI Gateway)

1. In the workspace, run a Claude Code prompt. Claude Code talks only to
   `<access_url>/api/v2/aibridge/anthropic` using the owner's Coder session
   token, never a raw model key.
2. Explain the two providers: `anthropic` (direct egress via the NAT gateway) and
   `anthropic-bedrock` (Amazon Bedrock in-region via IRSA, no static key).

!!! warning "Live AI needs a real key"
    The `anthropic` provider ships with a placeholder key, so a real call returns
    `502 "all configured keys failed authentication"`. That 502 still proves the
    full path (client to gateway to upstream). To make AI respond, sign in as the
    owner, open Admin settings > AI > Providers (`/ai/settings`), and paste a real
    `sk-ant-...` key into the `anthropic` provider. Do this in the UI, not the k8s
    secret. Detail: [AI Gateway](ai-gateway.md).

### 4. Observability and governance

1. Open `https://grafana.usgov.coderdemo.io` (Keycloak SSO). As `austen.platform`
   you are Grafana Admin via the `/platform` group rule.
2. Show the Coder dashboards (live metrics and logs) and the **AI Governance**
   dashboard (uid `ai-governance`): AI Gateway Overview, Usage and Cost,
   Intercepts and Sessions, and Agent Firewall. Usage panels read `0` until live
   AI traffic occurs, which is expected with the placeholder key.
3. Optionally open `https://kiali.usgov.coderdemo.io` to show the Istio mesh with
   STRICT mTLS (view-only).

Detail: [Observability](observability.md).

### 5. The boundary story

Reinforce the hardening posture:

- Coder's built-in GitHub login is disabled; login is Keycloak SSO plus a local
  break-glass owner only.
- Path-based workspace apps are disabled; apps serve from their own
  `*.usgov.coderdemo.io` subdomains.
- Secrets live in AWS Secrets Manager and sync via the External Secrets Operator
  with IRSA, never in git. Detail: [Secrets](secrets.md).
- A green `UNCLASSIFIED - USGOVCLOUD` classification banner is shown across Coder.

## Quick reference

| Thing | Value |
|---|---|
| Demo org | Mission Partner Alpha (`alpha`) |
| Super admin | `austen.platform` (Keycloak SSO; `SUPERADMIN_PASSWORD`) |
| Demo developer | `dana.dev` in Alpha (`DEMO_USER_PASSWORD`) |
| Auditor | `morgan.isso` (Alpha + Bravo, read-only) |
| Coder | `https://dev.usgov.coderdemo.io` |
| GitLab | `https://gitlab.usgov.coderdemo.io` |
| Grafana | `https://grafana.usgov.coderdemo.io` |
| AI Gateway route | `POST /api/v2/aibridge/anthropic/v1/messages` |

All credentials are in `~/.config/usgov-coderdemo/generated-secrets.env`
(gitignored, mode 600). Do not echo secret values during a demo.
