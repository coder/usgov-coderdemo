# AGENT-PRD — usgov-coderdemo

> **Agent entry point.** Dense spec. Detail: `docs/swarm/workstreams/WS-NN-*.md`. Orchestrator: `docs/swarm/ORCHESTRATOR.md`.

## META

| k | v |
|---|---|
| target_repo | `github.com/coder/usgov-coderdemo` |
| cwd_writes | `usgov-coderdemo/` only |
| region | `us-gov-west-1` |
| partition | `aws-us-gov` |
| domain | `usgov.coderdemo.io` |
| ref_root | `$REFERENCE_ROOT` default `../reference/` |
| cc_min | v2.1.154+ (Opus 4.8, ultracode) |

## REF_MAP — include in context

Plan **requires** reference clones for copy/adapt. Does **not** duplicate their contents. Agents read paths below; never write to `$REFERENCE_ROOT`.

| clone | upstream | copy → usgov-coderdemo |
|---|---|---|
| `coder-eks-deployment/` | `ausbru87/coder-eks-deployment` | `terraform/eks`, `eks-apps`, `eks-day2`, obs modules |
| `demo-aigov-rhsummit-2026/` | `coder/demo-aigov-rhaiis-rhsummit-2026` | `terraform/ocp`, `platform-ec2`, `gitops/`, Bedrock IRSA |
| `homelab/` | `ausbru87/homelab` | Keycloak TF, Coder idp-sync, provisioner tags |
| `openshift-servicemesh-inventory-demo/` | `ausbru87/openshift-servicemesh-inventory-demo` | `terraform/istio` patterns |

**Adapt every copy:** `region=us-gov-west-1`, `partition=aws-us-gov`, domain swap, `data.aws_partition.current.partition` (no `arn:aws:` hardcode R6), Coder version from lock, drop GPU/RHAIIS/in-cluster Coder from OCP material. Log SHA + files in handoff + `docs/decisions.md`.

## HOSTS

| svc | host | where |
|---|---|---|
| coder | `dev.usgov.coderdemo.io` | EKS |
| keycloak | `auth.usgov.coderdemo.io` | EKS |
| grafana | `metrics.usgov.coderdemo.io` | EKS |
| gitlab | `gitlab.usgov.coderdemo.io` | EC2 |
| eks_proxy | `aws.usgov.coderdemo.io` | EKS |
| ocp_proxy | `ocp.usgov.coderdemo.io` | OCP |
| ecr | `*.dkr.ecr.us-gov-west-1.amazonaws.com` | ECR |

## LOCKED

- 1 Coder CP @ `dev.*`; 2 fabrics (EKS + OCP) each: external provisioner + workspace proxy
- CP on EKS + RDS PG17 Multi-AZ; OCP = rebuildable fabric only (~75m IPI), not CP host
- Phase1 ingress: `ingress_mode=direct` NLB+ACM→coderd; Istio Phase2 only; keep NLB for rollback
- Istio: EKS Tier0 platform NS only; `coder-workspaces` istio-injection=disabled; mTLS PERMISSIVE→STRICT
- DNS: GovCloud R53 `usgov.coderdemo.io` NS-delegated from commercial `coderdemo.io`; ACM/cert-manager DNS-01 in-partition
- Registry: ECR only + pull-through (DH/GHCR/quay); workspace pull via IRSA
- Identity: Keycloak realm `usgov`; Phase1 minimal OIDC (WS-06); full sync Phase2 (WS-12)
- Network: EKS VPC `10.0.0.0/16`, OCP VPC separate (e.g. `10.1.0.0/16`), peering

## OOS v1

RHAIIS/GPU, GitLab HA, Harbor, workspace sidecars, OSSM-on-OCP, FIPS Istio builds, air-gap/ATO, GitLab→WS bridge, EC2 template

## CONST — versions.lock.yaml

Read only this file for versions. Orch pins Coder @ G0.7 before fan-out.

`coder.version`, `coder.helm_chart`, `kubernetes`, `terraform`, `postgres`, `istio`, `openshift`, `region`, `partition`, `domain`, `ingress_mode=direct`

## ENV

Human preflight: [PRE-REQUISITES.md](PRE-REQUISITES.md) + `scripts/preflight-readiness.sh` (exit 0).

```bash
source ~/.config/usgov-coderdemo/env  # or .env
export KUBECONFIG=$PWD/kubeconfig
export REFERENCE_ROOT=${REFERENCE_ROOT:-../reference}
```

Required: GovCloud creds, `AWS_COMMERCIAL_PROFILE` (G0.3/WS-01), `CODER_LICENSE` (WS-07). Never commit secrets/kubeconfig/.env.

## RULES

1. 1 WS per subagent (or named SA-*)
2. 1 TF apply agent per state key; `./scripts/tf-apply.sh`; abort unexpected destroys
3. Read: `decisions-locked.md`, your WS-NN md, upstream handoffs
4. Handoff required: `docs/swarm/handoffs/WS-NN-handoff.md` (no file = FAIL)
5. Commit: `ws-NN: summary` on branch `ws-NN/desc`
6. Max 1 retry/WS/night; no `force-unlock` without orch approval in SWARM-STATUS
7. EKS helm/kubectl: stagger 5m+ or separate NS
8. Provenance in handoff: ref repo@SHA, files, adaptations

