# WS-25 Brief: Template Golden-Path End-to-End Verification

Execution-ready checklist. A parent agent runs this later. Read it in order.
All commands target the live GovCloud demo deployment.

- Deployment: `https://dev.usgov.coderdemo.io`
- Coder version: v2.34.1
- Primary org: `coder` (id `5de29a6d-8836-4643-a42b-2cb807c8e3e2`). Other orgs: `alpha`, `bravo`.
- Templates in repo: `/home/coder/demoenv-workspace/usgov-phase2/coder-templates/`
  (`ai-agent-generic`, `claude-code`, `cpp-engineer`, `data-scientist`,
  `java-engineer`, `platform-engineer`, `firewalled`). `claude-code-ci` is also
  registered in Coder.

Set these shell variables before running steps:

```bash
CODER_URL="https://dev.usgov.coderdemo.io"
ADMIN_TOKEN="<admin session token>"
ORG_ID="5de29a6d-8836-4643-a42b-2cb807c8e3e2"
```

## 1. Objective

Prove that each demo template builds to a healthy, connected workspace and
passes a basic connectivity check. The goal is to de-risk the live demo's
template flow so that, on demo day, every template starts cleanly and the
agent reports ready. Success per template means: build job completes,
`latest_build.status` is `running`, the agent is `lifecycle_state=ready` and
`status=connected`, and the connectivity smoke test returns HTTP `200`.

## 2. The GitLab external-auth gate (read before building anything)

Every `claude-code`-derived template, and `platform-engineer`, declares:

```hcl
data "coder_external_auth" "gitlab" {
  id = "gitlab"
}
```

Declaring this data source without `optional = true` makes the workspace
REQUIRE that the workspace OWNER has completed the in-cluster GitLab OAuth
login before the build will proceed. There is NO device flow: `GET
/api/v2/external-auth/gitlab` returns `"device":false`. The login must happen
once, in a browser, at `https://dev.usgov.coderdemo.io/external-auth/gitlab`.

Current state observed this session:

- `admin` is NOT GitLab-authenticated. `GET /api/v2/external-auth/gitlab`
  returns `authenticated:false`. An admin-initiated `coder create` against a
  gitlab-gated template hangs on "Waiting for Git authentication".
- `austenplatform` IS authenticated (has running claude-code workspaces).

The provisioner uses the OWNER's GitLab token at build time, not the
requester's token. That fact drives both remediation options below.

### Remediation A (preferred for templates a human will demo)

Have the demoing user complete the one-time browser OAuth login at
`https://dev.usgov.coderdemo.io/external-auth/gitlab` while logged in as that
user. After this, that user can `coder create` gitlab-gated templates
normally. Confirm with `GET /api/v2/external-auth/gitlab` returning
`authenticated:true` for that user's token.

### Remediation B (workaround for automated verification)

Create the workspace via REST for an owner who is ALREADY authenticated (for
example `austenplatform`). The admin token authorizes the request, but the
build uses the owner's GitLab token, so the gate is satisfied.

```bash
# Resolve the authenticated owner's user id.
curl -sS -H "Coder-Session-Token: $ADMIN_TOKEN" \
  "$CODER_URL/api/v2/users?q=austenplatform"

OWNER_ID="<id from above>"

curl -sS -X POST \
  -H "Coder-Session-Token: $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  "$CODER_URL/api/v2/users/$OWNER_ID/workspaces" \
  -d '{
    "template_id": "<template id>",
    "name": "<workspace name>",
    "rich_parameter_values": [
      {"name": "cpu", "value": "4"},
      {"name": "memory", "value": "8"},
      {"name": "disk_size", "value": "20"}
    ]
  }'
```

This returned HTTP 201 and built successfully this session. Use Remediation B
for the automated build matrix unless the operator is themselves an
authenticated owner, in which case CLI `coder create` is fine.

## 3. Enumerate templates and identify the gitlab gate

List templates in the `coder` org and capture id plus active version:

```bash
curl -sS -H "Coder-Session-Token: $ADMIN_TOKEN" \
  "$CODER_URL/api/v2/organizations/$ORG_ID/templates" \
  | python3 -c 'import sys,json; [print(t["name"], t["id"], t["active_version_id"]) for t in json.load(sys.stdin)]'
```

For each template, grep its `main.tf` for the external-auth gate:

```bash
cd /home/coder/demoenv-workspace/usgov-phase2/coder-templates
grep -Rl 'coder_external_auth' */main.tf
```

