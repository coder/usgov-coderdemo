# Pre-requisites (human)

Complete **before** launching the orchestrator or running `make gate-0`.

Automated check: [`../scripts/preflight-readiness.sh`](../scripts/preflight-readiness.sh)

```bash
mkdir -p ~/demoenv-workspace && cd ~/demoenv-workspace
git clone git@github.com:coder/usgov-coderdemo.git
source ~/.config/usgov-coderdemo/env
./usgov-coderdemo/scripts/preflight-readiness.sh --clone   # first time
./usgov-coderdemo/scripts/preflight-readiness.sh           # verify only
```

---

## 1. Workspace layout

```text
~/demoenv-workspace/
├── usgov-coderdemo/     # this repo (WRITE)
│   ├── PLAN.md
│   ├── docs/
│   └── scripts/
└── reference/           # READ-ONLY — clone with --clone or manually
    ├── coder-eks-deployment/
    ├── demo-aigov-rhsummit-2026/
    ├── homelab/
    └── openshift-servicemesh-inventory-demo/
```

---

## 2. Environment file

Create `~/.config/usgov-coderdemo/env`:

```bash
export AWS_PROFILE=demoenv-usgov
export AWS_DEFAULT_REGION=us-gov-west-1
export AWS_COMMERCIAL_PROFILE=coderdemo-commercial
export CODER_LICENSE=<paste-license>
export DEMOENV_WORKSPACE_ROOT=~/demoenv-workspace
export REFERENCE_ROOT=$DEMOENV_WORKSPACE_ROOT/reference
export DEMOENV_ROOT=$DEMOENV_WORKSPACE_ROOT/usgov-coderdemo
```

| Variable | Required | Used for |
|---|---|---|
| `AWS_PROFILE` / GovCloud creds | yes | All TF/AWS workstreams |
| `AWS_COMMERCIAL_PROFILE` | yes | G0.3 NS delegation (WS-01) |
| `CODER_LICENSE` | yes | WS-07 |
| `REFERENCE_ROOT` | yes | Read-only copy sources |
| `RH_PULL_SECRET` | WS-11 only | OCP IPI |
| `DOCKERHUB_TOKEN` | optional | ECR pull-through |
| `GITLAB_ROOT_PASSWORD` | optional | WS-10 |

---

## 3. Reference repo clones

**Read-only.** Agents copy/adapt; never commit changes here.

| Directory under `$REFERENCE_ROOT` | Clone URL |
|---|---|
| `coder-eks-deployment/` | `https://github.com/ausbru87/coder-eks-deployment.git` |
| `demo-aigov-rhsummit-2026/` | `https://github.com/coder/demo-aigov-rhaiis-rhsummit-2026.git` |
| `homelab/` | `https://github.com/ausbru87/homelab.git` |
| `openshift-servicemesh-inventory-demo/` | `https://github.com/ausbru87/openshift-servicemesh-inventory-demo.git` |

Manual clone (from `~/demoenv-workspace/`):

```bash
mkdir -p reference && cd reference
git clone https://github.com/ausbru87/coder-eks-deployment.git
git clone https://github.com/coder/demo-aigov-rhaiis-rhsummit-2026.git demo-aigov-rhsummit-2026
git clone https://github.com/ausbru87/homelab.git
git clone https://github.com/ausbru87/openshift-servicemesh-inventory-demo.git
```

Or: `preflight-readiness.sh --clone`

See [architecture/reference-repos.md](architecture/reference-repos.md) for copy targets.

---

## 4. CLI tools

| Tool | Minimum | Notes |
|---|---|---|
| `aws` | v2 | GovCloud + commercial profiles |
| `git` | 2.x | |
| `terraform` | ≥ 1.9 | per `versions.lock.yaml` (WS-00) |
| `kubectl` | matches EKS | after WS-04 |
| `helm` | 3.x | WS-05+ |
| `claude` | ≥ 2.1.154 | Opus 4.8, ultracode |
| `tmux` | any | overnight runs |
| `curl` | any | connectivity validation |

---

## 5. AWS access checks

```bash
source ~/.config/usgov-coderdemo/env
aws sts get-caller-identity --region us-gov-west-1
aws sts get-caller-identity --profile "$AWS_COMMERCIAL_PROFILE"
```

---

## 6. Readiness gate

```bash
cd ~/demoenv-workspace
source ~/.config/usgov-coderdemo/env
./usgov-coderdemo/scripts/preflight-readiness.sh    # exit 0 required
```

Then (after WS-00 creates Makefile):

```bash
cd usgov-coderdemo
make gate-0
```

---

## 7. Runtime session

```bash
tmux new -s usgov-coderdemo
cd ~/demoenv-workspace/usgov-coderdemo
source ~/.config/usgov-coderdemo/env
export KUBECONFIG=$PWD/kubeconfig
claude --model opus --effort ultracode
```

---

## Never commit

`.env`, `kubeconfig`, license keys, pull secrets, Terraform state, `.terraform/`
