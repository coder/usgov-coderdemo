# Architecture

The environment runs entirely inside the AWS GovCloud boundary
(`us-gov-west-1`, account `430737322961`). Public traffic enters through
Route53, terminates TLS at an NLB with the `*.usgov.coderdemo.io` ACM
certificate, and reaches workloads on the EKS cluster `usgov-coderdemo`.

## Two ingress edges

There are two load balancers in front of the cluster, and DNS decides which one
a given host uses.

| Edge | NLB | Hosts in the DNS path |
|---|---|---|
| Istio ingress gateway | `k8s-istiosys-...elb.us-gov-west-1.amazonaws.com` | `dev`, `auth`, `gitlab`, `grafana`, `kiali`, registry, and the `*` wildcard |
| ingress-nginx | `k8s-ingressn-...elb.us-gov-west-1.amazonaws.com` | `envdocs` (this site) only, via an explicit Route53 alias |

The Route53 wildcard `*.usgov.coderdemo.io` aliases to the Istio gateway NLB, so
the core stack is served through Istio with mesh-wide STRICT mTLS. ingress-nginx
is retained as a per-host rollback path and is otherwise out of the DNS path.
This documentation site is the deliberate exception: an explicit
`envdocs.usgov.coderdemo.io` alias points at the ingress-nginx NLB (a more
specific record wins over the wildcard), because the auth gate for this site is
built from ingress-nginx external-auth annotations and oauth2-proxy. See
[Access and auth gate](access-and-auth.md).

## Topology

```mermaid
flowchart TB
  user(["Demo user / browser"])

  subgraph gov["AWS GovCloud us-gov-west-1 / account 430737322961"]
    r53["Route53 zone usgov.coderdemo.io"]
    nlbI["Istio gateway NLB<br/>ACM *.usgov.coderdemo.io"]
    nlbN["ingress-nginx NLB<br/>ACM *.usgov.coderdemo.io"]

    subgraph eks["EKS cluster usgov-coderdemo / k8s 1.36"]
      igw["Istio ingress gateway<br/>ns istio-system"]
      nginx["ingress-nginx controller<br/>ns ingress-nginx"]
      coder["Coder control plane<br/>ns coder / v2.34.0"]
      kc["Keycloak<br/>ns keycloak / realm coder"]
      gl["GitLab CE<br/>ns gitlab / embedded Postgres"]
      ws["Workspace pods<br/>ns coder-workspaces<br/>Claude Code agent"]
      o2p["oauth2-proxy<br/>ns envdocs"]
      docs["MkDocs site (nginx)<br/>ns envdocs"]
    end

    rds[("RDS PostgreSQL 18.4<br/>dbs coder + keycloak")]
    bedrock["Amazon Bedrock"]
    nat["NAT gateway"]
  end

  anthropic(["api.anthropic.com"])

  user --> r53
  r53 -->|"dev / auth / gitlab / *"| nlbI --> igw
  r53 -->|"envdocs"| nlbN --> nginx
  igw -->|mTLS| coder
  igw -->|mTLS| kc
  igw -->|mTLS| gl
  nginx -->|"auth subrequest"| o2p
  o2p -->|OIDC| kc
  nginx --> docs
  coder --> rds
  kc --> rds
  coder -->|"IRSA role coder-bedrock"| bedrock
  coder -->|"AI Bridge egress"| nat --> anthropic
  coder --> ws
  ws -->|"session token"| coder
```

## Core flow A: SSO login to Coder

```mermaid
sequenceDiagram
  participant U as Browser
  participant C as Coder (dev.)
  participant K as Keycloak (auth., realm coder)
  U->>C: Open dev.usgov.coderdemo.io, click "Sign in with Keycloak"
  C->>K: Redirect to /realms/coder authorize (client_id coder)
  K-->>U: Login page (realm coder)
  U->>K: Credentials
  K-->>C: Redirect to /api/v2/users/oidc/callback with code
  C->>K: Exchange code (server-side, valid TLS via in-cluster hairpin)
  K-->>C: ID token (email, preferred_username, groups)
  C-->>U: Session established, org/group/role applied by runtime IdP sync
```

On login Coder runs three IdP sync passes (organization, group, role) keyed on a
single full-path `groups` claim, placing the user in the correct Coder
organization(s), groups, and roles with no manual assignment. See
[Identity (Keycloak)](identity-keycloak.md).

## Core flow B: workspace create, GitLab auth, agent, AI

```mermaid
flowchart LR
  A["User creates workspace<br/>from claude-code template"] --> B["Coder requires<br/>GitLab external auth"]
  B --> C["In-boundary GitLab<br/>OAuth authorize/token"]
  C --> D["Provisioner builds pod<br/>ns coder-workspaces"]
  D --> E["Agent connects<br/>Claude Code + AgentAPI + code-server"]
  E --> F["git clone/push via<br/>short-lived GitLab token"]
  E --> G["Claude Code POST<br/>/api/v2/aibridge/anthropic"]
  G --> H{"AI Gateway<br/>route by name"}
  H -->|anthropic| I["api.anthropic.com<br/>via NAT gateway"]
  H -->|anthropic-bedrock| J["Amazon Bedrock<br/>in-region via IRSA"]
```

The workspace agent never holds a raw model key. Claude Code authenticates to
the AI Gateway with the workspace owner's Coder session token, and the gateway
applies governance and audit before forwarding to the named provider. See
[AI Gateway](ai-gateway.md).

## ASCII summary

```text
            Internet
               |
        Route53 (usgov.coderdemo.io)
          /                       \
   Istio gateway NLB        ingress-nginx NLB
   (dev/auth/gitlab/*)      (envdocs only)
          |                       |
   Istio ingress gw         ingress-nginx
    /     |     \                 |
 Coder Keycloak GitLab      oauth2-proxy -> Keycloak (OIDC)
    |      |                      |
    +------+--> RDS 18.4     MkDocs site (nginx)
    |
    +--> coder SA -> Bedrock (IRSA, in-region, no static key)
    +--> AI Bridge -> NAT gateway -> api.anthropic.com
    |
    +--> workspace pods (coder-workspaces) -> back to Coder via session token
```

## Where to go next

- [Coder control plane](coder-control-plane.md)
- [Identity (Keycloak)](identity-keycloak.md)
- [GitLab SCM](gitlab.md)
- [AI Gateway](ai-gateway.md)
- [Observability](observability.md)
- [Secrets](secrets.md)
