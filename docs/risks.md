# Risk register

| ID | Risk | Mitigation |
|---|---|---|
| R1 | GovCloud account onboarding | G0.1 |
| R2 | Cross-partition DNS | Resolved: GovCloud R53 + NS delegation |
| R3 | EKS Auto Mode unavailable | `auto_mode=false`, MNG |
| R4 | OCP IPI multi-day | Start WS-11a early; G0.8 skip |
| R5 | Bedrock model IDs differ | G0.9 enumerate; rewrite allowlist |
| R6 | Hardcoded `arn:aws:` | partition data source |
| R7 | GPU unavailable | N/A v1 |
| R8 | Image egress | NAT + ECR pull-through |
| R9 | Coder version drift | versions.lock.yaml |
| R10 | EKS outage takes auth/metrics | RDS/S3 durable |
| R11 | GitLab SPOF | Accepted; S3 restore |
| R12 | Istio breaks WebSockets | Phase 2 only; direct ingress Phase 1 |
| R13 | Sidecar in workspace pods | injection disabled v1 |
| R14 | mTLS STRICT too early | PERMISSIVE → STRICT |
| R15 | FIPS Istio | document; out of scope v1 |
| R16 | ECR OCP node pull | node IAM / pull secret |
| R17 | TF lock contention | one agent per state key |
| R18 | Agent scope creep | bounded WS prompts |
| R19 | Blank repo | WS-00 mandatory |
| R20 | Session timeout | tmux; handoffs for resume |
| R21 | Reference drift | record commit SHA |