## STATE_KEYS

| key | path | WS | ph |
|---|---|---|---|
| bootstrap/ | terraform/bootstrap/ | 01 | 1 |
| network/ | terraform/network/ | 02 | 1 |
| data/ | terraform/data/ | 03 | 1 |
| eks/ | terraform/eks/ | 04 | 1 |
| eks-apps/ | terraform/eks-apps/ | 05 | 1 |
| platform-eks/ | terraform/platform-eks/ | 06 | 1 |
| eks-day2/ | terraform/eks-day2/ | 07 | 1 |
| istio/ | terraform/istio/ | 09 | 2 |
| platform-ec2/ | terraform/platform-ec2/ | 10 | 2 |
| ocp/ | terraform/ocp/ | 11a | 3 |
| identity/ | terraform/identity/ | 12 | 2 |
| ai/ | terraform/ai/ | 13 | 4 |

Output chain: 01→bucket,zone,ecr | 02→vpc,subnets | 03→rds,s3 | 04→cluster,oidc,kubeconfig | 05→coder_url,nlb | 06→keycloak_url | 07→provisioner,proxy

## DEPS (hard)

```
GATE-0 → 00 → 01 → 02 → 03 → 04 → 05 → 07 → 08 → validate-track-a
06 ∥ 05 (diff state) | 11a after 02 (background) | 09 after 05 PASS
07 blocks 08 | 04 blocks 05,06
```

## WAVES

| w | apply | parallel notes |
|---|---|---|
| 0 | — | G0 probes ∥ WS-00 scaffold; orch merge |
| 1 | 01 | |
| 2 | 02 | author: SA-2-EKS-VPC, SA-2-OCP-VPC, SA-2-PEER |
| 3 | 03,10,11a | ≤3 applies; start 11a (long) |
| 3b | — | SA-COPY-*, SA-AUTH-*, SA-DOCS unlimited |
| 4 | 04 | 3b continues |
| 5 | 05,06 | stagger helm 5m |
| 6 | 07 | |
| 7 | 08 | template publish (API) |
| 8 | 09–13 | after Phase1 PASS |

Concurrency: TF applies ≤3–4; EKS mutators ≤1–2; authors unlimited.

## GATES G0

Hard fail → STOP. Soft → skip flag `docs/swarm/gate-0-skips.yaml`.

| id | check | soft? |
|---|---|---|
| G0.1 | sts govcloud | |
| G0.2 | quotas EKS/EC2/VPC/EIP/RDS | |
| G0.3 | NS delegation commercial→gov | partial block WS-01 |
| G0.4 | ACM *.usgov.coderdemo.io | |
| G0.5 | EKS Auto Mode or MNG path | |
| G0.6 | RDS PG17 class | |
| G0.7 | Coder pinned in lock | orch writes |
| G0.8 | OCP IPI feasible | **skip WS-11** |
| G0.9 | Bedrock models list | **skip WS-13** |
| G0.10 | ECR pull-through | warn UBI fallback |
| G0.11 | dual VPC+peering doc | |
| G0.12 | repo+4 ref clones | WS-00 |

`make gate-0` before fan-out.

## CONNECTIVITY

`scripts/validate-connectivity.sh --track a` → C1,C2,C3,C4,C5,C9,C13,C14

| id | check |
|---|---|
| C1 | curl -sfI https://dev.usgov.coderdemo.io |
| C2 | workspace terminal WSS |
| C3 | *.dev.usgov.coderdemo.io app |
| C4 | workspace Connected |
| C5 | app via aws.usgov.coderdemo.io |
| C6 | ocp proxy (ph3) |
| C7 | ocp provisioner (ph3) |
| C8 | DERP if C4 fail |
| C9 | Keycloak login |
| C10–C12 | grafana/gitlab/bedrock ph2–4 |
| C13 | ECR pull IRSA in WS |
| C14 | pull-through devcontainer |

Phase1 done: all Track A + WS handoffs 01–08 PASS (06 PARTIAL OK if OIDC wired).

## WS_INDEX

Read full prompt: `docs/swarm/workstreams/WS-NN-*.md`

