# Coder Agents chat spend limits (demo prototype)

Status: prototype applied to the live demo (`https://dev.usgov.coderdemo.io`).
Reversible via `scripts/demo-chat-spend-limits.py --teardown`.

This documents the Coder Agents **chat usage-limit** (spend limit) system, the
demo tiers we applied, and exactly how to operate and tear it down. Control
script: `scripts/demo-chat-spend-limits.py`.

## Two spend systems (only one is usable here)

1. **Chat usage limits** (what we use). Per-user spend caps on Coder Agents
   chats, enforced server-side. Spend is metered per message into
   `chat_messages.total_cost_micros`, computed from the per-model pricing on
   `chat_model_configs` (the input/output/cache prices per 1M tokens we already
   set on the four enabled models). Admin-only endpoints under
   `/api/experimental/chats/usage-limits`.
2. **AI Bridge budgets** (`/api/v2/.../ai/budget`). Non-functional scaffolding
   in this version: there is no enforcement and `/ai/budget` returns 404 on the
   live deployment. Do **not** use it. Mentioned here only so it is not mistaken
   for the enforcing system.

## Units and period

- Micros. `$1 = 1,000,000 micros`.
- One period applies globally: `day`, `week`, or `month`. Resets on the UTC
  calendar boundary (month = first of month 00:00 UTC).

## The three tiers and precedence

Effective limit is resolved per user, tightest wins:

```
user override  >  MIN(group overrides the user belongs to)  >  global default
```

- **Global default**: deployment-wide baseline.
- **Group override**: a per-group cap. If a user is in several groups with
  overrides, the **smallest** applies.
- **User override**: a per-user cap that wins over everything.

Group membership is scanned across **all organizations** in the HTTP path (the
endpoint passes an invalid org id; see TODO `CODAGT-161`). A Coder **"Everyone"**
group therefore behaves **org-wide**: every member of that org inherits the
override, and a user who belongs to multiple orgs is capped by the smallest
applicable group limit.

## The master switch (read this before tuning)

The global config carries an `enabled` flag that is ON **only when
`spend_limit_micros` is a positive integer**. When the global config is disabled
(`spend_limit_micros = null`), the resolver returns `-1` (NO LIMIT) for
**everyone**, and group/user overrides are ignored.

Consequence: **group and user overrides only take effect when a positive global
default is set.** To "limit some but not all", do not leave the global off.
Instead:

1. Set a **generous global default** (turns the system ON; that cohort is
   effectively unconstrained).
2. **Tighten** specific groups/users below it.

## Enforcement and accounting

- Enforcement is a **hard block**: when `current_spend >= effective_limit`, a new
  chat message is rejected with **HTTP 409** (`ChatUsageLimitExceededResponse`).
- `current_spend` is `SUM(chat_messages.total_cost_micros)` over the active UTC
  period, scoped to the user.
- Pricing comes from `chat_model_configs`. Messages sent **before** pricing was
  configured have `NULL` cost and are **excluded**. So `current_spend` starts at
  `$0` and only moves on **new priced messages**. This is the key demo caveat:
  applying limits does not retroactively bill historical chats.

## Endpoints (admin-only, ResourceDeploymentConfig)

Note the plural `usage-limits`.

```
GET    /api/experimental/chats/usage-limits
PUT    /api/experimental/chats/usage-limits
       body {"spend_limit_micros": <int|null>, "period": "day|week|month"}
GET    /api/experimental/chats/usage-limits/status          # CALLER-only effective status
PUT    /api/experimental/chats/usage-limits/overrides/{userUUID}
DELETE /api/experimental/chats/usage-limits/overrides/{userUUID}
       body {"spend_limit_micros": <int>0>}
PUT    /api/experimental/chats/usage-limits/group-overrides/{groupUUID}
DELETE /api/experimental/chats/usage-limits/group-overrides/{groupUUID}
       body {"spend_limit_micros": <int>0>}
```

`/usage-limits/status` reports only the **caller's** effective status (known TODO
`CODAGT-161`: it is global-scoped and not parameterized by user). To read **any**
user's effective limit as an admin without impersonation, use the cost summary,
whose `usage_limit` field embeds that user's effective `ChatUsageLimitStatus`:

```
GET /api/experimental/chats/cost/{userUUID}/summary   ->  .usage_limit
```

