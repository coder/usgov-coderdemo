# Model and effort selection for subagents

Recommendations for **Claude Code** subagent runs. Assign **model** and **effort** when spawning each subagent (`/model`, `/effort`, or session config).

**Uncapped Anthropic API** — no token budget, but still **match effort to task shape**. Higher effort adds latency and can overthink routine work. Reserve `xhigh`/`max` for high blast-radius or ambiguous debugging; use `high` as the Sonnet default and `medium` for pattern-heavy copy jobs.

**Requires Claude Code v2.1.154+** for Opus 4.8, effort controls, and dynamic workflows. Run `claude update` before overnight swarm runs.

## Current model aliases (Anthropic API / Max / Team Premium)

| Alias | Resolves to | Notes |
|---|---|---|
| `opus` | **Opus 4.8** (`claude-opus-4-8`) | Default on Max/Team Premium/Enterprise pay-as-you-go |
| `sonnet` | **Sonnet 4.6** | Default on Pro/Team Standard |
| `haiku` | Latest Haiku | Fast background / gate probes |
| `opus[1m]` | Opus 4.8, 1M context | Auto on Max/Team/Enterprise for Opus |
| `opusplan` | Opus in plan mode → Sonnet in execution | Hybrid planning + implementation |

On **Bedrock / Vertex / Foundry**, pin versions explicitly:

```bash
export ANTHROPIC_DEFAULT_OPUS_MODEL='claude-opus-4-8'
export ANTHROPIC_DEFAULT_SONNET_MODEL='claude-sonnet-4-6'
export ANTHROPIC_DEFAULT_HAIKU_MODEL='claude-haiku-4-5'
```