| ws | ph | state | model | effort | deps | ref_src | deliver | out_keys |
|---|---|---|---|---|---|---|---|---|
| 00 | 0 | — | Sonnet | high | G0.12 | repo-layout | skeleton, scripts, empty TF roots | scaffold_commit |
| 01 | 1 | bootstrap | Sonnet | high | 00 | coder-eks prereqs, demo-aigov prereqs | S3+DDB, R53, NS del, ECR+pull-through | tf_state_bucket, r53_zone_id, ecr_registry |
| 02 | 1 | network | Sonnet | high | 01 | — | dual VPC+peering | eks_vpc_id, subnet_ids, ocp_vpc_id, peering_id |
| 03 | 1 | data | Sonnet | high | 02 | — | RDS PG17, S3 | rds_endpoint, rds_*_db |
| 04 | 1 | eks | Opus4.8 | xhigh | 02,03 | coder-eks/01-infra | EKS+IRSA+kubeconfig; AutoMode or MNG | cluster_name, oidc_arn, kubeconfig_path |
| 05 | 1 | eks-apps | Opus4.8 | xhigh | 03,04 | coder-eks/02-apps | Coder HA helm, direct NLB, RDS coder DB | coder_url, nlb_arn |
| 06 | 1 | platform-eks | Sonnet | high | 04 | homelab KC patterns | Keycloak operator, realm usgov, coder OIDC | keycloak_url, realm, oidc_client_id |
| 07 | 1 | eks-day2 | Opus4.8 | xhigh | 05 | coder-eks/03-day2 | license, ext provisioner platform=eks, ws proxy | provisioner_name, workspace_proxy_url |
| 08 | 1 | — | Sonnet | high | 07 | — | eks k8s template, ECR IRSA, publish | template_id, test_workspace_name |
| 09 | 2 | istio | Opus4.8 | xhigh | 05 | mesh-demo/istio | mesh Tier0; NOT workspace NS | — |
| 10 | 2 | platform-ec2 | Sonnet | high | 02,03 | demo-aigov/platform-ec2 | GitLab EC2 SPOF | gitlab_url |
| 11a | 3 | ocp | Opus4.8 | xhigh | 02,G0.8 | demo-aigov/terraform/ocp | OCP IPI | ocp_api_url, kubeconfig |
| 11b | 3 | — | Sonnet | medium | 00 | demo-aigov/gitops | manifests author only | — |
| 11c | 3 | — | Opus4.8 | xhigh | 11a | homelab prov tags | OCP provisioner | — |
| 11d | 3 | — | Opus4.8 | xhigh | 11c | — | OCP ws proxy | — |
| 11e | 3 | — | Sonnet | high | 01 | — | UBI9→ECR | — |
| 11f | 3 | — | Sonnet | high | 11c,d | — | OCP template | — |
| 12 | 2 | identity | Sonnet | high | 05,06 | homelab | full idp sync | — |
| 13 | 4 | ai | Sonnet | high | 05,G0.9 | demo-aigov bedrock | IRSA allowlist | — |

**WS-05 MUST NOT:** Istio, ingress_mode=istio. **WS-09 AFTER** Phase1 direct ingress proven.

## MODELS (effort = task match, not budget)

| role | model | effort |
|---|---|---|
| orch | Opus4.8 | ultracode |
| opus critical | Opus4.8 | xhigh |
| sonnet apply | Sonnet4.6 | high |
| bulk copy | Sonnet4.6 | medium |
| gates | Haiku | — |
| retry/debug | Opus4.8 | max + ultrathink |

Escalate: mapped → +1 effort → max → Sonnet fail 2x → Opus upgrade. Full: `docs/swarm/MODELS.md`.

## HANDOFF (required)

`docs/swarm/handoffs/WS-NN-handoff.md`: Status PASS|FAIL|PARTIAL, commit, ref SHAs, output table, commands, validation checklist, blockers.

## ORCH

```bash
cd ~/demoenv-workspace/usgov-coderdemo
source ~/.config/usgov-coderdemo/env
export KUBECONFIG=$PWD/kubeconfig
claude --model opus --effort ultracode
```

Sequence: layout check → WS-00 if empty → gate-0 → pin G0.7 → handoffs dir + SWARM-STATUS → waves → validate-track-a → Track B.

Subagent prompt shell:
```
Model/Effort: per WS_INDEX
Read: RULES.md, decisions-locked.md, WS-NN-*.md, [handoffs]
Own state key: [key]
Never edit REFERENCE_ROOT
Write handoff + commit ws-NN:
```

## RISKS (act on)

R3 AutoMode→MNG | R6 partition ARNs | R12 Istio WSS breaks (ph2) | R17 TF locks | R21 ref SHA drift

## REPO_TREE (WS-00 creates)

```
usgov-coderdemo/{Makefile,versions.lock.yaml,kubeconfig(gitignore),terraform/{bootstrap,network,data,eks,eks-apps,platform-eks,eks-day2,istio,platform-ec2,ocp,identity,ai},gitops/,manifests/,coder-templates/,scripts/,docs/}
```

Make targets: `gate-0`, `scaffold`, `apply-*`, `kubeconfig`, `validate-track-a`, `validate-all`

## DOC_MAP (if more context needed)

| need | file |
|---|---|
| WS steps | `docs/swarm/workstreams/WS-NN-*.md` |
| orch runbook | `docs/swarm/ORCHESTRATOR.md` |
| parallelism | `docs/swarm/PARALLELISM.md` |
| creds | `docs/swarm/CREDENTIALS.md` |
| architecture | `docs/architecture/overview.md` |
| ingress/istio/id | `docs/architecture/{ingress,istio,identity}.md` |

Do **not** load all WS files at orch startup — load per spawned agent only.
