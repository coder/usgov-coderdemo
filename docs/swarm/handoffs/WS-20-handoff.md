# WS-20 handoff

- **Status:** PASS (authored, applied live, and verified by root)
- **Agent:** WS-20 (AI providers reconciler)
- **Timestamp:** 2026-06-08T06:29:48Z
- **Git commit:** uncommitted (root applies and commits)
- **Branch:** ws-2x/phase2

## Applied result (root, 2026-06-08)
Ran `python3 scripts/reconcile-ai-providers.py --apply`: updated `anthropic` to
the real key, created `openai`, disabled `anthropic-bedrock` (staged), created 4
model presets (claude-sonnet-4-5-20250929 default, claude-haiku-4-5-20251001,
gpt-5.1, gpt-4.1); 0 failures. coderd stayed 2/2 Running with 0 restarts (no
seed-env crash). Re-run is a no-op. Live verification: providers list correct; 4
model presets present; `POST /api/v2/aibridge/anthropic/v1/messages` -> HTTP 200
real completion; `POST /api/v2/aibridge/openai/v1/chat/completions` -> HTTP 200
real completion.

## Reference commits copied
| Repo | SHA |
|------|-----|
| reference/coder | 47a8c9572f579913209edddfddd6c71c5546781b (v2.34.0-rc.0-706) |

Notes: no code copied verbatim. `mask_secret()` in the reconciler re-implements
`aibridge/utils.MaskSecret` (`revealLength` 4/2/1/0) for idempotent key compare.
API shapes adapted from `codersdk/aiproviders.go` and `codersdk/chats.go`.

## Outputs (required for downstream)
| Key | Value |
|-----|-------|
| Store sharing | ONE shared `ai_providers` table backs both AI Gateway and Coder Agents picker. Legacy chat-provider API returns HTTP 410. |
| Models table | Separate `chat_model_configs` via `/api/experimental/chats/model-configs`; tied to an enabled provider by `ai_provider_id`. |
| Live providers | `anthropic` (placeholder key `sk-a...ings`, enabled), `anthropic-bedrock` (IRSA, enabled). |
| Live model presets | none (`model-configs` is `[]`; picker shows providers with empty model set). |
| Live model generations | Sonnet 4.5 `claude-sonnet-4-5-20250929`; Haiku 4.5 `claude-haiku-4-5-20251001`; Bedrock `us-gov.anthropic.claude-sonnet-4-5-20250929-v1:0` + `amazon.nova-pro-v1:0`. |
| Source of truth | `deploy/coder/ai-providers.yaml` |
| Reconciler | `scripts/reconcile-ai-providers.py` (default dry-run; `--apply` mutates) |

## Commands run
```
# read-only investigation: admin login (POST) then GET only
curl POST /api/v2/users/login                       # token captured, not printed
GET  /api/v2/buildinfo                               # v2.34.0+3006da5
GET  /api/v2/ai/providers                            # 2 providers (above)
GET  /api/experimental/chats/models                  # providers available, models []
GET  /api/experimental/chats/model-configs           # []
GET  /api/v2/deployment/config                        # seed providers + model generations
python3 scripts/reconcile-ai-providers.py --dry-run  # plan below; live state unchanged
```

Dry-run plan (no changes made):
```
[UPDATE ] provider anthropic           key: replace ['sk-a...ings'] -> from $ANTHROPIC_KEY
[CREATE ] provider openai              type=openai; enabled=True; base_url=https://api.openai.com/v1/; key from $OPENAI_KEY
[DISABLE] provider anthropic-bedrock   enabled=False; display_name set
[CREATE ] model anthropic/claude-sonnet-4-5-20250929   default=True context_limit=200000
[CREATE ] model anthropic/claude-haiku-4-5-20251001    context_limit=200000
[CREATE ] model openai/gpt-5.1                          context_limit=400000
[CREATE ] model openai/gpt-4.1                          context_limit=1047576
[BLOCKED] model anthropic-bedrock/...sonnet-4-5...      provider disabled in file
Summary: BLOCKED=1, CREATE=5, DISABLE=1, UPDATE=1
```

## EXACT commands for root (apply)

```sh
# Env. ANTHROPIC_KEY / OPENAI_KEY are the real keys; admin creds from generated-secrets.env.
. ~/.config/usgov-coderdemo/env
export PATH="$HOME/.local/bin:$PATH"
cd /home/coder/demoenv-workspace/usgov-phase2

# 1. Re-confirm the plan (read-only).
python3 scripts/reconcile-ai-providers.py --dry-run

# 2. Apply: enable anthropic (replace placeholder key) + openai (create with key),
#    disable the pre-staged Bedrock provider, create the 4 model presets.
python3 scripts/reconcile-ai-providers.py --apply

# 3. Idempotency: re-run must report no CREATE/UPDATE/DISABLE.
python3 scripts/reconcile-ai-providers.py --dry-run
```

