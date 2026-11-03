#!/usr/bin/env python3
# Status line: shows usage limits and saves them to ~/.claude/state/rate-limits.json
# so operators (e.g. commit-operator) can read the weekly usage.
import json, os, sys, time

data = json.load(sys.stdin)
limits = data.get("rate_limits") or {}
state_dir = os.path.expanduser("~/.claude/state")
if limits:
    os.makedirs(state_dir, exist_ok=True)
    tmp = os.path.join(state_dir, "rate-limits.json.tmp")
    with open(tmp, "w") as f:
        json.dump({"updated_at": int(time.time()), "rate_limits": limits}, f)
    os.replace(tmp, os.path.join(state_dir, "rate-limits.json"))

parts = []
for key, label in (("five_hour", "5h"), ("seven_day", "7d")):
    pct = (limits.get(key) or {}).get("used_percentage")
    if pct is not None:
        parts.append(f"{label}: {pct:.0f}%")
print(" | ".join(parts))
