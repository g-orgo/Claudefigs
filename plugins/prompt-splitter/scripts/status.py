"""Show the last 20 sessions dispatched by prompt-splitter as a tree per parent session.

Joins ~/.claude/state/prompt-splitter.jsonl with `claude agents --json --all`.
Only sessions under the current directory are listed unless --all is given.
Parent titles come from the parent transcript (custom-title, then ai-title).
"""

import argparse
import datetime as dt
import glob
import json
import os
import re
import subprocess
import sys

STATE_FILE = os.path.expanduser("~/.claude/state/prompt-splitter.jsonl")
NO_PARENT_HEADER = "Sem sessao de origem (versao antiga)"
# Completion icons shown before each item (same marks as dispatch.py).
DONE_MARK = "✓"
PENDING_MARK = "○"
LEGEND = "✓ completo   ○ em andamento ou aguardando"
# Bytes read from the end of a child transcript to find an unanswered question.
TAIL_BYTES = 64 * 1024


def normalize_path(path: str) -> str:
    """Return the realpath, with "/var/home/" folded into "/home/" (same folder on Atomic systems)."""
    real = os.path.realpath(path)
    return real[len("/var"):] if real.startswith("/var/home/") else real


def is_under(path: str, base: str) -> bool:
    return path == base or path.startswith(base.rstrip("/") + "/")


def load_records(only_cwd: str | None, limit: int = 20) -> list[dict]:
    """Return the last record per (group, index), in file order, limited to limit.

    With only_cwd set, keep records whose cwd or parent_cwd is that directory or under it.
    """
    if not os.path.exists(STATE_FILE):
        return []
    latest: dict = {}
    with open(STATE_FILE, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(rec, dict):
                continue
            if only_cwd is not None and not any(
                isinstance(p, str) and p and is_under(normalize_path(p), only_cwd)
                for p in (rec.get("cwd"), rec.get("parent_cwd"))
            ):
                continue
            if isinstance(rec.get("index"), int):
                key = (str(rec.get("group") or "-"), rec["index"])
            else:
                key = ("id", rec.get("id"))
            latest.pop(key, None)
            latest[key] = rec
    return list(latest.values())[-limit:]


def load_agents() -> dict:
    try:
        proc = subprocess.run(
            ["claude", "agents", "--json", "--all"],
            capture_output=True, text=True, timeout=60,
        )
        data = json.loads(proc.stdout or "[]")
    except Exception as exc:
        print(f"Could not read `claude agents --json --all`: {exc}", file=sys.stderr)
        return {}
    items = data if isinstance(data, list) else data.get("agents", [])
    result = {}
    for item in items:
        if isinstance(item, dict) and item.get("id"):
            result[item["id"]] = item
    return result


_TRANSCRIPT_CACHE: dict[str, str] = {}


def find_transcript(parent: str) -> str:
    """Glob the parent transcript once per parent (first match), "" when none."""
    if parent not in _TRANSCRIPT_CACHE:
        pattern = os.path.expanduser(os.path.join("~/.claude/projects/*", parent + ".jsonl"))
        matches = sorted(glob.glob(pattern))
        _TRANSCRIPT_CACHE[parent] = matches[0] if matches else ""
    return _TRANSCRIPT_CACHE[parent]


def parent_title(parent: str, transcript: str) -> str:
    """Return the last custom-title, else the last ai-title, else a short session label."""
    fallback = f"Sessao {parent[:8]}"
    if not transcript or not os.path.isfile(transcript):
        transcript = find_transcript(parent)
    if not transcript or not os.path.isfile(transcript):
        return fallback
    custom = None
    ai = None
    try:
        # Read line by line: transcripts can be many MB.
        with open(transcript, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if '"custom-title"' not in line and '"ai-title"' not in line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                kind = obj.get("type")
                if kind == "custom-title" and obj.get("customTitle"):
                    custom = obj["customTitle"]
                elif kind == "ai-title" and obj.get("aiTitle"):
                    ai = obj["aiTitle"]
    except OSError:
        return fallback
    return custom or ai or fallback


# Readable pt-BR labels for the live agent states; unknown states are shown as they are.
STATE_LABELS = {
    "working": "rodando",
    "done": "concluida",
    "failed": "falhou",
}


def child_transcript(rec: dict, agent: dict) -> str:
    """Return ~/.claude/projects/<slug>/<sessionId>.jsonl for the child, slug = cwd with non-alphanumerics as "-"."""
    cwd = os.path.realpath(str(rec.get("cwd") or ""))
    slug = re.sub(r"[^A-Za-z0-9]", "-", cwd)
    session_id = str(agent.get("sessionId") or rec.get("id") or "")
    return os.path.expanduser(os.path.join("~/.claude/projects", slug, session_id + ".jsonl"))


def awaits_answer(path: str) -> bool:
    """True when the child's last assistant turn asks the user something it cannot proceed without."""
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - TAIL_BYTES))
            lines = fh.read().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return False
    if size > TAIL_BYTES and lines:
        lines = lines[1:]  # the first line may be cut in the middle
    records = []
    for line in lines:
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    last = next((i for i in range(len(records) - 1, -1, -1) if records[i].get("type") == "assistant"), None)
    if last is None:
        return False
    blocks = (records[last].get("message") or {}).get("content")
    if not isinstance(blocks, list):
        return False
    answered = set()
    for rec in records[last + 1:]:
        content = (rec.get("message") or {}).get("content")
        for block in content if isinstance(content, list) else []:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                answered.add(block.get("tool_use_id"))
    for block in blocks:
        if isinstance(block, dict) and block.get("type") == "tool_use":
            if block.get("name") == "AskUserQuestion" or block.get("id") not in answered:
                return True  # a question, or a permission request with no result yet
    return False