See [Claude Code model config](https://code.claude.com/docs/en/model-config) for provider-specific IDs and `modelOverrides`.

---

## Effort matching principles

Match effort to **blast radius**, **ambiguity**, and **task type** — not budget.

| Signal | Raise effort | Keep effort moderate |
|---|---|---|
| Mistake cost | Blocks critical path, multi-system wiring, mesh cutover | Bounded module, reference-repo copy |
| Ambiguity | Partition edge cases, IRSA/OIDC, WebSocket ingress | Straightforward TF with upstream handoff |
| Task type | Debug / retry / merge conflict | Read-only probe, manifest bulk copy |
| Model fit | Opus on integration work | Sonnet on single-module apply |

**Escalation ladder:** start at the mapped level → on FAIL, bump one step (`high` → `xhigh` → `max`) or add `ultrathink` in the prompt → orchestrator retry may switch model tier (Sonnet fail → Opus).

Do **not** default everything to `max`. Anthropic notes diminishing returns and overthinking at `max` on routine tasks.

---

## Effort levels

Effort controls adaptive reasoning depth. Available levels depend on the active model:

| Model | Supported levels | Default |
|---|---|---|
| **Opus 4.8**, **Opus 4.7** | `low`, `medium`, `high`, `xhigh`, `max` | `high` (4.8), `xhigh` (4.7) |
| **Opus 4.6**, **Sonnet 4.6** | `low`, `medium`, `high`, `max` | `high` |
| Haiku | *(no effort control)* | — |

| Level | When to use in this swarm |
|---|---|
| `low` | *(Haiku only)* — read-only CLI gate probes |
| `medium` | Pattern-heavy bulk copy: manifest trees, empty TF stubs, doc pack copy |
| `high` | **Default Sonnet apply agents** — standard TF/Helm with reference repos |
| `xhigh` | **Default Opus apply agents** — critical path, integration, subtle YAML |
| `max` | **Escalation only** — failed apply retry, blocked WS, Istio/C4 debug |
| `ultracode` | **Orchestrator only** — `xhigh` + dynamic workflow orchestration |

`ultracode` is a Claude Code session setting, not an API effort level. It sends `xhigh` to the model and enables automatic dynamic workflows. Set via `/effort ultracode` on the orchestrator session. Requires Opus 4.7+ (Opus 4.8 recommended).

**Persistence:** `low`–`xhigh` via `effortLevel` in settings. Per-subagent override in frontmatter (`effort: high`). `max` and `ultracode` are session-only except via `CLAUDE_CODE_EFFORT_LEVEL` env var.

**One-off deep reasoning:** include `ultrathink` in a prompt without changing session effort.

References: [Model configuration](https://code.claude.com/docs/en/model-config), [Dynamic workflows](https://code.claude.com/docs/en/workflows), [Effort API](https://platform.claude.com/docs/en/build-with-claude/effort).

---

## Tiers

| Tier | Model | Default effort | Use when |
|---|---|---|---|
| **A — Reasoning** | **Opus** (4.8) | `xhigh` | Critical path apply, multi-system debugging, high blast-radius infra |
| **A+ — Orchestrator** | **Opus** (4.8) | `ultracode` | Wave scheduling, merge conflicts, parallel subagent coordination |
| **B — Coding** | **Sonnet** (4.6) | `high` | Standard Terraform/Helm/k8s adaptation from reference repos |
| **B− — Bulk copy** | **Sonnet** (4.6) | `medium` | Large manifest/TF trees with clear upstream patterns |
| **C — Fast** | **Haiku** | *(n/a)* | Read-only gates, literal doc copy |

### Cursor Task subagents (if not using Claude Code)

Effort is Claude Code–specific. For Cursor Task tool launches, use model slug only:

| Tier | Cursor slug | Maps to |
|---|---|---|
| A | `gpt-5.3-codex-high-fast` | Complex infra / mesh / OCP |
| B | `composer-2.5-fast` | Default TF/Helm work |
| B+ | `gpt-5.5-medium` | Identity TF, template logic, orchestrator |
| C | `composer-2.5-fast` | Gates, scaffold file splits |

When in doubt on Cursor: use **Codex high-fast** for WS on the Phase 1 critical path; **Composer fast** for parallel authoring.

---

## Orchestrator

| Role | Model | Effort | Why |
|---|---|---|---|
| **Top-level orchestrator** | **Opus 4.8** | **ultracode** | Wave scheduling, dynamic workflows, merge conflicts, retry decisions |

---

## Phase 0

| WS / SA | Model | Effort | Why |
|---|---|---|---|
| **GATE-0 probes** (G0.1–G0.12, parallel) | **Haiku** | — | Read-only CLI; no reasoning needed |
| **WS-00 Scaffold** (orchestrator merge) | **Sonnet** | `high` | Templated multi-file layout |
| SA-S0-GATE, SA-S0-VALID scripts | **Sonnet** | `high` | Shell scripts need correctness |
| SA-S0-TF skeletons | **Haiku** | — | Empty module stubs |
| SA-S0-DOCS / runbooks copy | **Haiku** | — | Literal copy from pack |

---

## Phase 1 — critical path

| WS | Model | Effort | Why |
|---|---|---|---|
| **WS-01 Bootstrap** | **Sonnet** | `high` | TF state, R53, ECR; NS delegation needs care but bounded |
| **WS-02 Network** | **Sonnet** | `high` | Dual VPC + peering; well-scoped TF |
| **WS-03 Data** | **Sonnet** | `high` | RDS + S3; security groups |
| **WS-04 EKS** | **Opus 4.8** | `xhigh` | Adapt 01-infra; Auto Mode fallback; IRSA OIDC — high blast radius |
| **WS-05 Coder** | **Opus 4.8** | `xhigh` | **Phase 1 milestone** — Helm, NLB, ACM, DB wiring |
| **WS-06 Keycloak** | **Sonnet** | `high` | Operator/chart + OIDC client; bounded scope |
| **WS-07 EKS day2** | **Opus 4.8** | `xhigh` | Provisioner + workspace proxy + license; easy to miswire |
| **WS-08 EKS templates** | **Sonnet** | `high` | Template + ECR IRSA; mostly authoring |

### Phase 1 parallel authoring (Wave 3b)

| SA | Model | Effort | Why |
|---|---|---|---|
| SA-COPY-EKS (adapt 01/02/03) | **Sonnet** | `high` | Partition refactor while copying |
| SA-COPY-HOMELAB | **Sonnet** | `high` | TF identity patterns |
| SA-COPY-OCP (gitops only, 11b) | **Sonnet** | `medium` | Large manifest trees; pattern-heavy |
| SA-COPY-MESH | **Opus 4.8** | `xhigh` | Istio YAML is subtle (defer apply to WS-09) |
| SA-AUTH-WS5/7 Helm values | **Sonnet** | `high` | Pre-write before apply agent |

---

## Phase 2–4 — Track B

| WS | Model | Effort | Why |
|---|---|---|---|
| **WS-09 Istio** | **Opus 4.8** | `xhigh` | WebSockets, mTLS rollout, ingress cutover — #1 failure mode (R12) |
| **WS-10 GitLab EC2** | **Sonnet** | `high` | Adapt existing demo-aigov module |
| **WS-11a OCP IPI** | **Opus 4.8** | `xhigh` | Long IPI; GovCloud partition; multi-hour debug likely |
| **WS-11b GitOps prep** | **Sonnet** | `medium` | Manifest adaptation, no cluster |
| **WS-11c/d provisioner+proxy** | **Opus 4.8** | `xhigh` | Same class as WS-07 on OCP |
| **WS-11e UBI9 → ECR** | **Sonnet** | `high` | Image build/push script |
| **WS-11f OCP template** | **Sonnet** | `high` | Template publish |
| **WS-12 Identity full** | **Sonnet** | `high` | Homelab TF; SA-12-KC-CLIENTS first, then parallel Sonnet |
| **WS-13 Bedrock** | **Sonnet** | `high` | IRSA + allowlist; bounded if G0.9 enumerated models |

---

## Wave-by-wave model + effort assignment

| Wave | Apply agents | Model | Effort |
|---|---|---|---|
| 0 | — | Haiku (gates), Sonnet (WS-00 merge) | —, `high` |
| 1 | WS-01 | Sonnet | `high` |
| 2 | WS-02 | Sonnet | `high` |
| 3 | WS-03, WS-10, WS-11a | Sonnet, Sonnet, **Opus** | `high`, `high`, **`xhigh`** |
| 4 | WS-04 | **Opus** | **`xhigh`** |
| 5 | WS-05, WS-06 | **Opus**, Sonnet | **`xhigh`**, `high` |
| 6 | WS-07 | **Opus** | **`xhigh`** |
| 7 | WS-08 | Sonnet | `high` |
| 8 | WS-09–13 | **Opus** (09, 11c/d), Sonnet (rest) | **`xhigh`** (Opus), `high` (Sonnet) |

Parallel copy agents in Wave 3b run concurrently at `medium`–`high` per SA table above.

---

## Retry policy × model × effort

Escalate on failure — do not start at max.

| Situation | Model | Effort |
|---|---|---|
| First attempt failed on TF plan/apply (same WS) | **Opus 4.8** | **`max`** + `ultrathink` |
| First attempt failed on gate probe | **Sonnet** | `high` → **`max`** if creds ruled out |
| Istio/WebSocket/C4 agent connectivity | **Opus 4.8** | **`max`** |
| Merge conflict resolution | **Opus 4.8** (orchestrator) | **`xhigh`** (ultracode workflow if multi-file) |
| Blocked >1h on critical path | **Opus 4.8** | **`max`** + orchestrator **`ultracode`** workflow |
| Sonnet WS failed twice | **Opus 4.8** | **`xhigh`** (model upgrade, not just effort bump) |

---

## Subagent launch snippet

```
Model: Opus 4.8   # or Sonnet / Haiku per docs/swarm/MODELS.md
Effort: xhigh     # high | xhigh | max (escalation) | omit for Haiku

You are subagent WS-05 ...
```

For subagent definition files, set frontmatter:

```yaml
---
model: opus
effort: xhigh
---
```

Orchestrator session: `/effort ultracode` or `claude --model opus --effort ultracode`.

---

## Quick lookup table

| ID | Name | Model | Effort |
|---|---|---|---|
| — | Orchestrator | Opus 4.8 | ultracode |
| G0-* | Gate probes | Haiku | — |
| WS-00 | Scaffold | Sonnet | high |
| WS-01 | Bootstrap | Sonnet | high |
| WS-02 | Network | Sonnet | high |
| WS-03 | Data | Sonnet | high |
| WS-04 | EKS | Opus 4.8 | xhigh |
| WS-05 | Coder | Opus 4.8 | xhigh |
| WS-06 | Keycloak | Sonnet | high |
| WS-07 | Day2 | Opus 4.8 | xhigh |
| WS-08 | Templates | Sonnet | high |
| WS-09 | Istio | Opus 4.8 | xhigh |
| WS-10 | GitLab | Sonnet | high |
| WS-11a | OCP IPI | Opus 4.8 | xhigh |
| WS-11b | GitOps prep | Sonnet | medium |
| WS-11c | OCP provisioner | Opus 4.8 | xhigh |
| WS-11d | OCP proxy | Opus 4.8 | xhigh |
| WS-11e | UBI9 ECR | Sonnet | high |
| WS-11f | OCP template | Sonnet | high |
| WS-12 | Identity | Sonnet | high |
| WS-13 | Bedrock | Sonnet | high |
