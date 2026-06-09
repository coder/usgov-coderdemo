#!/usr/bin/env python3
"""
demo-chat-spend-limits.py - drive the Coder Agents chat usage-limit (spend
limit) system on the live demo deployment.

WHAT THIS CONTROLS
Coder Agents chats meter spend per message into chat_messages.total_cost_micros
(computed from the per-model chat_model_configs pricing). A deployment-level
"usage limit" config plus per-group and per-user overrides cap how much a user
may spend per UTC calendar period (day/week/month). When a user reaches their
effective limit, new chat messages are hard-blocked with HTTP 409.

Endpoints used (all admin-only, ResourceDeploymentConfig; note PLURAL
`usage-limits`):
    GET  /api/experimental/chats/usage-limits
    PUT  /api/experimental/chats/usage-limits
        body {"spend_limit_micros": <int|null>, "period": "day|week|month"}
    PUT  /api/experimental/chats/usage-limits/overrides/{userUUID}
    DELETE .../overrides/{userUUID}
    PUT  /api/experimental/chats/usage-limits/group-overrides/{groupUUID}
    DELETE .../group-overrides/{groupUUID}
        override body {"spend_limit_micros": <int>0>}
Per-user EFFECTIVE status is read (admin, no impersonation) from:
    GET  /api/experimental/chats/cost/{userUUID}/summary  -> .usage_limit

MASTER SWITCH (read this before tuning tiers)
The global config has an `enabled` flag that is ON only when spend_limit_micros
is a positive integer. The resolver returns -1 (NO LIMIT for everyone) whenever
the global config is disabled, so group and user overrides take effect ONLY when
a positive global default is also set. To "limit some but not all", set a
generous global default (turns the system ON; that cohort is effectively
unconstrained) and then tighten specific groups/users below it.

PRECEDENCE (tightest wins per the resolver):
    user override  >  MIN(group overrides the user belongs to)  >  global default
Group membership is scanned across ALL organizations here (the HTTP path passes
an invalid org id), so a Coder "Everyone" group override behaves org-wide and a
user in several orgs is capped by the smallest applicable group limit.

UNITS: micros. $1 = 1_000_000 micros. Period is global-only; resets on the UTC
calendar boundary.

SAFETY: --show is read-only and is the default. --apply and --teardown mutate
the live deployment but are fully reversible (--teardown restores the clean
slate: no overrides, global disabled). Admin creds come from
~/.config/usgov-coderdemo/generated-secrets.env and are never logged.

Usage:
    python3 scripts/demo-chat-spend-limits.py [--show]     # read-only (default)
    python3 scripts/demo-chat-spend-limits.py --apply       # set demo tiers
    python3 scripts/demo-chat-spend-limits.py --teardown    # restore clean slate
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("DEMO_CODER_URL", "https://dev.usgov.coderdemo.io").rstrip("/")
SECRETS_ENV = os.path.expanduser("~/.config/usgov-coderdemo/generated-secrets.env")

TOKEN = None

# --- demo tiers (placeholders; tune here) ----------------------------------
# Micros: $1 == 1_000_000. These are DEMO values only.
MICROS_PER_DOLLAR = 1_000_000

# Global default turns the system ON (master switch). A generous baseline means
# anyone NOT caught by a tighter group/user override is effectively
# unconstrained for the demo.
GLOBAL_DEFAULT = {
    "spend_limit_micros": 100_000_000,  # $100
    "period": "month",
}

# (label, group_uuid, spend_limit_micros)
GROUP_OVERRIDES = [
    ("alpha / developers", "0783bd37-fe80-4e61-86d7-bf9333d62d9c", 10_000_000),   # $10
    ("bravo / Everyone",   "4565f1c6-f1de-4e20-bb7e-a171e1046a59", 25_000_000),   # $25 (org-wide)
]

# (label, user_uuid, spend_limit_micros)
USER_OVERRIDES = [
    ("patrickplatform", "289f3ef0-d69a-45ac-b96b-93366543e513", 5_000_000),       # $5
]

# Sample users whose EFFECTIVE limit we surface in --show (read via
# cost/{user}/summary.usage_limit). Chosen to exercise each tier:
#   patrickplatform -> user override ($5)
#   danadev         -> alpha/developers group ($10)
#   austenplatform  -> bravo/Everyone group ($25); also an alpha member
#   admin           -> bravo/Everyone group ($25); in all three orgs
# Note: with these tiers no sample user resolves to the bare $100 default,
# because admin and austen are bravo org members (bravo Everyone == $25).
SAMPLE_USERS = [
    ("admin",           "3ebd62f0-7863-4521-ba98-bb3e5423f2e6"),
    ("austenplatform",  "7e77e572-6658-41e8-a4a2-bd565c116e24"),
    ("patrickplatform", "289f3ef0-d69a-45ac-b96b-93366543e513"),
    ("danadev",         "0eae7f80-9e88-4507-8b0f-faf99b7855a4"),
]


# --- helpers ---------------------------------------------------------------

def read_env_file(path):
    """Parse a shell env file into a dict, tolerating an optional `export `."""
    out = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                if line.startswith("export "):
                    line = line[len("export "):]
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return out


def creds():
    c = read_env_file(SECRETS_ENV)
    if "CODER_ADMIN_EMAIL" not in c or "CODER_ADMIN_PASSWORD" not in c:
        sys.exit(f"admin creds not found in {SECRETS_ENV}")
    return c


def login():
    body = json.dumps({"email": creds()["CODER_ADMIN_EMAIL"],
                       "password": creds()["CODER_ADMIN_PASSWORD"]}).encode()
    req = urllib.request.Request(BASE + "/api/v2/users/login", data=body,
                                 headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req))["session_token"]


def api(method, path, body=None):
    headers = {"Coder-Session-Token": TOKEN, "Content-Type": "application/json"}
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        r = urllib.request.urlopen(req)
        raw = r.read().decode()
        return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, raw


def dollars(micros):
    """Render a micros amount as a dollar string, or a sentinel for None/-1."""
    if micros is None:
        return "(none)"
    if micros < 0:
        return "no-limit"
    return f"${micros / MICROS_PER_DOLLAR:,.2f}"


# --- subcommands -----------------------------------------------------------

def get_global():
    code, cfg = api("GET", "/api/experimental/chats/usage-limits")
    if code != 200 or not isinstance(cfg, dict):
        sys.exit(f"GET usage-limits failed: {code} {cfg}")
    return cfg


def user_effective(user_id):
    """Return (effective_micros|None, current_spend|None, is_limited).

    Reads the user's effective ChatUsageLimitStatus embedded in their cost
    summary. usage_limit is absent when limits are globally disabled.
    """
    code, summary = api("GET", f"/api/experimental/chats/cost/{user_id}/summary")
    if code != 200 or not isinstance(summary, dict):
        return None, None, None
    ul = summary.get("usage_limit")
    if not ul:
        return None, None, False
    return ul.get("spend_limit_micros"), ul.get("current_spend"), ul.get("is_limited", False)


def cmd_show():
    cfg = get_global()
    enabled = cfg.get("spend_limit_micros") is not None
    print(f"Global config @ {BASE}")
    print(f"  enabled (master switch): {enabled}")
    print(f"  default spend limit:     {dollars(cfg.get('spend_limit_micros'))}")
    print(f"  period:                  {cfg.get('period')}")
    print(f"  unpriced model count:    {cfg.get('unpriced_model_count')}")
    print(f"  updated_at:              {cfg.get('updated_at')}")

    print("\nGroup overrides:")
    grp = cfg.get("group_overrides") or []
    if not grp:
        print("  (none)")
    for g in grp:
        name = g.get("group_display_name") or g.get("group_name")
        print(f"  {name:24} {dollars(g.get('spend_limit_micros')):>10}  "
              f"members={g.get('member_count')}  id={g.get('group_id')}")

    print("\nUser overrides:")
    ovr = cfg.get("overrides") or []
    if not ovr:
        print("  (none)")
    for o in ovr:
        print(f"  {o.get('username'):24} {dollars(o.get('spend_limit_micros')):>10}  "
              f"id={o.get('user_id')}")

    print("\nEffective per-user limit (via cost/{user}/summary.usage_limit):")
    if not enabled:
        print("  master switch OFF -> resolver returns no-limit for everyone.")
    for label, uid in SAMPLE_USERS:
        eff, spend, limited = user_effective(uid)
        if eff is None:
            print(f"  {label:18} -> no-limit (usage_limit absent)")
        else:
            print(f"  {label:18} -> limit {dollars(eff):>10}  "
                  f"spend {dollars(spend):>10}  is_limited={limited}")


def put_global(spend_limit_micros, period):
    return api("PUT", "/api/experimental/chats/usage-limits",
               {"spend_limit_micros": spend_limit_micros, "period": period})


def cmd_apply():
    print(f"Applying demo spend-limit tiers @ {BASE}\n")
    # 1. Global default FIRST so the master switch is ON before overrides matter.
    code, _ = put_global(GLOBAL_DEFAULT["spend_limit_micros"], GLOBAL_DEFAULT["period"])
    ok = code == 200
    print(f"  [{'ok' if ok else 'FAIL'}] global default "
          f"{dollars(GLOBAL_DEFAULT['spend_limit_micros'])} / {GLOBAL_DEFAULT['period']} -> {code}")
    failed = 0 if ok else 1

    # 2. Group overrides.
    for label, gid, micros in GROUP_OVERRIDES:
        code, _ = api("PUT", f"/api/experimental/chats/usage-limits/group-overrides/{gid}",
                      {"spend_limit_micros": micros})
        ok = code == 200
        failed += 0 if ok else 1
        print(f"  [{'ok' if ok else 'FAIL'}] group   {label:20} {dollars(micros):>10} -> {code}")

    # 3. User overrides.
    for label, uid, micros in USER_OVERRIDES:
        code, _ = api("PUT", f"/api/experimental/chats/usage-limits/overrides/{uid}",
                      {"spend_limit_micros": micros})
        ok = code == 200
        failed += 0 if ok else 1
        print(f"  [{'ok' if ok else 'FAIL'}] user    {label:20} {dollars(micros):>10} -> {code}")

    print(f"\nApply done. {failed} failure(s).")
    return failed


def cmd_teardown():
    print(f"Tearing down demo spend-limit tiers @ {BASE}\n")
    failed = 0
    # Remove user overrides, then group overrides (404 tolerated == already gone).
    for label, uid, _ in USER_OVERRIDES:
        code, _ = api("DELETE", f"/api/experimental/chats/usage-limits/overrides/{uid}")
        ok = code in (200, 204, 404)
        failed += 0 if ok else 1
        print(f"  [{'ok' if ok else 'FAIL'}] del user  {label:20} -> {code}")
    for label, gid, _ in GROUP_OVERRIDES:
        code, _ = api("DELETE", f"/api/experimental/chats/usage-limits/group-overrides/{gid}")
        ok = code in (200, 204, 404)
        failed += 0 if ok else 1
        print(f"  [{'ok' if ok else 'FAIL'}] del group {label:20} -> {code}")
    # Disable global last (master switch OFF -> no-limit for everyone).
    code, _ = put_global(None, GLOBAL_DEFAULT["period"])
    ok = code == 200
    failed += 0 if ok else 1
    print(f"  [{'ok' if ok else 'FAIL'}] disable global (spend_limit_micros=null) -> {code}")

    print(f"\nTeardown done. {failed} failure(s).")
    return failed


def main():
    global TOKEN
    ap = argparse.ArgumentParser(description="Drive Coder Agents chat spend limits on the demo.")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--show", action="store_true", help="read-only report (default)")
    g.add_argument("--apply", action="store_true", help="set the demo tiers (idempotent)")
    g.add_argument("--teardown", action="store_true", help="remove overrides and disable global")
    args = ap.parse_args()

    TOKEN = login()

    if args.apply:
        rc = cmd_apply()
        print()
        cmd_show()
        sys.exit(1 if rc else 0)
    if args.teardown:
        rc = cmd_teardown()
        print()
        cmd_show()
        sys.exit(1 if rc else 0)
    cmd_show()


if __name__ == "__main__":
    main()
