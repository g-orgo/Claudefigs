#!/usr/bin/env python3
"""PreToolUse hook for Bash: blocks `opencode run` while the opencode free usage limit is exhausted.

On every Bash call it scans the tail of opencode's log for the limit error. When a new one shows up,
it records `blocked_until` (next local midnight after the error) in ~/.claude/state/opencode-limit.json
and kills running `opencode run` processes, which otherwise keep retrying. While the block is active,
any command that starts `opencode run` is denied with a reason telling the operator to do the work itself.

Manual override: delete the state file, or set "blocked_until" by hand.
"""
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

STATE = Path.home() / ".claude/state/opencode-limit.json"
LOG = Path.home() / ".local/share/opencode/log/opencode.log"
SIGNATURE = "Free usage limit reached"
TAIL_BYTES = 512 * 1024
# `opencode run` in command position (line start, after ; & | ( or a timeout/exec/nohup prefix), not inside prose.
RUN_PATTERN = re.compile(
    r"(?:^|[;&|(])\s*(?:(?:timeout\s+\S+|nohup|exec)\s+)*(?:\S*/)?opencode\s+run\b",
    re.MULTILINE,
)
TIMESTAMP = re.compile(r"timestamp=(\S+)")


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {}


def latest_limit_error() -> datetime | None:
    try:
        with LOG.open("rb") as handle:
            handle.seek(0, 2)
            handle.seek(max(0, handle.tell() - TAIL_BYTES))
            text = handle.read().decode("utf-8", "replace")
    except OSError:
        return None
    latest = None
    for line in text.splitlines():
        if SIGNATURE not in line:
            continue
        match = TIMESTAMP.search(line)
        if not match:
            continue
        try:
            latest = datetime.fromisoformat(match.group(1).replace("Z", "+00:00"))
        except ValueError:
            continue
    return latest


def next_local_midnight(moment: datetime) -> datetime:
    local = moment.astimezone()
    return (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


def kill_opencode_runs() -> None:
    # Only processes whose executable is opencode with the `run` subcommand; shells that merely
    # mention "opencode run" in their command line must survive.
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            argv = (proc / "cmdline").read_bytes().split(b"\0")
        except OSError:
            continue
        if len(argv) > 1 and Path(argv[0].decode(errors="replace")).name == "opencode" and argv[1] == b"run":
            subprocess.run(["kill", proc.name], check=False)


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return
    command = (payload.get("tool_input") or {}).get("command", "")
    now = datetime.now(timezone.utc).astimezone()
    state = load_state()

    error_at = latest_limit_error()
    last_seen = state.get("last_error_at")
    if error_at and (not last_seen or error_at > datetime.fromisoformat(last_seen)):
        state = {
            "last_error_at": error_at.isoformat(),
            "blocked_until": next_local_midnight(error_at).isoformat(),
            "reason": SIGNATURE,
        }
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(state, indent=2) + "\n")
        if next_local_midnight(error_at) > now:
            kill_opencode_runs()

    blocked_until = state.get("blocked_until")
    if not blocked_until or not RUN_PATTERN.search(command):
        return
    until = datetime.fromisoformat(blocked_until)
    if now >= until:
        return
    reason = (
        f"opencode free usage limit reached; opencode is blocked until {until.isoformat()} "
        f"(state: {STATE}). Do not retry opencode: do the work yourself with your own tools "
        "and say in the report that you took over because of the opencode limit."
    )
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))


if __name__ == "__main__":
    main()