Record, per template, whether it requires gitlab auth. Verified this session:
`claude-code` and `platform-engineer` both declare the gitlab gate. Treat any
`claude-code`-derived template as gated until grep proves otherwise. Templates
without the gate can be built by any owner, including a freshly authenticated
test user.

## 4. Per-template build matrix

For each template, do the following:

1. Read the template's `coder_parameter` blocks in its `main.tf` to get the
   exact parameter names and acceptable values. Do not assume; parameters
   differ per template.
2. Decide the owner. If the template is gitlab-gated, use an authenticated
   owner (Remediation A) or the REST create-for-owner workaround (Remediation
   B). If ungated, any owner works.
3. Create the workspace. Use CLI when the operator is the authenticated owner:

   ```bash
   coder --url "$CODER_URL" --token "$ADMIN_TOKEN" \
     create <name> --template <template> \
     --parameter cpu=4 --parameter memory=8 --parameter disk_size=20 --yes
   ```

   Otherwise use the REST POST from Remediation B.
4. Poll to healthy:

   ```bash
   WS_ID="<workspace id from create response>"
   curl -sS -H "Coder-Session-Token: $ADMIN_TOKEN" \
     "$CODER_URL/api/v2/workspaces/$WS_ID" \
     | python3 -c 'import sys,json; d=json.load(sys.stdin); b=d["latest_build"]; print("build", b["status"], "job", b["job"]["status"])'
   ```

   Parse JSON with `strict=False` because some fields contain control
   characters. Repeat until `build` is `running` and `job` is `succeeded`.
   The agent is ready when `lifecycle_state=ready` and `status=connected` in
   the workspace resources.
5. Connectivity smoke test:

   ```bash
   coder --url "$CODER_URL" --token "$ADMIN_TOKEN" \
     ssh <owner>/<workspace> -- \
     bash -lc "curl -sS -o /dev/null -w '%{http_code}' $CODER_URL/api/v2/buildinfo"
   ```

   Expect `200`.
6. Record pass/fail in the results table (section 6).

Known parameters for `claude-code`-derived templates: `cpu` (default 4),
`memory` (default 8), `disk_size` (immutable, default 20), `ai_prompt`
(default ""). `platform-engineer` adds `git_repo` (optional, default ""). For
every other template, read its `coder_parameter` blocks and pass the required
parameters explicitly.

## 5. Cleanup guidance

After verification, optionally stop or delete the verification workspaces to
keep the deployment tidy:

```bash
coder --url "$CODER_URL" --token "$ADMIN_TOKEN" stop <owner>/<workspace> --yes
# or
coder --url "$CODER_URL" --token "$ADMIN_TOKEN" delete <owner>/<workspace> --yes
```

The `firewalled` template already has a validated workspace
`austenplatform/firewall-test`. Leave it running for the demo; do not delete
it during cleanup.

## 6. Results table (fill in)

| Template | Gitlab-gated | Owner used | Create method | Build status | Agent connected | Smoke HTTP | Pass/Fail | Notes |
|----------|--------------|------------|---------------|--------------|-----------------|------------|-----------|-------|
| ai-agent-generic |  |  |  |  |  |  |  |  |
| claude-code |  |  |  |  |  |  |  |  |
| claude-code-ci |  |  |  |  |  |  |  |  |
| cpp-engineer |  |  |  |  |  |  |  |  |
| data-scientist |  |  |  |  |  |  |  |  |
| java-engineer |  |  |  |  |  |  |  |  |
| platform-engineer |  |  |  |  |  |  |  |  |
| firewalled |  |  |  |  |  |  |  |  |

## 7. Risks and open questions

- Per-template egress: `platform-engineer` and similar templates run
  best-effort startup downloads (kubectl, helm, terraform from public
  endpoints). In a fully air-gapped boundary these may be blocked. A build can
  succeed while tooling installs silently fail. Note this when scoring.
- Image pull from ECR: templates default to the ECR-mirrored
  `codercom/enterprise-base`. A missing or mis-tagged mirror image causes the
  pod to fail to start. Check pod events if the build hangs in `pending`.
- GitLab token expiry: the owner's OAuth token is short-lived. If a previously
  authenticated owner's token has expired, builds gate again. Re-confirm with
  `GET /api/v2/external-auth/gitlab` before a batch run.
- Coder Tasks vs plain builds: `claude-code` wires `coder_ai_task` and the
  AgentAPI chat UI. Verifying a plain build proves the workspace path but not
  the full Task UI. Decide whether the demo needs Task-mode verification too.
- Parameter drift: immutable parameters such as `disk_size` cannot be changed
  after creation. Pick demo-representative values up front.

Generated by Coder Agents.
