# Repository layout

WS-00 creates this structure in `github.com/coder/usgov-coderdemo`.

```
usgov-coderdemo/
├── PLAN.md
├── README.md
├── Makefile
├── versions.lock.yaml
├── .env.example
├── .gitignore
├── kubeconfig                 # gitignored
├── terraform/
│   ├── modules/
│   │   └── partition/         # aws-us-gov provider + partition data source
│   ├── bootstrap/             # WS-01
│   ├── network/               # WS-02
│   ├── data/                  # WS-03
│   ├── eks/                   # WS-04
│   ├── eks-apps/              # WS-05
│   ├── platform-eks/          # WS-06
│   ├── eks-day2/              # WS-07
│   ├── istio/                 # WS-09
│   ├── platform-ec2/          # WS-10
│   ├── ocp/                   # WS-11
│   ├── identity/              # WS-12
│   └── ai/                    # WS-13
├── gitops/                    # OCP Argo apps
├── manifests/                 # OCP cluster manifests
├── coder-templates/
├── scripts/
│   ├── gate-0-check.sh
│   ├── validate-connectivity.sh
│   ├── tf-apply.sh
│   └── lib/common.sh
└── docs/
    ├── architecture/
    ├── swarm/
    │   ├── handoffs/          # WS-*-handoff.md written at runtime
    │   └── workstreams/
    ├── decisions.md           # provenance log (runtime)
    └── runbooks/
```

## Makefile targets (WS-00 creates)

| Target | Purpose |
|---|---|
| `make gate-0` | Hard gates G0.1–G0.12 |
| `make scaffold` | Init skeleton only |
| `make apply-bootstrap` … `make apply-eks-day2` | Track A TF order |
| `make kubeconfig` | Write `./kubeconfig` |
| `make validate-track-a` | C1–C5, C9, C13–C14 |
| `make validate-all` | Full C1–C14 |

## versions.lock.yaml

All agents read versions from this file only. Orchestrator pins Coder version at G0.7 before fan-out.

```yaml
coder:
  version: "2.33.x"
  helm_chart: "2.x.x"
kubernetes: "1.31"
terraform: ">= 1.9"
postgres: "17"
istio: "1.24.x"
openshift: "4.17"
region: us-gov-west-1
partition: aws-us-gov
domain: usgov.coderdemo.io
ingress_mode: direct
```
