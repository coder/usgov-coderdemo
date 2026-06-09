# Data-store MCP (`deploy/datastore-mcp/`)

A read-only Model Context Protocol (MCP) server over a small, synthetic,
UNCLASSIFIED Postgres "analytic data store", wired into the Coder AI Gateway
so its tools are **injected and governed at the gateway** (every call is
recorded in `aibridge_tool_usages` with `injected=true` and `server_url` set).
It demonstrates the AOI "federated data integration / dynamically registered
data sources via MCP" capability with full central governance.

## Pieces

| Piece | What |
|---|---|
| `server/` | A ~250-line Go Streamable-HTTP MCP server (`mark3labs/mcp-go` v0.38.0, the same SDK the gateway client uses). Read-only: connects as a least-privilege role, allows only a single `SELECT`/`WITH` per `query`, runs in a read-only transaction with an 8s statement timeout, caps rows at 200. Tools: `list_tables`, `describe_table`, `query`. |
| `server/Dockerfile` | Multi-stage build to a distroless static image (no Node, no shell). |
| `k8s/seed.sql` | Synthetic demo dataset (regions, entities, reports) plus a `mcp_ro` read-only role. |
| `k8s/*.yaml` + `kustomization.yaml` | Namespace `coder-demo-mcp`, the demo Postgres (ephemeral, reseeded each start), and the MCP Deployment/Service. |

## Image (built by us, not an upstream mirror)

```sh
cd deploy/datastore-mcp/server
docker build -t 430737322961.dkr.ecr.us-gov-west-1.amazonaws.com/usgov/datastore-mcp:0.1.0 .
aws ecr get-login-password --region us-gov-west-1 \
  | docker login --username AWS --password-stdin 430737322961.dkr.ecr.us-gov-west-1.amazonaws.com
docker push 430737322961.dkr.ecr.us-gov-west-1.amazonaws.com/usgov/datastore-mcp:0.1.0
```

## Deploy

```sh
kubectl apply -k deploy/datastore-mcp/k8s
```

The demo Postgres holds only synthetic data and is ClusterIP-only. The
credentials in `kustomization.yaml` are demo-only and intentionally low value.

## Gateway wiring (in `deploy/coder/values.yaml`)

The MCP server is registered as a Coder **External Auth** app
(`CODER_EXTERNAL_AUTH_1_*`, id `datastore`) backed by Keycloak realm `coder`,
with `MCP_URL` pointing at the in-cluster Service and **no `VALIDATE_URL`**
(so Coder's `ValidateToken` returns true while the user's link is unexpired;
the MCP server does not check the bearer the gateway forwards). The Keycloak
client `coder-datastore` has its access-token lifespan raised to 10h to avoid
the gateway's no-refresh token-expiry behaviour on long demos.

Client id/secret live in ASM `usgov-coderdemo/coder/external-auth` (keys
`datastore-client-id`, `datastore-client-secret`) and are synced by ESO into
the `coder-external-auth` Secret, keeping ASM the single source of truth.

## Using it in the demo

The data-store MCP is available on three surfaces, all governed/attributed:

### A. Coder Agents (control-plane chat) via the "MCP Servers" admin page

Registered as an `auth_type: none`, `streamable_http` server that coderd
reaches in-cluster (no per-user OAuth needed). Reproduce the live object
(Admin Settings -> MCP Servers, or API):

```sh
curl -X POST "$CODER_URL/api/experimental/mcp/servers" \
  -H "Coder-Session-Token: $TOKEN" -H "Content-Type: application/json" \
  --data '{
    "display_name": "Demo Data Store",
    "slug": "datastore",
    "description": "Read-only analytic demo data store (synthetic, unclassified).",
    "transport": "streamable_http",
    "url": "http://datastore-mcp.coder-demo-mcp.svc.cluster.local:8000/mcp",
    "auth_type": "none",
    "availability": "default_on",
    "enabled": true,
    "model_intent": true,
    "allow_in_plan_mode": true
  }'
```

This is a live API object (not in git). In a Coder Agents chat the tools
appear as `datastore__list_tables`, `datastore__describe_table`,
`datastore__query`. Verified live: a chat invoked all three and returned the
real per-region report counts.

### B. AI Gateway injection (in-workspace Claude Code / aibridge messages)

1. The user authenticates the **Demo Data Store** provider once at
   `https://dev.usgov.coderdemo.io/external-auth/datastore` (standard External
   Auth connect, redirects to Keycloak).
2. After that, any AI Gateway request by that user (Coder Agents chat or
   Claude Code in a workspace) has the data-store tools injected as
   `bmcp_datastore_list_tables`, `bmcp_datastore_describe_table`,
   `bmcp_datastore_query`.
3. Every call is recorded with `injected=true` and
   `server_url=http://datastore-mcp.coder-demo-mcp.svc.cluster.local:8000/mcp`,
   visible in the AI Gateway governance dashboard
   ("MCP Servers & Tool Sources").

## Verify

```sql
SELECT tool, server_url, injected, count(*)
FROM aibridge_tool_usages
WHERE server_url LIKE '%datastore-mcp%'
GROUP BY 1,2,3;
```

## Notes / known follow-ups

- Gateway-side injected MCP is marked **deprecated** upstream (functional,
  security-only patches) until the replacement ships. Fine for the demo.
- The demo Postgres uses an `emptyDir`, so data resets on pod restart (the
  seed reloads). That is intentional for a throwaway demo store.
- The custom MCP image is built locally and pushed to ECR; it is not part of
  `scripts/images.txt` (that list is for upstream mirrors).