`usage_limit` is **absent** when limits are globally disabled (master switch
OFF), which is itself a clean signal that nobody is limited.

### curl recipes

```sh
TOKEN=$(cat /tmp/.ct); H="Coder-Session-Token: $TOKEN"
BASE=https://dev.usgov.coderdemo.io

# Inspect global config + all overrides
curl -s "$BASE/api/experimental/chats/usage-limits" -H "$H"

# Master switch ON: global default $100/month
curl -s -X PUT "$BASE/api/experimental/chats/usage-limits" -H "$H" \
  -H 'Content-Type: application/json' \
  -d '{"spend_limit_micros":100000000,"period":"month"}'

# Group override (org-wide via an Everyone group): $25
curl -s -X PUT "$BASE/api/experimental/chats/usage-limits/group-overrides/4565f1c6-f1de-4e20-bb7e-a171e1046a59" \
  -H "$H" -H 'Content-Type: application/json' -d '{"spend_limit_micros":25000000}'

# User override: $5
curl -s -X PUT "$BASE/api/experimental/chats/usage-limits/overrides/289f3ef0-d69a-45ac-b96b-93366543e513" \
  -H "$H" -H 'Content-Type: application/json' -d '{"spend_limit_micros":5000000}'

# Read any user's effective limit (admin, no impersonation)
curl -s "$BASE/api/experimental/chats/cost/289f3ef0-d69a-45ac-b96b-93366543e513/summary" -H "$H" \
  | python3 -c 'import sys,json;print(json.load(sys.stdin).get("usage_limit"))'

# Master switch OFF (no limit for anyone)
curl -s -X PUT "$BASE/api/experimental/chats/usage-limits" -H "$H" \
  -H 'Content-Type: application/json' -d '{"spend_limit_micros":null,"period":"month"}'
```

## Demo tiers applied (placeholders; tune in the script)

| Tier                          | Scope                         | Limit  |
|-------------------------------|-------------------------------|--------|
| Global default (master ON)    | everyone (baseline)           | $100 / month |
| Group: alpha / developers     | `0783bd37-...d62d9c`          | $10    |
| Group: bravo / Everyone       | `4565f1c6-...e1046a59` (org-wide) | $25 |
| User: patrickplatform         | `289f3ef0-...6543e513`        | $5     |

### Resolved effective limits (verified live)

| User            | Effective | Why                                            |
|-----------------|-----------|------------------------------------------------|
| patrickplatform | $5        | user override wins over all groups             |
| danadev         | $10       | only in alpha/developers ($10)                 |
| austenplatform  | $25       | bravo org member -> bravo Everyone ($25)       |
| admin           | $25       | bravo org member -> bravo Everyone ($25)       |

`current_spend` is `$0` for all (historical messages are unpriced).

**Caveat / deviation from a naive expectation:** the $100 default is **not**
visible on any of these sample users. `admin` and `austenplatform` are members
of the **bravo** org, so they inherit the bravo **Everyone** override ($25); the
bare $100 default only applies to a user who is in **neither** alpha/developers
**nor** any bravo org (for example, a user confined to the `coder` org). This is
correct resolver behavior (MIN across all of a user's groups, globally), just a
reminder that "Everyone" overrides reach every org member.

## How to view

- **Admin UI**: `/agents/settings/spend` ("Spend management") lists the global
  default, group overrides, and user overrides.
- **User topbar `UsageIndicator`** (the ring): renders **only** when the user's
  `status.is_limited` is true.
- **`ChatCostSummaryView`**: shows the "{period} spend limit" card for the user.
- **CLI**: `python3 scripts/demo-chat-spend-limits.py --show`.

## Apply / tear down

```sh
# Read-only (default)
python3 scripts/demo-chat-spend-limits.py --show

# Apply the demo tiers (global first so the master switch is ON, then overrides)
python3 scripts/demo-chat-spend-limits.py --apply

# Restore the clean slate: remove all overrides, then disable the global config
python3 scripts/demo-chat-spend-limits.py --teardown
```

`--apply` is idempotent (all writes are upserts). `--teardown` deletes every
override the script manages and then PUTs `spend_limit_micros = null`, returning
the deployment to "no limits for anyone".

The demo tiers are currently **left applied** so the feature can be shown. Run
`--teardown` to revert.
