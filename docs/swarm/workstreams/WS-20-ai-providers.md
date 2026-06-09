# WS-20: AI providers reconciler

| Field | Value |
|---|---|
| **State key** | n/a (API-managed; no tfstate) |
| **Phase** | 2 (demo finishing) |
| **Model** | **Sonnet** |
| **Depends on** | WS-05 (Coder control plane), WS-13 (Bedrock IRSA) |
| **Track** | B |

## Goal

Make the AI Gateway providers and the Coder Agents model picker a declarative,
API-managed source of truth that survives the v2.34 seed-once constraint:

1. Author `deploy/coder/ai-providers.yaml` (providers + model presets).
2. Implement `scripts/reconcile-ai-providers.py` to diff the file against the
   live API and create/update/disable providers and model presets to match.
3. Populate the (currently empty) model picker so a Coder Agents chat has
   selectable models, and pre-stage a disabled Bedrock provider for a one-flip
   swap.

Authoring + read-only only in this workstream. The orchestrator (root) runs the
live `--apply`.

## Store-sharing finding (verified, v2.34.0)

There is ONE shared provider store. The `ai_providers` database table backs both
paths:

- **AI Gateway / aibridge in-workspace path:** `POST
  /api/v2/aibridge/<provider-name>/v1/...` routes by provider name.
- **Coder Agents control-plane model picker:** `GET
  /api/experimental/chats/models` resolves availability via
  `getUserChatProviderAvailability`, which reads the SAME `ai_providers` rows
  (`GetAIProviders`) and derives chat providers from them
  (`configuredProvidersFromAIProviders`). The legacy SEPARATE chat-provider API
  (`/api/experimental/chats/providers`) now returns HTTP 410 "Legacy chat
  provider APIs were removed. Use AI provider APIs instead", confirming the two
  stores were unified.

Models are a SEPARATE table (`chat_model_configs`), managed via
`/api/experimental/chats/model-configs`. An `AIProvider` row carries no model
list (only Bedrock `settings` carry `model` + `small_fast_model`). Each model
config is tied to an enabled provider by `ai_provider_id`; the create API
returns 412 if the provider is missing or disabled.

Source (reference `coder` @ `47a8c9572f` = v2.34.0-rc.0-706): `coderd/ai_providers.go`,
`coderd/exp_chats.go` (`getUserChatProviderAvailability`,
`configuredProvidersFromAIProviders`, `createChatModelConfig`,
`writeLegacyChatProviderGone`), `codersdk/aiproviders.go`, `codersdk/chats.go`.

## Live enumeration (read-only)

Live deployment `v2.34.0+3006da5`.

- `GET /api/v2/ai/providers`: `anthropic` (type anthropic, enabled, placeholder
  key masked `sk-a...ings`) and `anthropic-bedrock` (type bedrock, enabled,
  IRSA, settings `model=us-gov.anthropic.claude-sonnet-4-5-20250929-v1:0`,
  `region=us-gov-west-1`, `small_fast_model=amazon.nova-pro-v1:0`).
- `GET /api/experimental/chats/models`: providers `anthropic` + `bedrock`,
  both `available`, but `models: []`.
- `GET /api/experimental/chats/model-configs`: `[]` (zero presets). The picker
  therefore lists providers with no selectable models until presets are created.
- `GET /api/v2/deployment/config` (seed values): `model =
  global.anthropic.claude-sonnet-4-5-20250929-v1:0`, `small_fast_model =
  global.anthropic.claude-haiku-4-5-20251001-v1:0`. These ground the preset
  model generations (Sonnet 4.5 `claude-sonnet-4-5-20250929`, Haiku 4.5
  `claude-haiku-4-5-20251001`).

The live `ai_model_prices` table (71 rows) has no read-only REST endpoint and
`psql` is absent from the coderd image, so prices were not enumerated directly
(an ephemeral DB pod was avoided to honor "no cluster mutation"). Preset model
ids are grounded on the live `deployment/config` generations; the create API
enforces only a provider-prefix check, so ids are validated post-apply against
the live picker.

## Files

| File | Purpose |
|---|---|
| `deploy/coder/ai-providers.yaml` | Declarative source of truth: providers (type, name, enabled, base_url, key_from_env, bedrock settings) + model presets. |
| `scripts/reconcile-ai-providers.py` | Idempotent reconciler. Default is a read-only plan; `--apply` mutates. Keys read from env, never argv/URL, never logged. |

## Reconcile / Apply

```sh
. ~/.config/usgov-coderdemo/env
python3 scripts/reconcile-ai-providers.py --dry-run   # read-only plan
python3 scripts/reconcile-ai-providers.py --apply     # orchestrator only
```

The reconciler manages only providers declared in the file; live providers not
in the file are reported `UNMANAGED` and left untouched. Provider key drift is
detected by comparing the server masked rendering against a locally computed
mask (replicating `aibridge/utils.MaskSecret`), so the placeholder is detected
and replaced and a second run is a no-op without printing the key.

## Validation

- [ ] **C20a** `--dry-run` reports the intended diff and makes no changes
- [ ] **C20b** after `--apply`, picker shows live models and a Coder Agents chat responds
- [ ] **C20c** `POST /api/v2/aibridge/anthropic/v1/messages` returns 200
- [ ] **C20d** an OpenAI route (`POST /api/v2/aibridge/openai/v1/chat/completions`) returns 200
- [ ] **C20e** `/ai/settings` reachable; re-run of `--apply` is a no-op; coderd stays healthy

## Risks

- **Seed-env crash guard.** Never change a seeded `CODER_AI_GATEWAY_PROVIDER_*`
  Helm value after first boot; coderd refuses to start. This reconciler manages
  providers via the API only; Helm env stays a frozen one-time seed.
- **Bedrock pre-staged disabled.** The file declares `anthropic-bedrock`
  disabled, so a dry-run shows `DISABLE` against the currently-enabled live
  provider. Intended staged posture (Sonnet 4.5 Bedrock access gated;
  `coder/aibridge#221` beta-flag issue). Set `enabled: true` in the file to keep
  Bedrock live.
