# Brief: Authenticated MCP Server in Coder Agents (GitHub hosted MCP)

## 1. Objective and demo narrative

Stand up an authenticated MCP server in Coder Agents on
`https://dev.usgov.coderdemo.io` that demonstrates real authentication plus
need-to-know. The approved backend is GitHub's hosted MCP
(`https://api.githubcopilot.com/mcp/`), accessed read-only with a fine-scoped
GitHub token. Narrative: "Coder Agents reaching an authenticated internal
service. The agent can only call tools the credential is allowed to call, and
each user sees only what their identity can access." Attribution (WS-23) is out
of scope. The single highest risk is a client/server protocol mismatch on
`notifications/initialized` (the 204 gate, see section 3), so verify the gate
before committing the demo to GitHub.

## 2. Prerequisites

- Admin Coder session token in `$TOKEN` and `CODER_URL=https://dev.usgov.coderdemo.io`.
  Environment and admin token setup is documented elsewhere; assume it is ready.
- A fine-scoped GitHub Personal Access Token (PAT) from the user. Use a throwaway
  demo org/repo to keep blast radius small.
- Recommended PAT scopes:
  - Fine-grained, read-only: Contents Read, Metadata Read, Issues Read,
    Pull Requests Read; optional Actions Read; org Members Read; Email Read.
  - Classic alternative: `read:user`, `user:email`, `read:org`, `repo`, paired
    with the `X-MCP-Readonly: true` header as defense in depth.
- For Path B only: ability to create a GitHub OAuth App in the chosen org.

Field reference (verified against `codersdk/mcp.go`,
`CreateMCPServerConfigRequest`): `display_name` (required), `slug` (required),
`description`, `icon_url`, `transport` (required, oneof `streamable_http` `sse`),
`url` (required, url), `auth_type` (required, oneof `none` `oauth2` `api_key`
`custom_headers` `user_oidc`), `oauth2_client_id`, `oauth2_client_secret`,
`oauth2_auth_url`, `oauth2_token_url`, `oauth2_scopes`, `api_key_header`,
`api_key_value`, `custom_headers` (map of string to string), `tool_allow_list`,
`tool_deny_list`, `availability` (required, oneof `force_on` `default_on`
`default_off`), `enabled`, `model_intent`, `allow_in_plan_mode`,
`forward_coder_headers`. The POST returns HTTP 201 with the created object
including `id`.

## 3. THE GATE: 204 vs 202 (verify FIRST)

Coder's MCP client is `mark3labs/mcp-go` v0.38.0, which accepts only HTTP 200 or
202 on the `notifications/initialized` POST. GitLab's MCP returned 204 and was
dropped (CODAGT-570). GitHub's status on that notification is unverified, so this
gate decides whether GitHub MCP is usable as-is.

Most authoritative procedure (register, then read coderd logs):

1. Mint the PAT (section 2).
2. Register the GitHub MCP in Coder with `api_key` + the PAT (section 4 body).
3. Trigger a connection: open a Coder Agents chat with the server enabled, or
   list servers, so coderd attempts to connect.
4. Watch coderd logs for a connection-failure line mentioning status 204:

```sh
kubectl -n coder logs deploy/coder --tail=400 | \
  grep -iE "skipping MCP server.*connection failure|status 204|notifications/initialized"
```