Optional Bedrock swap later (after GovCloud Sonnet 4.5 access is granted): set
`enabled: true` on `anthropic-bedrock` in `deploy/coder/ai-providers.yaml`, then
re-run `python3 scripts/reconcile-ai-providers.py --apply`.

## EXACT verification for root

```sh
. ~/.config/usgov-coderdemo/env; . ~/.config/usgov-coderdemo/generated-secrets.env
export CODER_ADMIN_EMAIL CODER_ADMIN_PASSWORD PATH="$HOME/.local/bin:$PATH"
export KUBECONFIG=/home/coder/demoenv-workspace/usgov-coderdemo/kubeconfig
URL="https://dev.usgov.coderdemo.io"
B=$(python3 -c 'import os,json;print(json.dumps({"email":os.environ["CODER_ADMIN_EMAIL"],"password":os.environ["CODER_ADMIN_PASSWORD"]}))')
TOKEN=$(printf '%s' "$B" | curl -s -X POST "$URL/api/v2/users/login" -H 'Content-Type: application/json' --data @- | jq -r .session_token)
AG(){ printf 'header = "Coder-Session-Token: %s"\n' "$TOKEN" | curl -s -K - "$URL$1"; }
AP(){ printf 'header = "Coder-Session-Token: %s"\n' "$TOKEN" > /tmp/h.$$; curl -s -o /dev/null -w '%{http_code}\n' -K /tmp/h.$$ -H 'Content-Type: application/json' -X POST "$URL$1" --data "$2"; rm -f /tmp/h.$$; }

# picker shows live models (expect anthropic + openai with non-empty models)
AG /api/experimental/chats/models | jq '.providers[] | {provider, available, models:(.models|length)}'
# model presets present (expect 4: 2 anthropic, 2 openai)
AG /api/experimental/chats/model-configs | jq 'map({provider,model,enabled,is_default})'
# AI Gateway anthropic route -> 200
AP /api/v2/aibridge/anthropic/v1/messages '{"model":"claude-sonnet-4-5-20250929","max_tokens":16,"messages":[{"role":"user","content":"ping"}]}'
# AI Gateway openai route -> 200
AP /api/v2/aibridge/openai/v1/chat/completions '{"model":"gpt-4.1","max_tokens":16,"messages":[{"role":"user","content":"ping"}]}'
# /ai/settings reachable (expect 200)
AG /ai/settings >/dev/null; printf 'ai/settings: '; curl -s -o /dev/null -w '%{http_code}\n' -K <(printf 'header = "Coder-Session-Token: %s"\n' "$TOKEN") "$URL/ai/settings"
# coderd healthy
kubectl -n coder rollout status deploy/coder --timeout=60s
AG /api/v2/buildinfo | jq -r .version
```

Expected: picker lists `anthropic` and `openai` with non-empty `models`; a Coder
Agents chat in the dashboard responds; the two POST probes print `200`;
`/ai/settings` prints `200`; the second `--dry-run` shows only
NOOP/UNMANAGED/BLOCKED; coderd rollout is complete and buildinfo returns
`v2.34.0+3006da5`.

## Validation
- [x] Store-sharing question answered (one shared `ai_providers` store)
- [x] Live model ids enumerated read-only
- [x] `deploy/coder/ai-providers.yaml` authored (anthropic, openai, disabled bedrock + presets)
- [x] `scripts/reconcile-ai-providers.py` implemented; `--dry-run` run; live state unchanged
- [x] root `--apply` (enabled anthropic+openai with real keys; 0 failures)
- [x] picker shows live models; Coder Agents chat responds
- [x] anthropic route 200; openai route 200; `/ai/settings` 200; re-run no-op; coderd healthy (2/2, 0 restarts)

## Blockers
- None for authoring. Live apply requires the real `ANTHROPIC_KEY`/`OPENAI_KEY`
  (present in `~/.config/usgov-coderdemo/env`) and owner creds (present).

## Notes for orchestrator
- The reconciler manages providers via the API only. Do NOT change any seeded
  `CODER_AI_GATEWAY_PROVIDER_*` Helm value afterward; coderd refuses to start on
  seed-env drift. Treat Helm env as a frozen one-time seed.
- The plan includes `DISABLE anthropic-bedrock` because the file pre-stages it
  disabled while the live provider is enabled. If you want Bedrock to stay live,
  set `enabled: true` on it in the file before `--apply`.
- Key handling is idempotent: drift is detected by masked compare, so the real
  key replaces the placeholder on first apply and a re-run is a no-op. Use
  `--rotate-keys` only to force a same-mask rotation.
- BLOCKED model presets (Bedrock) are not mutations; they stay BLOCKED until the
  Bedrock provider is enabled, so they do not break the no-op re-run check.
