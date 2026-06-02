# Parallelization map

## Never parallelize

| Rule | Reason |
|---|---|
| One TF apply per state key | DynamoDB lock |
| WS-01 before WS-02 | state backend |
| WS-02 before WS-03/04/10/11 | VPC |
| WS-03 before WS-04/06 | RDS |
| WS-04 before WS-05/06 | kubeconfig |
| WS-05 before WS-07 | coderd API |
| WS-07 before WS-08 | provisioner registered |
| WS-09 after WS-05 PASS | Istio baseline |

## Waves

### Wave 0 — GATE-0 + WS-00

- Parallel: gate probes (10 agents), scaffold (20 agents) — see WS-00
- Serial: orchestrator merges

### Wave 1 — WS-01 (1 apply)

State: `bootstrap/`

### Wave 2 — WS-02 (1 apply)

State: `network/`  
Author parallel: SA-2-EKS-VPC, SA-2-OCP-VPC, SA-2-PEER → one apply

### Wave 3 — up to 3 applies

| WS | State | After |
|---|---|---|
| WS-03 | `data/` | WS-02 |
| WS-10 | `platform-ec2/` | WS-02 + WS-03 S3 |
| WS-11a | `ocp/` | WS-02, G0.8 |

Start **WS-11a here** (hours-long background).

### Wave 3b — code-only (unlimited)

Run anytime after WS-00:

| SA | Task |
|---|---|
| SA-COPY-EKS | Adapt coder-eks-deployment |
| SA-COPY-OCP | Adapt demo-aigov |
| SA-COPY-HOMELAB | Adapt homelab identity |
| SA-COPY-MESH | Adapt istio patterns |
| SA-AUTH-WS* | Author TF/Helm without apply |
| SA-DOCS | architecture, decisions, runbooks |

### Wave 4 — WS-04 (1 apply)

State: `eks/`  
Continue Wave 3b while cluster creates.

### Wave 5 — up to 2 applies

| WS | State |
|---|---|
| WS-05 | `eks-apps/` |
| WS-06 | `platform-eks/` |

Stagger helm 5 min.

### Wave 6 — WS-07 (1 apply)

State: `eks-day2/`

### Wave 7 — WS-08 (1 agent)

Coder template publish (API/TF).

### Wave 8 — Track B (up to 5 applies)

After Phase 1 PASS:

| WS | State | Needs |
|---|---|---|
| WS-09 | `istio/` | WS-05 PASS |
| WS-10 | `platform-ec2/` | if not done |
| WS-11c/d | OCP k8s | WS-11a READY |
| WS-12 | `identity/` | WS-06, WS-05 |
| WS-13 | `ai/` | G0.9, WS-05 |

## WS-11 split

| ID | Task | When |
|---|---|---|
| WS-11a | OCP IPI apply | Wave 3 |
| WS-11b | gitops/manifests author | Wave 3b |
| WS-11c | OCP provisioner | cluster READY |
| WS-11d | OCP workspace proxy | after 11c |
| WS-11e | UBI9 → ECR | after WS-01 |
| WS-11f | OCP template | after 11c/d |

## WS-05 split (author parallel, one apply)

SA-5-CODER, SA-5-ES, SA-5-OBS (OBS optional defer)

## WS-12 split

SA-12-KC-CLIENTS first → then SA-12-CODER-SYNC, SA-12-GRAFANA-OIDC, SA-12-GITLAB-OIDC in parallel

## Concurrency limits

| Resource | Max |
|---|---|
| TF applies | 3–4 |
| EKS mutators | 1–2 |
| Authors | unlimited |

## Critical path

```
GATE-0 → WS-01 → WS-02 → WS-03 → WS-04 → WS-05 → WS-07 → WS-08
```

See [STATE-KEYS.md](STATE-KEYS.md) for ownership.
