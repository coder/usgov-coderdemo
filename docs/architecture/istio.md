# Istio service mesh

**Phase 2 only.** Do not block Phase 1 on Istio.

## Scope

- Mesh covers EKS Tier 0: coderd, provisioner, Keycloak, Grafana stack
- Istio ingress gateway = shared ingress (Phase 2)
- **`coder-workspaces` namespace: injection DISABLED v1**

## Coder gotchas (#1 failure mode: WebSockets)

Configure for long-lived WSS (agent, terminal, app proxy, DERP):

- Gateway/VirtualService: HTTP/1.1 upgrade
- Raise/disable idle timeouts on Gateway and DestinationRule
- Wildcard host `*.dev.usgov.coderdemo.io` + cert SNI

## mTLS rollout

`PeerAuthentication`: **PERMISSIVE → validate C1–C8 → STRICT**

## External traffic

- OCP provisioner → ingress gateway over TLS (north-south)
- Workspace pods → coderd egress without sidecar (v1)

## Bedrock egress (with WS-13)

When mesh on, coderd needs:

- `ServiceEntry` for `bedrock-runtime.us-gov-west-1.amazonaws.com`
- Egress policy allowlist or `ALLOW_ANY` during bring-up

## Reference

`reference/openshift-servicemesh-inventory-demo/`

## OCP side

OSSM mirror on OCP fabric is optional post-v1.
