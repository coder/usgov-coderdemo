# Connectivity matrix

Validate with `scripts/validate-connectivity.sh`.

| ID | Path | Phase | Check |
|---|---|---|---|
| **C1** | Coder UI | 1 | `curl -sfI https://dev.usgov.coderdemo.io` |
| **C2** | Web terminal | 1 | Open terminal in workspace (WSS) |
| **C3** | Workspace apps | 1 | `*.dev.usgov.coderdemo.io` loads |
| **C4** | Agent ↔ coderd | 1 | Workspace status Connected |
| **C5** | EKS workspace proxy | 1 | App via `aws.usgov.coderdemo.io` |
| **C6** | OCP workspace proxy | 3 | App via `ocp.usgov.coderdemo.io` |
| **C7** | OCP provisioner | 3 | Registered; build succeeds |
| **C8** | DERP relay | 1/2 | Agent connects if direct WS fails |
| **C9** | Keycloak OIDC | 1 | Login via Keycloak |
| **C10** | Grafana | 2 | `metrics.usgov.coderdemo.io` |
| **C11** | GitLab | 2 | git clone/push |
| **C12** | Bedrock AI Bridge | 4 | Completion in workspace |
| **C13** | ECR pull | 1 | docker pull via IRSA in workspace |
| **C14** | ECR pull-through | 1 | devcontainer base build |

## Track A script

`validate-connectivity.sh --track a` → C1, C2, C3, C4, C5, C9, C13, C14

## Track all

`validate-connectivity.sh --track all` → C1–C14

## Troubleshooting

| Symptom | Check |
|---|---|
| C4 fail, C1 pass | C8 DERP / relay config |
| C2 fail after Istio | R12 WebSocket timeouts on Gateway/VS |
| C12 fail after Istio | Bedrock ServiceEntry + egress policy |
| C3 fail | Wildcard DNS + cert SAN |

## When to run

- WS-05 handoff: C1 minimum
- WS-08 handoff: C1–C5, C9, C13, C14
- WS-09 before DNS flip: C1–C8
- Phase 1 done: `make validate-track-a`
