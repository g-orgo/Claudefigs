#!/usr/bin/env python3
"""Aggregate real token usage from Claude Code transcripts, plus router tier counts."""
import argparse
import glob
import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

PROJECTS = os.path.expanduser("~/.claude/projects")
ROUTER = os.path.expanduser("~/.claude/state/router.jsonl")
FIELDS = ["calls", "input", "cache_write", "cache_read", "output", "thinking"]


def parse_ts(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def agent_name(path):
    if "/subagents/" not in path:
        return "main"
    meta = path[:-len(".jsonl")] + ".meta.json"
    try:
        with open(meta, encoding="utf-8") as fh:
            return json.load(fh).get("agentType") or "subagent"
    except Exception:
        return "subagent"


def read_file(path, since, project_filter):
    """Return {(agent, model, effort): counters}, deduped by requestId (last record wins)."""
    last = {}
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                msg = rec.get("message") or {}
                usage = msg.get("usage")
                if not isinstance(usage, dict):
                    continue
                ts = parse_ts(rec.get("timestamp"))
                if ts is None or ts < since:
                    continue
                key = rec.get("requestId") or rec.get("uuid") or id(rec)
                last[key] = (rec, msg, usage, ts)
    except Exception:
        return {}
    agg = defaultdict(lambda: Counter())
    agent = agent_name(path)
    for rec, msg, usage, _ts in last.values():
        group = (agent, msg.get("model") or "-", rec.get("effort") or "-")
        c = agg[group]
        c["calls"] += 1
        c["input"] += usage.get("input_tokens") or 0
        c["cache_write"] += usage.get("cache_creation_input_tokens") or 0
        c["cache_read"] += usage.get("cache_read_input_tokens") or 0
        c["output"] += usage.get("output_tokens") or 0
        details = usage.get("output_tokens_details") or {}
        c["thinking"] += details.get("thinking_tokens") or 0
    return agg


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=float, default=7)
    ap.add_argument("--project", default="")
    args = ap.parse_args()
    since = datetime.now(timezone.utc) - timedelta(days=args.days)

    files = glob.glob(os.path.join(PROJECTS, "*", "*.jsonl"))
    files += glob.glob(os.path.join(PROJECTS, "*", "*", "subagents", "agent-*.jsonl"))
    if args.project:
        files = [f for f in files if args.project in os.path.relpath(f, PROJECTS).split(os.sep)[0]]

    totals = defaultdict(lambda: Counter())
    for path in files:
        try:
            if os.path.getmtime(path) < since.timestamp():
                continue
        except OSError:
            continue
        for group, counters in read_file(path, since, args.project).items():
            totals[group].update(counters)

    rows = sorted(totals.items(), key=lambda kv: kv[1]["output"], reverse=True)
    header = ["agent", "model", "effort"] + FIELDS
    table = [header]
    grand = Counter()
    for (agent, model, effort), c in rows:
        table.append([agent, model, effort] + [f"{c[f]:,}" for f in FIELDS])
        grand.update(c)
    table.append(["TOTAL", "", ""] + [f"{grand[f]:,}" for f in FIELDS])
    widths = [max(len(str(r[i])) for r in table) for i in range(len(header))]
    print(f"Usage since {since.date()} ({args.days:g} days), {len(files)} transcript files scanned")
    for i, r in enumerate(table):
        print("  ".join(str(v).ljust(widths[j]) if j < 3 else str(v).rjust(widths[j]) for j, v in enumerate(r)))
        if i == 0:
            print("  ".join("-" * w for w in widths))
    denom = grand["input"] + grand["cache_write"] + grand["cache_read"]
    ratio = grand["cache_read"] / denom if denom else 0.0
    print(f"Cache hit ratio: {ratio:.1%} (cache_read / (input + cache_write + cache_read))")

    print()
    if os.path.exists(ROUTER):
        tiers = Counter()
        try:
            with open(ROUTER, encoding="utf-8") as fh:
                for line in fh:
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue
                    ts = parse_ts(rec.get("ts"))
                    if ts is None or ts < since:
                        continue
                    tiers[rec.get("tier", "?")] += 1
        except Exception:
            pass
        print("Router tiers: " + (", ".join(f"{t}={n}" for t, n in sorted(tiers.items())) or "none in window"))
    else:
        print("Router tiers: no router log")


if __name__ == "__main__":
    main()
