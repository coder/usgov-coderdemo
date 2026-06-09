# Data-store MCP (`deploy/datastore-mcp/`)

A read-only Model Context Protocol (MCP) server over a small, synthetic,
UNCLASSIFIED Postgres "analytic data store", registered with **Coder Agents**
(the control-plane agentic chat) via the admin "MCP Servers" configuration so
the agent can query a federated data source through MCP. It demonstrates the
AOI "federated data integration / dynamically registered data sources via MCP"
capability.

This intentionally uses the supported Coder Agents MCP path and NOT the AI
Gateway's injected-MCP mechanism, which is deprecated upstream.

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

## Register with Coder Agents (`/api/experimental/mcp/servers`)

The MCP server is registered as an `auth_type: none`, `streamable_http` server
that coderd reaches in-cluster (no per-user OAuth needed). Configure it from
Admin Settings -> MCP Servers, or via the API:

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

This is a live API object (DB-resident, not in git). In a Coder Agents chat
the tools appear as `datastore__list_tables`, `datastore__describe_table`,
`datastore__query`.

## Verify

Start a Coder Agents chat that has the Demo Data Store server enabled and ask
it to query the data (for example, "how many reports per region?"). The agent
calls `datastore__list_tables` / `datastore__describe_table` /
`datastore__query` and returns the real rows. Verified live: a chat invoked
all three tools and returned the per-region report counts.

## Notes / known follow-ups

- Uses the supported Coder Agents MCP path; the AI Gateway injected-MCP
  mechanism (External Auth `MCP_URL`, `CODER_AI_GATEWAY_INJECT_CODER_MCP_TOOLS`)
  is deprecated upstream and is deliberately NOT used here.
- The Coder Agents "MCP Servers" config is a live, DB-resident API object, not
  captured in git. A future idempotent reconciler (git desired-state ->
  `/api/experimental/mcp/servers`) would make it reproducible like the AI
  providers.
- The demo Postgres uses an `emptyDir`, so data resets on pod restart (the
  seed reloads). That is intentional for a throwaway demo store.
- The custom MCP image is built locally and pushed to ECR; it is not part of
  `scripts/images.txt` (that list is for upstream mirrors).
