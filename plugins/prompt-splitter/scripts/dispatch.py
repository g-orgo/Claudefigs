"""Dispatch each group of a split plan to its own background Claude session.

Usage: dispatch.py plan.json [--view konsole|none] [--permission-mode MODE]
       dispatch.py --wait <state.json>   (internal: launches the groups that were waiting)
Plan: {"cwd": "...", "groups": [{"name": "short-kebab", "title": "...", "prompt": "...", "after": ["other"]}]}
"after" lists the groups this one waits for; groups without it start at once.

Chains: groups linked by "after" (shared context or one builds on another) form a chain.
Each chain runs in sequence and is numbered K.S; chains run in parallel with each other.
Independent groups are single-item chains, numbered K and run async.
"""

import argparse
import datetime as dt
import glob
import json
import os
import re
import subprocess
import sys
import time
import uuid

STATE_DIR = os.path.expanduser("~/.claude/state")
STATE_FILE = os.path.join(STATE_DIR, "prompt-splitter.jsonl")
PERMISSION_MODES = ["acceptEdits", "auto", "bypassPermissions", "manual", "dontAsk", "plan"]
# "backgrounded · <id> · <name>" (middle dot U+00B7)
BG_RE = re.compile(r"backgrounded\s*·\s*(\S+)\s*·\s*(\S+)")
POLL_INTERVAL_S = 15
# Same grace as the mod's isRunning: a missing agent counts as ended after this many seconds.
MISSING_GRACE_S = 90
# A just-launched item may not report "working" yet, so it never counts as ended this early.
MIN_RUN_S = 45
WAIT_GIVE_UP_S = 12 * 60 * 60
# Completion icons shown before each item in the table (same marks as status.py).
DONE_MARK = "✓"
PENDING_MARK = "○"
LEGEND = "✓ completo   ○ em andamento ou aguardando"


def fail(message: str) -> None:
    print(message, file=sys.stderr)
    sys.exit(2)


def after_of(group: dict) -> list[str]:
    return [str(dep) for dep in (group.get("after") or [])]


def session_name(group: dict) -> str:
    return "split-" + group["name"]


def group_title(group: dict) -> str:
    """Return the group's title, else the first prompt line clipped to 60 chars."""
    title = str(group.get("title") or "").strip()
    if title:
        return title
    first_line = str(group.get("prompt") or "").strip().splitlines()[0:1]
    head = first_line[0].strip() if first_line else ""
    return head if len(head) <= 60 else head[:57].rstrip() + "..."


def order_groups(groups: list[dict]) -> list[dict]:
    """Return the groups in execution order, stable on plan order. Exits 2 on unknown names or cycles."""
    names = {str(g.get("name") or "") for g in groups}
    for group in groups:
        for dep in after_of(group):
            if dep not in names:
                fail(f"Group '{group.get('name')}' waits for unknown group '{dep}'.")
    placed: list[dict] = []
    done: set[str] = set()
    remaining = list(groups)
    while remaining:
        ready = next((g for g in remaining if all(d in done for d in after_of(g))), None)
        if ready is None:
            stuck = ", ".join(str(g.get("name")) for g in remaining)
            fail(f"Cycle in 'after' between groups: {stuck}.")
        placed.append(ready)
        done.add(str(ready["name"]))
        remaining = [g for g in remaining if g is not ready]
    return placed


def plan_items(groups: list[dict]) -> list[dict]:
    """Return the execution order as items with index, after, chain and label fields.

    Chains are the connected components of the "after" graph, numbered by the smallest plan
    position of their members. Inside a chain each step also waits for the step before it.
    """
    ordered = order_groups(groups)  # exits 2 on unknown names or cycles
    plan_pos = {str(g["name"]): i for i, g in enumerate(groups)}
    parent = {name: name for name in plan_pos}

    def root(name: str) -> str:
        while parent[name] != name:
            name = parent[name]
        return name

    for group in groups:
        for dep in after_of(group):
            parent[root(str(group["name"]))] = root(dep)
    members: dict[str, list[dict]] = {}
    for group in ordered:  # topological order, so each chain keeps a valid order
        members.setdefault(root(str(group["name"])), []).append(group)
    chains = sorted(members.values(), key=lambda chain: min(plan_pos[str(g["name"])] for g in chain))

    items: list[dict] = []
    index_of: dict[str, int] = {}
    for chain_no, chain in enumerate(chains, start=1):
        for step, group in enumerate(chain, start=1):
            index = len(items) + 1  # chains are contiguous in the execution order
            index_of[str(group["name"])] = index
            deps = {index_of[dep] for dep in after_of(group)}
            if step > 1:
                deps.add(index - 1)  # the previous step of the chain
            label = str(chain_no) if len(chain) == 1 else f"{chain_no}.{step}"
            items.append({
                "index": index,
                "after": sorted(deps),
                "group": group,
                "chain": chain_no,
                "step": step,
                "chain_len": len(chain),
                "label": label,
                "mode": "async" if len(chain) == 1 else "sync",
            })
    return items


