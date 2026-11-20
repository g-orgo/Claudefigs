"""Hides split child sessions from the Claude Code /resume picker.

The picker drops a session whose transcript tail carries a `continued-in` record
pointing at a target transcript that exists and has content. This module writes
that record for the sessions the splitter launched, reopens nothing and keeps
the transcript itself untouched.
"""

import datetime as dt
import glob
import json
import os
import sys
import time

STATE_FILE = os.path.expanduser("~/.claude/state/prompt-splitter.jsonl")
PROJECTS_DIR = os.path.expanduser("~/.claude/projects")
TAIL_BYTES = 256 * 1024
# Seconds to wait between the deferred marks after a Stop hook.
DEFER_DELAYS = (2, 6)
TARGET_MARK = b'"parentUuid":'
# Claude Code matches this exact text, so the marker must be written without spaces.
MARKER_TEXT = '"type":"continued-in"'


def _completed(obj: dict) -> bool:
    """True when the record ends the session: a finished assistant turn or a human prompt."""
    kind = obj.get("type")
    message = obj.get("message")
    if not isinstance(message, dict):
        message = {}
    api_error = obj.get("isApiErrorMessage") is True or message.get("isApiErrorMessage") is True
    if kind == "assistant":
        return isinstance(message.get("stop_reason"), str) and not api_error
    if kind == "user":
        if obj.get("isMeta") is True or message.get("isMeta") is True:
            return False
        content = message.get("content")
        if isinstance(content, str):
            return True
        if isinstance(content, list):
            return any(isinstance(block, dict) and block.get("type") == "text" for block in content)
    return False


def needs_marker(tail_text: str, target: str) -> bool:
    """True when the tail does not yet hide the session behind `target`."""
    try:
        for line in reversed(tail_text.splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if not isinstance(obj, dict):
                continue
            if obj.get("type") == "continued-in":
                if MARKER_TEXT not in line:
                    continue  # a spaced marker is invisible to Claude Code
                return obj.get("continuedInSessionId") != target
            if _completed(obj):
                return True
        return True
    except Exception:
        return True


def target_for(transcript_path: str, session_id: str, parent: str) -> str:
    """The parent transcript when it exists, else the session itself."""
    try:
        if parent:
            sibling = os.path.join(os.path.dirname(transcript_path), parent + ".jsonl")
            if os.path.exists(sibling):
                return parent
    except Exception:
        pass
    return session_id


def hide(transcript_path: str, session_id: str, parent: str) -> bool:
    """Append the continued-in marker once; True when a line was written."""
    try:
        before = os.stat(transcript_path)
        with open(transcript_path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - TAIL_BYTES))
            data = fh.read()
        if TARGET_MARK not in data:
            return False
        tail = data.decode("utf-8", "replace")
        target = target_for(transcript_path, session_id, parent)
        if not needs_marker(tail, target):
            return False
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        marker = {
            "type": "continued-in",
            "timestamp": now,
            "sessionId": session_id,
            "continuedInSessionId": target,
        }
        line = json.dumps(marker, separators=(",", ":")) + "\n"
        prefix = "" if data.endswith(b"\n") else "\n"
        fd = os.open(transcript_path, os.O_WRONLY | os.O_APPEND)
        try:
            os.write(fd, (prefix + line).encode("utf-8"))
        finally:
            os.close(fd)
        # Keep the modification time, so the marker does not move the session in any list.
        os.utime(transcript_path, ns=(before.st_atime_ns, before.st_mtime_ns))
        return True
    except Exception:
        return False


def parent_of(session_id: str) -> str:
    """The parent recorded for this split session, or ""."""
    try:
        override = os.environ.get("CLAUDE_SPLIT_PARENT")
        if override:
            return override
        want = session_id[:8]
        parent = ""
        with open(STATE_FILE, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if isinstance(obj, dict) and obj.get("id") == want:
                    found = obj.get("parent")
                    parent = found if isinstance(found, str) else ""
        return parent
    except Exception:
        return ""


def _records() -> list[dict]:
    try:
        out = []
        with open(STATE_FILE, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if isinstance(obj, dict) and obj.get("id"):
                    out.append(obj)
        return out
    except Exception:
        return []


SEEN_FILE = os.path.expanduser("~/.claude/state/prompt-splitter-hidden.json")


def _load_seen() -> dict:
    try:
        with open(SEEN_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_seen(seen: dict) -> None:
    try:
        tmp = SEEN_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(seen, fh)
        os.replace(tmp, SEEN_FILE)
    except Exception:
        pass


def _backfill(quiet: bool = False) -> None:
    """Hides every recorded split session. A file whose size and mtime match the last
    checked state is skipped with a stat only, so this is cheap enough for SessionStart."""
    seen = _load_seen()
    hidden = 0
    checked = 0
    for entry in _records():
        key = str(entry.get("id"))
        parent = entry.get("parent") if isinstance(entry.get("parent"), str) else ""
        pattern = os.path.join(PROJECTS_DIR, "*", key + "*.jsonl")
        for path in sorted(glob.glob(pattern)):
            stem = os.path.basename(path)[: -len(".jsonl")]
            if not stem.startswith(key):
                continue
            checked += 1
            try:
                st = os.stat(path)
            except OSError:
                continue
            state = [st.st_size, st.st_mtime_ns]
            if seen.get(path) == state:
                continue
            if hide(path, stem, parent):
                hidden += 1
                try:
                    st = os.stat(path)
                    state = [st.st_size, st.st_mtime_ns]
                except OSError:
                    continue
            seen[path] = state
    _save_seen(seen)
    if not quiet:
        print(f"hidden {hidden} of {checked}")


def _hook() -> None:
    try:
        if os.environ.get("CLAUDE_SPLIT_CHILD") != "1":
            return
        raw = sys.stdin.read()
        data = json.loads(raw or "{}")
        if not isinstance(data, dict):
            return
        transcript = data.get("transcript_path")
        session_id = data.get("session_id")
        if not transcript or not session_id:
            return
        transcript, session_id = str(transcript), str(session_id)
        parent = parent_of(session_id)
        if "--defer" not in sys.argv[1:]:
            hide(transcript, session_id, parent)
            return
        # Stop fires before the final reply reaches the transcript, so a detached child
        # marks it again once the engine has written it. The hook itself returns at once.
        if os.fork() != 0:
            return
        os.setsid()
        if os.fork() != 0:
            os._exit(0)
        null = os.open(os.devnull, os.O_RDWR)
        for fd in (0, 1, 2):
            os.dup2(null, fd)  # free the hook's pipes, so Claude Code does not wait for this child
        for delay in DEFER_DELAYS:
            time.sleep(delay)
            hide(transcript, session_id, parent)
        os._exit(0)
    except Exception:
        return


def main() -> int:
    try:
        if "--hook" in sys.argv[1:]:
            _hook()
        elif "--all" in sys.argv[1:]:
            _backfill(quiet="--quiet" in sys.argv[1:])
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