Optional direct probe (confirms GitHub's behavior independent of Coder). Read
the status line on the `notifications/initialized` POST:

```sh
# 1) initialize (capture the Mcp-Session-Id response header if present)
curl -sS -D - -o /dev/null -X POST https://api.githubcopilot.com/mcp/ \
  -H "Authorization: Bearer <fine_scoped_PAT>" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "X-MCP-Readonly: true" \
  --data '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"gate-check","version":"0.0.1"}}}'

# 2) notifications/initialized (echo back Mcp-Session-Id from step 1 if returned)
curl -sS -D - -o /dev/null -X POST https://api.githubcopilot.com/mcp/ \
  -H "Authorization: Bearer <fine_scoped_PAT>" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "X-MCP-Readonly: true" \
  -H "Mcp-Session-Id: <id_from_step_1>" \
  --data '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}'
```

Pass/fail decision:

- Status 200 or 202, and no "skipping MCP server" line: PASS. Proceed with Path A
  (or Path B for the per-user headline).
- Status 204, or coderd logs the connection-failure/204 line: FAIL. GitHub MCP is
  unusable as-is. Switch to Fallback C (in-boundary datastore MCP), which we
  control and can make return 202.

## 4. Path A (recommended, fastest): api_key + PAT

Simplest and genuinely authenticated; it is also the same registration that
clears the gate. Caveat: one PAT is one shared identity, so per-user need-to-know
requires either one server per demoed user (per-user PATs) or Path B.

Exact JSON body. `api_key_value` is set verbatim, so it MUST include the
`Bearer ` prefix:

```json
{
  "display_name": "GitHub (Internal Service)",
  "slug": "github",
  "description": "Read-only GitHub access via GitHub hosted MCP.",
  "transport": "streamable_http",
  "url": "https://api.githubcopilot.com/mcp/",
  "auth_type": "api_key",
  "api_key_header": "Authorization",
  "api_key_value": "Bearer <fine_scoped_PAT>",
  "tool_allow_list": [
    "get_me",
    "search_repositories",
    "get_repository",
    "search_code",
    "list_issues",
    "get_issue",
    "list_pull_requests",
    "get_pull_request"
  ],
  "availability": "default_off",
  "enabled": true
}
```

Register:

```sh
curl -sS -X POST "$CODER_URL/api/experimental/mcp/servers" \
  -H "Coder-Session-Token: $TOKEN" -H "Content-Type: application/json" \
  --data @path/to/body.json
```

X-MCP-Readonly header approach (important). The `api_key` auth type sends exactly
ONE header (`api_key_header`/`api_key_value`). It cannot also send a second static
header such as `X-MCP-Readonly: true`. Per `codersdk/mcp.go`, sending multiple
static headers requires `auth_type: custom_headers` with a `custom_headers` map.
To send both the bearer token and the read-only header, use this body instead:

```json
{
  "display_name": "GitHub (Internal Service)",
  "slug": "github",
  "description": "Read-only GitHub access via GitHub hosted MCP.",
  "transport": "streamable_http",
  "url": "https://api.githubcopilot.com/mcp/",
  "auth_type": "custom_headers",
  "custom_headers": {
    "Authorization": "Bearer <fine_scoped_PAT>",
    "X-MCP-Readonly": "true"
  },
  "tool_allow_list": [
    "get_me",
    "search_repositories",
    "get_repository",
    "search_code",
    "list_issues",
    "get_issue",
    "list_pull_requests",
    "get_pull_request"
  ],
  "availability": "default_off",
  "enabled": true
}
```

Recommendation: use the `custom_headers` body if you want `X-MCP-Readonly: true`
as defense in depth (preferred). Use the `api_key` body only if a single header is
acceptable and the PAT scopes alone enforce read-only. Keep `availability`
`default_off` and `enabled` true so the server exists but users opt in per chat.

## 5. Path B (per-user RBAC headline): manual oauth2 + GitHub OAuth App

Best per-user need-to-know story: each user clicks Connect once, Coder stores a
per-user GitHub token, and each user sees only what their GitHub identity allows.
GitHub advertises no DCR `registration_endpoint`, so oauth2 MUST be manual
(pre-registered GitHub OAuth App). For manual oauth2, supply ALL of
`oauth2_client_id`, `oauth2_auth_url`, and `oauth2_token_url`, otherwise Coder
attempts auto-DCR (which fails for GitHub).

Callback sequencing problem: the OAuth App callback must be
`https://dev.usgov.coderdemo.io/api/experimental/mcp/servers/{id}/oauth2/callback`,
but `{id}` does not exist until the Coder MCP row is created. Resolve in this
order:

1. Create the Coder MCP row first with placeholder oauth2 values so Coder mints
   the `{id}` (returned in the 201 response):

```json
{
  "display_name": "GitHub (Per-User)",
  "slug": "github-oauth",
  "transport": "streamable_http",
  "url": "https://api.githubcopilot.com/mcp/",
  "auth_type": "oauth2",
  "oauth2_client_id": "placeholder",
  "oauth2_client_secret": "placeholder",
  "oauth2_auth_url": "https://github.com/login/oauth/authorize",
  "oauth2_token_url": "https://github.com/login/oauth/access_token",
  "oauth2_scopes": "read:user user:email read:org repo",
  "tool_allow_list": ["get_me", "search_repositories", "get_repository", "list_issues", "get_issue"],
  "availability": "default_off",
  "enabled": false
}
```

2. Create (or edit) the GitHub OAuth App and set its Authorization callback URL to
   `https://dev.usgov.coderdemo.io/api/experimental/mcp/servers/{id}/oauth2/callback`
   using the `{id}` from step 1.
3. Patch the Coder row with the real client id/secret and enable it:

```sh
curl -sS -X PATCH "$CODER_URL/api/experimental/mcp/servers/{id}" \
  -H "Coder-Session-Token: $TOKEN" -H "Content-Type: application/json" \
  --data '{"oauth2_client_id":"<real_id>","oauth2_client_secret":"<real_secret>","enabled":true}'
```

4. Each user opens the connect URL
   (`$CODER_URL/api/experimental/mcp/servers/{id}/oauth2/connect`) from the chat UI,
   authorizes once, and Coder stores their per-user token. Note: oauth2 does not
   carry the `X-MCP-Readonly` header; enforce read-only via scopes and
   `tool_allow_list`.

## 6. Fallback C (in-boundary, clean optics): authenticated datastore MCP

If the gate fails or egress optics must stay inside the GovCloud boundary, add
auth to the existing datastore MCP (`deploy/datastore-mcp`). It currently runs as
`auth_type: none` at
`http://datastore-mcp.coder-demo-mcp.svc.cluster.local:8000/mcp` and is reached
in-cluster. Because we own the code, we control the `notifications/initialized`
response and can guarantee the 202 gate passes. Ranked options:

1. Manual `oauth2` via Keycloak: real per-user auth, in-boundary, best optics. The
   MCP server must validate the access token (issuer, audience, expiry) and map
   the subject to authorized rows. Supply Keycloak `oauth2_auth_url`,
   `oauth2_token_url`, `oauth2_client_id`, `oauth2_client_secret`, `oauth2_scopes`,
   and set the Keycloak client callback to the Coder
   `/oauth2/callback` URL for that server `{id}` (same sequencing as Path B).
2. `user_oidc`: Coder forwards the user's OIDC token to the MCP server, which must
   verify the audience and enforce per-user access. Less setup than full oauth2,
   still per-user.
3. `api_key`: shared static credential, simplest, but a single shared identity (no
   per-user need-to-know).

Implementation note: the current datastore server does not validate the inbound
Authorization header (see `server/main.go`), so options 1 and 2 require adding
token verification before they are a true auth demo. Option 3 only requires Coder
to send the header and the server to check it.

## 7. Verification

- Connected: re-run the section 3 log grep and confirm NO "skipping MCP server"
  line for the slug. Optionally `GET $CODER_URL/api/experimental/mcp/servers` and
  confirm the row is present with `enabled: true`.
- Visible to the model: open a Coder Agents chat, enable the server (it is
  `default_off`), and confirm the tools appear in the chat tools listing /
  model picker as `github__<tool>` (datastore tools appear as `datastore__<tool>`,
  same `slug__tool` convention).
- Smoke test (read-only): ask the agent to call a read-only tool, for example
  `github__get_me` ("who am I authenticated as?") or
  `github__search_repositories` against the throwaway demo org. Confirm it returns
  real data and that a write-style tool is absent because it is not in
  `tool_allow_list`.

## 8. Rollback

- Disable (keep the row): PATCH `enabled:false`.

```sh
curl -sS -X PATCH "$CODER_URL/api/experimental/mcp/servers/{id}" \
  -H "Coder-Session-Token: $TOKEN" -H "Content-Type: application/json" \
  --data '{"enabled":false}'
```

- Delete (remove the row): DELETE returns HTTP 204.

```sh
curl -sS -X DELETE "$CODER_URL/api/experimental/mcp/servers/{id}" \
  -H "Coder-Session-Token: $TOKEN"
```

- Revoke the PAT or the GitHub OAuth App in GitHub after the demo. For Path B,
  users can also disconnect their token via
  `DELETE $CODER_URL/api/experimental/mcp/servers/{id}/oauth2/disconnect`.

## 9. Risks and open questions

- 204 gate (highest risk): if GitHub returns 204 on `notifications/initialized`,
  GitHub MCP is unusable as-is and the demo must use Fallback C. Verify before
  committing.
- Egress / optics: GitHub MCP egresses to public GitHub, so packets and tokens
  leave the GovCloud boundary even though the narrative says "internal service."
  Mitigate with read-only tools, `X-MCP-Readonly: true`, a scoped PAT, and a
  throwaway org/repo. If optics must stay in-boundary, make Fallback C primary.
- Shared vs per-user identity: Path A (api_key) is one shared identity. The
  per-user need-to-know headline needs Path B (oauth2) or one server per user.
- The MCP servers config is a live, DB-resident object, not in git, so the row
  must be recreated by hand if the database is reset.
- Open: which GitHub org/repos for the PAT or OAuth App? Is calling `github.com`
  acceptable for demo optics, or must the authenticated MCP stay in-boundary
  (then Fallback C is primary)? Auth headline preference: per-user RBAC (oauth2)
  or fastest-authenticated (api_key)?

Generated by Coder Agents.