def item_state(rec: dict, agents: dict) -> tuple[str, bool]:
    """Return (status text, complete) for an item that has started."""
    agent = agents.get(rec.get("id"))
    if agent is None:
        return "encerrada", True
    live = str(agent.get("state") or agent.get("status") or "unknown")
    if agent.get("status") == "busy" or live == "working":
        return STATE_LABELS.get(live, live), False
    if live == "failed":
        return STATE_LABELS["failed"], False
    if awaits_answer(child_transcript(rec, agent)):
        return "aguarda sua resposta", False
    if live == "blocked":
        return "concluida, aguarda voce", True  # finished its turn and waits for the user
    return STATE_LABELS.get(live, live), True


def group_records(records: list[dict]) -> list[tuple[str, list[dict]]]:
    """Group records by `group`, keeping the order of first appearance (most recent last)."""
    groups: dict[str, list[dict]] = {}
    for rec in records:
        key = str(rec.get("group") or "-")
        groups.setdefault(key, []).append(rec)
    return list(groups.items())


def item_label(rec: dict) -> str:
    """Return the child label: title, else prompt_head clipped to 60, else the name without "split-"."""
    title = str(rec.get("title") or "").strip()
    if title:
        return title
    head = str(rec.get("prompt_head") or "").strip().splitlines()[0:1]
    head = head[0].strip() if head else ""
    if head:
        return head if len(head) <= 60 else head[:57].rstrip() + "..."
    name = str(rec.get("name", "?"))
    return name[len("split-"):] if name.startswith("split-") else name


def group_started(recs: list[dict]) -> str:
    """Return the local dd/mm HH:MM of the earliest start in the group, "" when unknown."""
    starts = []
    for rec in recs:
        try:
            starts.append(dt.datetime.fromisoformat(str(rec.get("started"))))
        except ValueError:
            continue
    if not starts:
        return ""
    earliest = min(s if s.tzinfo else s.replace(tzinfo=dt.timezone.utc) for s in starts)
    return earliest.astimezone().strftime("%d/%m %H:%M")


def print_group(group_id: str, recs: list[dict], agents: dict) -> None:
    # Children follow their execution index; records without one keep their order inside the group.
    ordered = sorted(
        enumerate(recs),
        key=lambda pair: (pair[1].get("index") if isinstance(pair[1].get("index"), int) else pair[0] + 1, pair[0]),
    )
    labels = {rec.get("index"): item_label(rec) for _, rec in ordered}
    parent = recs[0].get("parent")
    started = group_started(recs)
    when = f"{started}, " if started else ""
    if parent:
        title = parent_title(parent, recs[0].get("parent_transcript") or "")
    else:
        title = NO_PARENT_HEADER
    print(f"{title}  ({when}{len(recs)} itens)")
    print("│")
    count = len(ordered)
    for position, (_, rec) in enumerate(ordered, start=1):
        branch = "└" if position == count else "├"
        index = rec.get("index")
        # Records written before chains have no label: fall back to the execution index.
        label = str(rec.get("label") or (index if isinstance(index, int) else "?"))
        if rec.get("state") == "waiting":
            deps = ", ".join(labels.get(dep, "?") for dep in rec.get("after") or [])
            status, complete = f"aguardando {deps}", False
        else:
            status, complete = item_state(rec, agents)
        mark = DONE_MARK if complete else PENDING_MARK
        print(f"{branch}──► {mark} {label}  {item_label(rec)}  {status}  {rec.get('id', '?')}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--all",
        action="store_true",
        help="List the sessions of every directory, not only the current one.",
    )
    args = parser.parse_args()
    only_cwd = None if args.all else normalize_path(os.getcwd())
    records = load_records(only_cwd)
    if not records:
        print("No prompt-splitter sessions recorded yet.")
        return 0
    agents = load_agents()
    for group_id, recs in group_records(records):
        print_group(group_id, recs, agents)
    print("Use /splits para navegar com as setas e abrir uma sessao.")
    print(LEGEND)
    return 0


if __name__ == "__main__":
    sys.exit(main())
