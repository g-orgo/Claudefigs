"""PostToolUse hook for Read: note files with 3+ numbered items, once per (session, file).

Never fails: any error results in silence and exit code 0.
"""

import json
import os
import re
import sys

def is_excluded(path: str) -> bool:
    """True when the path lives inside the plugin root or inside ~/.claude/ (never user work files)."""
    real = os.path.realpath(path)
    hooks_dir = os.path.dirname(os.path.realpath(__file__))
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT") or os.path.dirname(hooks_dir)
    roots = [os.path.realpath(plugin_root), os.path.realpath(os.path.expanduser("~/.claude/"))]
    return any(real == root or real.startswith(root.rstrip(os.sep) + os.sep) for root in roots)


STATE_FILE = os.path.expanduser("~/.claude/state/prompt-splitter-seen.json")
MAX_ENTRIES = 200
MAX_FILE_BYTES = 300 * 1024
ITEM_RE = re.compile(r"^\s*(?:\(\d+\)|\d+\s*[).]|\d+\s+-)", re.MULTILINE)

CONTEXT = (
    "prompt-splitter: {path} contains {n} numbered items. If the user asked you to execute "
    "this file as a list of requests/corrections, do not start yet: ask with AskUserQuestion "
    "(same 3 options: 'Split into sessions (Recommended)', 'Split and open Konsole tabs', "
    "'Keep in this session') whether to split into background sessions. If it is just "
    "reference material, ignore this note."
)


def load_seen() -> list[str]:
    try:
        with open(STATE_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
        return [str(x) for x in data] if isinstance(data, list) else []
    except Exception:
        return []


def save_seen(entries: list[str]) -> None:
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as fh:
        json.dump(entries[-MAX_ENTRIES:], fh)


def main() -> int:
    if os.environ.get("CLAUDE_SPLIT_CHILD") == "1":
        return 0
    data = json.loads(sys.stdin.read() or "{}")
    tool_input = data.get("tool_input") or {}
    path = tool_input.get("file_path") if isinstance(tool_input, dict) else None
    if not isinstance(path, str) or not path:
        return 0
    path = os.path.expanduser(path)
    if is_excluded(path):
        return 0
    if not os.path.isfile(path) or os.path.getsize(path) > MAX_FILE_BYTES:
        return 0
    with open(path, encoding="utf-8", errors="ignore") as fh:
        count = len(ITEM_RE.findall(fh.read()))
    if count < 3:
        return 0
    key = f"{data.get('session_id') or ''}|{path}"
    seen = load_seen()
    if key in seen:
        return 0
    save_seen(seen + [key])
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": CONTEXT.format(path=path, n=count),
        }
    }
    print(json.dumps(output))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