def start_group(group: dict, cwd: str, permission_mode: str | None) -> tuple[str | None, str]:
    name = session_name(group)
    cmd = ["claude", "--bg", "-n", name]
    if permission_mode:
        cmd += ["--permission-mode", permission_mode]
    cmd.append(group["prompt"])
    env = dict(os.environ, CLAUDE_SPLIT_CHILD="1")
    env.pop("CLAUDE_CODE_SESSION_ID", None)
    proc = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=300)
    out = (proc.stdout or "") + (proc.stderr or "")
    if "Workspace not trusted" in out:
        print(
            f"Workspace {cwd} is not trusted by Claude Code. Run `claude` once in that "
            "directory and accept the trust prompt, then dispatch again.",
            file=sys.stderr,
        )
        sys.exit(2)
    match = BG_RE.search(out)
    if not match:
        print(f"Could not read a session id for '{name}': {out.strip()[:200]}", file=sys.stderr)
        return None, name
    return match.group(1), name


def find_parent_transcript(parent: str | None) -> str:
    """Return the absolute path of the parent session transcript, or "" when unknown."""
    if not parent:
        return ""
    pattern = os.path.expanduser(os.path.join("~/.claude/projects/*", parent + ".jsonl"))
    matches = sorted(glob.glob(pattern))
    return os.path.abspath(matches[0]) if matches else ""


