# Credentials and runtime env

**Human setup (clone repos, tools, AWS):** [PRE-REQUISITES.md](../PRE-REQUISITES.md)  
**Automated check:** [`../../scripts/preflight-readiness.sh`](../../scripts/preflight-readiness.sh)

## Env file

Create `~/.config/usgov-coderdemo/env` (or copy `.env.example` → `.env`):

```bash
export AWS_PROFILE=demoenv-usgov
export AWS_DEFAULT_REGION=us-gov-west-1
export AWS_COMMERCIAL_PROFILE=coderdemo-commercial
export CODER_LICENSE=
export REFERENCE_ROOT=$DEMOENV_WORKSPACE_ROOT/reference
export DEMOENV_ROOT=$DEMOENV_WORKSPACE_ROOT/usgov-coderdemo
```

See [PRE-REQUISITES.md](../PRE-REQUISITES.md) for full variable list, clone URLs, and `preflight-readiness.sh`.

## Required secrets

| Var | Used by |
|---|---|
| GovCloud AWS creds | All TF/AWS WS |
| `AWS_COMMERCIAL_PROFILE` | G0.3 NS delegation (WS-01) |
| `CODER_LICENSE` | WS-07 |

## Pre-flight (human, before orchestrator)

```bash
cd ~/demoenv-workspace
source ~/.config/usgov-coderdemo/env
./scripts/preflight-readiness.sh --clone   # first time
./scripts/preflight-readiness.sh           # must exit 0
```

## Runtime

```bash
cd ~/demoenv-workspace/usgov-coderdemo
source ~/.config/usgov-coderdemo/env
export KUBECONFIG=$PWD/kubeconfig
```

## tmux

```bash
tmux new -s usgov-coderdemo
# disable laptop sleep
```

## Never commit

`.env`, `kubeconfig`, license keys, pull secrets, TF state, `.terraform/`
