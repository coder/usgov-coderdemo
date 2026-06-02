# Target architecture (v1)

```
GovCloud R53: usgov.coderdemo.io  (NS-delegated from commercial coderdemo.io)
                    |
    +---------------+----------------+------------------+
    |               |                |                  |
dev/auth/metrics   gitlab.usgov    aws.usgov...     ocp.usgov...
*.dev.usgov        (EC2 ALB)       (EKS proxy)      (OCP proxy)

┌──────────── AWS GovCloud us-gov-west-1 ─────────────────────────────────────┐
│                                                                              │
│  EKS Tier 0 (control + EKS fabric)                                          │
│    Phase 1: NLB → coderd (direct)                                           │
│    Phase 2: NLB → istio-ingressgateway → VirtualServices                     │
│    Coder HA | Keycloak | Grafana/Prom/Loki                                   │
│    EKS provisioner (platform=eks) + workspace proxy                          │
│    coder-workspaces ns (istio-injection=DISABLED)                            │
│    cert-manager | External Secrets | IRSA                                    │
│                                                                              │
│  RDS PG17 Multi-AZ (coder, keycloak) | S3 | ECR                              │
│                                                                              │
│  EC2: GitLab Omnibus (SPOF; data → S3)                                       │
│                                                                              │
│  OCP IPI cluster (workspace fabric only)                                     │
│    external provisioner (platform=ocp) + workspace proxy                     │
│    NO in-cluster Coder | NO RHAIIS/GPU v1                                     │
│                                                                              │
│  AI Bridge → Bedrock (Phase 4, IRSA)                                         │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Fabric routing

Templates declare `platform=eks` or `platform=ocp`. Provisioner keys use matching tags. One Coder CP governs both.

## Why this shape

- Single audit/governance plane
- EKS + RDS survives OCP rebuild
- Red Hat runway preserved on OCP fabric