def record(entry: dict) -> None:
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def open_konsole(session_id: str) -> None:
    subprocess.Popen(
        ["konsole", "--new-tab", "-e", "claude", "attach", session_id],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def base_fields(item: dict, started: str, common: dict) -> dict:
    group = item["group"]
    return {
        "name": session_name(group),
        "title": group_title(group),
        "cwd": common["cwd"],
        "prompt_head": group["prompt"][:120],
        "started": started,
        "parent": common["parent"],
        "group": common["group"],
        "index": item["index"],
        "total": common["total"],
        "parent_transcript": common["parent_transcript"],
        "parent_cwd": common["parent_cwd"],
        "after": item["after"],
        "chain": item["chain"],
        "step": item["step"],
        "chain_len": item["chain_len"],
        "label": item["label"],
        "mode": item["mode"],
    }


def item_ended(agent: dict | None, started: float, now: float) -> bool:
    """An item ended when its live agent is not busy, or when it has been missing past the grace."""
    if now - started < MIN_RUN_S:
        return False
    if agent is not None:
        return not (agent.get("status") == "busy" or agent.get("state") == "working")
    return now - started > MISSING_GRACE_S


def load_live_agents() -> dict | None:
    """Return {id: agent} from `claude agents --json --all`, or None when the list cannot be read."""
    try:
        proc = subprocess.run(["claude", "agents", "--json", "--all"], capture_output=True, text=True, timeout=60)
        data = json.loads(proc.stdout or "[]")
    except Exception as exc:
        print(f"Could not read `claude agents --json --all`: {exc}", file=sys.stderr)
        return None
    items = data if isinstance(data, list) else data.get("agents", [])
    return {item["id"]: item for item in items if isinstance(item, dict) and item.get("id")}


def dep_ended(state: dict, dep: int, agents: dict, now: float) -> bool:
    entry = state["launched"].get(str(dep))
    if entry is None:
        return False  # still waiting itself
    if entry.get("id") is None:
        return True  # launch failed: release the dependents instead of hanging
    return item_ended(agents.get(entry["id"]), entry["started"], now)


def launch_waiting(state: dict, item: dict) -> None:
    group = item["group"]
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    try:
        session_id, _ = start_group(group, state["common"]["cwd"], state["permission_mode"])
    except (Exception, SystemExit) as exc:
        print(f"Launch failed for '{session_name(group)}': {exc}", file=sys.stderr)
        session_id = None
    state["launched"][str(item["index"])] = {"id": session_id, "started": time.time()}
    if session_id is None:
        print(f"No session id for '{session_name(group)}'; its dependents are released.", file=sys.stderr)
        return
    record({"id": session_id, **base_fields(item, started, state["common"])})
    if state["view"] == "konsole":
        open_konsole(session_id)


def wait_main(path: str) -> int:
    """Poll the live agents and launch each waiting group once all its dependencies ended."""
    with open(path, encoding="utf-8") as fh:
        state = json.load(fh)
    print(f"Waiter started with {len(state['pending'])} waiting group(s).", file=sys.stderr)
    while state["pending"]:
        if time.time() > state["deadline"]:
            print(f"Gave up after 12 h; {len(state['pending'])} group(s) never started.", file=sys.stderr)
            return 1
        agents = load_live_agents()
        if agents is not None:
            now = time.time()
            still = []
            for item in state["pending"]:
                if all(dep_ended(state, dep, agents, now) for dep in item["after"]):
                    launch_waiting(state, item)
                else:
                    still.append(item)
            state["pending"] = still
        if state["pending"]:
            time.sleep(POLL_INTERVAL_S)
    return 0


def spawn_waiter(state: dict, group_id: str) -> str:
    """Write the waiter state file and start one detached waiter for this run."""
    os.makedirs(STATE_DIR, exist_ok=True)
    state_path = os.path.join(STATE_DIR, f"prompt-splitter-wait-{group_id}.json")
    with open(state_path, "w", encoding="utf-8") as fh:
        json.dump(state, fh)
    log_path = os.path.join(STATE_DIR, f"prompt-splitter-waiter-{group_id}.log")
    env = dict(os.environ, CLAUDE_SPLIT_CHILD="1")
    env.pop("CLAUDE_CODE_SESSION_ID", None)
    with open(log_path, "a", encoding="utf-8") as log:
        subprocess.Popen(
            [sys.executable, os.path.abspath(__file__), "--wait", state_path],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    return log_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("plan", nargs="?")
    parser.add_argument("--view", choices=["konsole", "none"], default="none")
    parser.add_argument("--permission-mode", choices=PERMISSION_MODES, default=None)
    parser.add_argument(
        "--parent",
        default=None,
        help="Parent Claude session id (defaults to CLAUDE_CODE_SESSION_ID).",
    )
    parser.add_argument("--wait", default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.wait:
        return wait_main(args.wait)
    if not args.plan:
        parser.error("plan.json is required")
    parent = args.parent or os.environ.get("CLAUDE_CODE_SESSION_ID") or None
    group_id = uuid.uuid4().hex[:8]

    with open(args.plan, encoding="utf-8") as fh:
        plan = json.load(fh)
    cwd = plan["cwd"]
    groups = plan.get("groups") or []
    if not groups:
        print("Plan has no groups.", file=sys.stderr)
        return 1
    items = plan_items(groups)  # exits 2 before anything is launched or recorded

    common = {
        "cwd": os.path.realpath(cwd),
        "parent": parent,
        "group": group_id,
        "total": len(items),
        "parent_transcript": find_parent_transcript(parent),
        "parent_cwd": os.getcwd(),
    }
    rows = []  # (item, session name, id or status)
    launched: dict[str, dict] = {}
    pending: list[dict] = []
    for item in items:
        index = item["index"]
        group = item["group"]
        started = dt.datetime.now(dt.timezone.utc).isoformat()
        name = session_name(group)
        if item["after"]:
            record({
                "id": f"wait-{group_id}-{index}",
                "state": "waiting",
                **base_fields(item, started, common),
            })
            pending.append(item)
            rows.append((item, name, "aguardando"))
            continue
        session_id, name = start_group(group, cwd, args.permission_mode)
        if session_id is None:
            launched[str(index)] = {"id": None, "started": time.time()}
            rows.append((item, name, "-"))
            continue
        launched[str(index)] = {"id": session_id, "started": time.time()}
        record({"id": session_id, **base_fields(item, started, common)})
        if args.view == "konsole":
            open_konsole(session_id)
        rows.append((item, name, session_id))

    if pending:
        state = {
            "common": common,
            "permission_mode": args.permission_mode,
            "view": args.view,
            "deadline": time.time() + WAIT_GIVE_UP_S,
            "launched": launched,
            "pending": pending,
        }
        log_path = spawn_waiter(state, group_id)
        print(f"{len(pending)} group(s) wait for others; a background waiter launches them (log: {log_path}).")

    width = max(len(name) for _, name, _ in rows)
    label_width = max(len(item["label"]) for item, _, _ in rows)
    print(f"  {'#'.ljust(label_width)}  {'name'.ljust(width)}  id")
    for item, name, sid in rows:
        print(f"{PENDING_MARK} {item['label'].ljust(label_width)}  {name.ljust(width)}  {sid}")
    print(LEGEND)
    print("\nWatch: `claude agents` (panel), `claude attach <id>`, `/prompt-splitter:sessions`.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
