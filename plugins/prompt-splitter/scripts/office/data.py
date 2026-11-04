"""Read-only data layer of the office viewer: turns split state, agents and transcripts into Workers."""
import datetime as dt
import glob
import json
import os
import re
import subprocess
import sys
import threading
import time
from urllib.parse import urlparse

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import status  # noqa: E402  (scripts dir is added to sys.path above)
from office.model import Line, Worker  # noqa: E402

TAIL = 200  # activity lines kept per worker
CLIP = 300  # characters kept per transcript line
LABEL_MAX = 60
PREFIX = "split-"
TAIL_BYTES = 256 * 1024
SPAWN_GRACE_MS = 90_000
RECORDS_PERIOD = 1.5
AGENTS_PERIOD = 3.0
AGENTS_TIMEOUT = 10
RECENT_GROUPS = 40
ALL_RECORDS = 80  # the warehouse shows every directory, so this reaches further back than the side panel

# tool name -> (template, input key, how the value is shaped, fallback when the value is missing)
ACTIVITY = {
    "Bash": ("Estou rodando um comando para {value}", "description", "desc", "Estou rodando um comando no terminal"),
    "Read": ("Estou lendo o arquivo {value}", "file_path", "base", "Estou lendo arquivos"),
    "Grep": ("Estou procurando \"{value}\" no código", "pattern", "clip", "Estou procurando no código"),
    "Glob": ("Estou procurando arquivos com {value}", "pattern", "clip", "Estou procurando arquivos"),
    "Edit": ("Agora vou modificar o arquivo {value}", "file_path", "base", "Agora vou modificar arquivos"),
    "Write": ("Agora vou escrever o arquivo {value}", "file_path", "base", "Agora vou escrever arquivos"),
    "NotebookEdit": ("Agora vou modificar o notebook {value}", "notebook_path", "base", "Agora vou modificar um notebook"),
    "Agent": ("Estou delegando a um subagent: {value}", "description", "desc", "Estou delegando a um subagent"),
    "WebSearch": ("Estou pesquisando na web sobre {value}", "query", "text", "Estou pesquisando na web"),
    "WebFetch": ("Estou consultando a página {value}", "url", "host", "Estou consultando uma página da web"),
    "Skill": ("Estou usando a skill {value}", "skill", "clip", "Estou usando uma skill"),
}
# tools whose line never changes with the input
FIXED_ACTIVITY = {
    "TodoWrite": "Estou atualizando minha lista de tarefas",
    "AskUserQuestion": "Estou fazendo uma pergunta",
}
ACTIVITY_KIND = {
    "Bash": "term",
    "Read": "doc",
    "Grep": "doc",
    "Glob": "doc",
    "Edit": "code",
    "Write": "code",
    "NotebookEdit": "code",
    "WebSearch": "web",
    "WebFetch": "web",
    "Agent": "delegate",
}

_cache_lock = threading.Lock()
_tail_cache: dict[str, tuple[float, str]] = {}  # path -> (mtime, tail text)
_lines_cache: dict[str, tuple[float, list[Line]]] = {}  # path -> (mtime, lines)


def display_name(name: str) -> str:
    """Strip the split- prefix from a child name."""
    return name[len(PREFIX):] if name.startswith(PREFIX) else name


def clip(text: str) -> str:
    """Collapse whitespace and keep at most CLIP characters."""
    return re.sub(r"\s+", " ", text)[:CLIP]


INJECTED_TAGS = (
    "system-reminder",
    "task-notification",
    "agent-message",
    "cross-session-message",
    "local-command-stdout",
    "local-command-stderr",
    "local-command-caveat",
    "command-name",
    "command-message",
    "command-args",
    "tools-used-before-summary",
)
_TAG_ALTERNATION = "|".join(re.escape(tag) for tag in INJECTED_TAGS)
_PAIRED_BLOCK = re.compile(rf"<({_TAG_ALTERNATION})(?:\s[^>]*)?>.*?</\1>", re.DOTALL)
_UNTERMINATED_START = re.compile(rf"<(?:{_TAG_ALTERNATION})(?:\s[^>]*)?>")
_ORPHAN_CLOSE = re.compile(rf"\A.*</(?:{_TAG_ALTERNATION})>", re.DOTALL)


def strip_injected(text: str) -> str:
    """Remove harness-injected tag blocks (paired, cut-off opening, orphan closing) from user text."""
    text = _PAIRED_BLOCK.sub("", text)
    if _UNTERMINATED_START.match(text.lstrip()):
        text = ""
    text = _ORPHAN_CLOSE.sub("", text, count=1)
    return text.strip()


def to_ms(value) -> float:
    """Convert an ISO string or a number into epoch milliseconds; 0 when unknown."""
    if isinstance(value, bool) or value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    try:
        text = str(value).strip().replace("Z", "+00:00")
        return dt.datetime.fromisoformat(text).timestamp() * 1000.0
    except ValueError:
        return 0.0


def worker_title(rec: dict) -> str:
    """Title: rec title, else prompt_head cut to 60 chars plus '...', else the display name."""
    title = str(rec.get("title") or "").strip()
    if title:
        return title
    head = str(rec.get("prompt_head") or "").strip()
    if head:
        return head if len(head) <= LABEL_MAX else f"{head[:LABEL_MAX]}..."
    return display_name(str(rec.get("name") or ""))


def parse_entry(line: str):
    """Parse one JSONL line into a dict, or None when it is empty or invalid."""
    if line.strip() == "":
        return None
    try:
        value = json.loads(line)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def blocks_of(content) -> list[tuple[str, str, object]]:
    """Return ('text', text, None) or ('tool', name, input) blocks of a message content."""
    if isinstance(content, str):
        return [("text", content, None)] if content != "" else []
    if not isinstance(content, list):
        return []
    out: list[tuple[str, str, object]] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text" and isinstance(block.get("text"), str) and block["text"] != "":
            out.append(("text", block["text"], None))
        elif block.get("type") == "tool_use" and isinstance(block.get("name"), str):
            out.append(("tool", block["name"], block.get("input")))
    return out


def _lower_first(text: str) -> str:
    """Lowercase the first letter, unless the first word is all caps or has a digit or a dot."""
    word = text.split(" ", 1)[0]
    if word.isupper() or any(ch.isdigit() or ch == "." for ch in word):
        return text
    return text[:1].lower() + text[1:]


_ENGLISH_STOPWORDS = {"the", "and", "to", "of", "with", "from", "for", "in", "on"}
_PT_WORDS = {"de", "do", "da", "dos", "das", "em", "no", "na", "nos", "nas", "para", "com",
             "um", "uma", "os", "as", "ao", "que", "por"}
_NOT_PT_INFINITIVE = {
    "filter", "order", "clear", "enter", "render", "number", "cover", "register", "gather", "error",
    "server", "user", "her", "over", "under", "after", "your", "their", "compiler", "docker", "container",
    "parser", "tar", "jar", "star", "char", "car", "war", "air", "fair", "pair", "dir", "stir", "for", "or",
}
_ACCENTED = set("áàâãéêíóôõúüçÁÀÂÃÉÊÍÓÔÕÚÜÇ")


def looks_portuguese(text: str) -> bool:
    """Heuristic: True when the text reads as pt-BR (accent, pt word or pt infinitive), False when it reads as English."""
    words = re.findall(r"[^\W\d_]+", text.lower())
    if not words:
        return False
    has_accent = any(ch in _ACCENTED for ch in text)
    if not has_accent and any(w in _ENGLISH_STOPWORDS for w in words):
        return False
    if has_accent or any(w in _PT_WORDS for w in words):
        return True
    first = words[0]
    return (first.endswith(("ar", "er", "ir")) and len(first) > 3
            and first not in _NOT_PT_INFINITIVE)


def _shaped(value: str, how: str) -> str:
    """The inserted value of a tool phrase: basename, host, or lowered description, clipped.
    Free text ("desc", "text") that does not read as pt-BR gives "" so the tool's fallback is used."""
    if how == "base":
        value = os.path.basename(value)
    elif how == "host":
        try:
            value = urlparse(value).hostname or ""
        except ValueError:
            value = ""
    value = clip(value).strip()
    if how in ("desc", "text") and value and not looks_portuguese(value):
        return ""
    return _lower_first(value) if how == "desc" and value else value


def activity_label(name: str, tool_input: dict | None = None) -> str:
    """The first-person pt-BR line of a tool call, built from its real input; the fallback when a field is missing."""
    if name in FIXED_ACTIVITY:
        return FIXED_ACTIVITY[name]
    if name not in ACTIVITY:
        return f"Estou usando a ferramenta {clip(name)}"
    template, key, how, fallback = ACTIVITY[name]
    raw = tool_input.get(key) if isinstance(tool_input, dict) else None
    value = _shaped(raw, how) if isinstance(raw, str) else ""
    return template.format(value=value) if value else fallback


def collapse_activity(lines: list[Line]) -> list[Line]:
    """Merge consecutive tool lines with the same text into one line with a count."""
    out: list[Line] = []
    for line in lines:
        last = out[-1] if out else None
        if line.role == "tool" and last is not None and last.role == "tool" and last.text == line.text:
            last.count += 1
        else:
            out.append(Line(role=line.role, text=line.text, count=line.count))
    return out


def transcript_lines(text: str) -> list[Line]:
    """The last TAIL lines of a transcript tail, as the pane shows them."""
    out: list[Line] = []
    for raw in text.split("\n"):
        entry = parse_entry(raw)
        if entry is None:
            continue
        kind = entry.get("type")
        role = "voce" if kind == "user" else "claude" if kind == "assistant" else None
        if role is None:
            continue
        if kind == "user" and (entry.get("isMeta") or entry.get("isCompactSummary")):
            continue
        message = entry.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        for block_kind, value, tool_input in blocks_of(content):
            if block_kind == "tool":
                out.append(Line(role="tool", text=activity_label(value, tool_input)))
            elif role == "voce":
                cleaned = strip_injected(value)
                if cleaned:
                    out.append(Line(role=role, text=clip(cleaned)))
            else:
                out.append(Line(role=role, text=clip(value)))
    return collapse_activity(out)[-TAIL:]


def read_tail(path: str) -> str:
    """Read the last TAIL_BYTES of a file; the first, possibly cut, line is dropped. Cached by mtime."""
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return ""
    with _cache_lock:
        cached = _tail_cache.get(path)
    if cached is not None and cached[0] == mtime:
        return cached[1]
    with open(path, "rb") as handle:
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
        start = max(0, size - TAIL_BYTES)
        handle.seek(start)
        data = handle.read().decode("utf-8", errors="replace")
    if start > 0:
        newline = data.find("\n")
        data = data[newline + 1:] if newline >= 0 else ""
    with _cache_lock:
        _tail_cache[path] = (mtime, data)
    return data


def default_read_lines(path: str) -> list[Line]:
    """Activity lines of a transcript; empty when there is no transcript yet. Cached by mtime."""
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return []
    with _cache_lock:
        cached = _lines_cache.get(path)
    if cached is not None and cached[0] == mtime:
        return list(cached[1])
    lines = transcript_lines(read_tail(path))
    with _cache_lock:
        _lines_cache[path] = (mtime, lines)
    return list(lines)


def last_tool_use(path: str):
    """Name of the tool the last assistant entry ends with, or None."""
    text = read_tail(path)
    for raw in reversed(text.split("\n")):
        entry = parse_entry(raw)
        if entry is None or entry.get("type") != "assistant":
            continue
        message = entry.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        blocks = blocks_of(content)
        if blocks and blocks[-1][0] == "tool":
            return blocks[-1][1]
        return None
    return None


def subagent_count(path: str, now_ms: float) -> int:
    """Unfinished background subagents in the sibling 'subagents' folder of a transcript."""
    if path == "":
        return 0
    folder = f"{path[:-len('.jsonl')]}/subagents" if path.endswith(".jsonl") else f"{path}/subagents"
    try:
        names = os.listdir(folder)
    except OSError:
        return 0
    count = 0
    for name in names:
        if not name.endswith(".meta.json"):
            continue
        base = name[:-len(".meta.json")]
        touched = []
        for candidate in (name, f"{base}.jsonl"):
            try:
                touched.append(os.path.getmtime(os.path.join(folder, candidate)) * 1000.0)
            except OSError:
                pass
        if touched and now_ms - max(touched) >= 15 * 60_000:
            continue
        try:
            with open(os.path.join(folder, name), encoding="utf-8") as handle:
                meta = json.loads(handle.read())
        except (OSError, ValueError):
            continue  # unreadable meta counts as ended
        if isinstance(meta, dict) and meta.get("finished") is not True:
            count += 1
    return count


def map_state(rec: dict, agent, path: str, now_ms: float, started_ms: float):
    """Return (state, activity) of a record following the split-pane rules."""
    if rec.get("state") == "waiting":
        return "waiting", "none"
    if agent is not None:
        running = agent.get("status") == "busy" or agent.get("state") == "working"
    else:
        running = now_ms - started_ms < SPAWN_GRACE_MS
    if running:
        tool = last_tool_use(path) if path else None
        if tool is not None:
            return "working", ACTIVITY_KIND.get(tool, "code")
        return "thinking", "none"
    if agent is not None:
        if agent.get("state") == "failed":
            return "failed", "none"
        if status.awaits_answer(path):
            return "ask", "none"
        if agent.get("state") != "done":
            return "blocked", "none"
    return "done", "none"


_room_titles: dict[str, tuple[float, str]] = {}
ROOM_TITLE_PERIOD = 30.0  # seconds between re-reads of a parent transcript title


def room_title_of(rec: dict, now: float | None = None) -> str:
    """Return the parent session title for a split, reading its transcript at most every ROOM_TITLE_PERIOD seconds."""
    parent = str(rec.get("parent") or "")
    if not parent:
        return ""
    current = time.monotonic() if now is None else now
    cached = _room_titles.get(parent)
    if cached is not None and current - cached[0] < ROOM_TITLE_PERIOD:
        return cached[1]
    title = status.parent_title(parent, rec.get("parent_transcript") or "")
    _room_titles[parent] = (current, title)
    return title


def build_workers(records: list[dict], agents: dict, now_ms: float, read_lines=default_read_lines, cwd: str | None = None) -> list[Worker]:
    """Map split records, live agents and transcripts into ordered Workers. Pure apart from file reads."""
    workers: list[Worker] = []
    for position, rec in enumerate(records):
        agent = agents.get(rec.get("id"))
        agent_dict = agent if isinstance(agent, dict) else None
        probe = agent_dict if agent_dict is not None else {}
        path = status.child_transcript(rec, probe)
        started_ms = to_ms(rec.get("started", probe.get("startedAt")))
        state, activity = map_state(rec, agent_dict, path, now_ms, started_ms)
        subagents = 0
        if state in ("working", "thinking"):
            subagents = subagent_count(path, now_ms)
        index = rec.get("index") if isinstance(rec.get("index"), int) else position + 1
        session_id = str(probe.get("sessionId") or rec.get("id") or "")
        workers.append(Worker(
            id=str(rec.get("id") or rec.get("name") or position),
            session_id=session_id,
            name=str(rec.get("name") or ""),
            title=worker_title(rec),
            item_label=str(rec.get("label") or index),
            group=str(rec.get("group") or "-"),
            index=index,
            cwd=str(rec.get("cwd") or ""),
            started_ms=started_ms,
            state=state,
            activity=activity,
            after=list(rec.get("after") or []),
            lines=read_lines(path) if path else [],
            subagents=subagents,
            attachable=agent_dict is not None,
            room_title=room_title_of(rec),
            parent=str(rec.get("parent") or ""),
            in_cwd=record_in_cwd(rec, cwd),
        ))
    return order_workers(workers)


def full_session_id(session_id: str) -> str:
    """The full id of a session from its short or full id, read from its transcript; "" when unknown or ambiguous."""
    if not session_id:
        return ""
    pattern = os.path.expanduser(os.path.join("~/.claude/projects/*", glob.escape(session_id) + "*.jsonl"))
    stems = {os.path.basename(path)[:-len(".jsonl")] for path in glob.glob(pattern)}
    return stems.pop() if len(stems) == 1 else ""


def record_in_cwd(rec: dict, cwd: str | None) -> bool:
    """True when the split or its parent session ran in that directory or under it; no cwd means every record."""
    if cwd is None:
        return True
    return any(isinstance(p, str) and p and status.is_under(status.normalize_path(p), cwd) for p in (rec.get("cwd"), rec.get("parent_cwd")))


def order_workers(workers: list[Worker]) -> list[Worker]:
    """Keep the most recent groups, newest start first so the top of the list is the latest; members by index."""
    groups: dict[str, list[Worker]] = {}
    for worker in workers:
        groups.setdefault(worker.group, []).append(worker)
    recent = sorted(groups.values(), key=lambda members: max(w.started_ms for w in members), reverse=True)[:RECENT_GROUPS]
    return [worker for members in recent for worker in sorted(members, key=lambda w: w.index)]


def load_agents_once(timeout: int = AGENTS_TIMEOUT):
    """Run 'claude agents --json --all' and return its list of objects, or None on any failure."""
    try:
        done = subprocess.run(
            ["claude", "agents", "--json", "--all"],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
        value = json.loads(done.stdout)
    except Exception:  # every failure keeps the last good result
        return None
    return value if isinstance(value, list) else None


class Poller:
    """Daemon thread that keeps the latest Worker list ready for the viewer."""

    def __init__(self, read_lines=default_read_lines):
        self._read_lines = read_lines
        self._cwd = status.normalize_path(os.getcwd())
        self._lock = threading.Lock()
        self._workers: list[Worker] = []
        self._agents: dict[str, dict] = {}
        self._records: list[dict] = []
        self._records_mtime = None
        self._thread = threading.Thread(target=self._run, name="office-poller", daemon=True)

    def start(self) -> None:
        """Start the polling thread."""
        self._thread.start()

    def snapshot(self) -> list[Worker]:
        """Return the latest workers; never raises."""
        with self._lock:
            return list(self._workers)

    def _read_records(self) -> None:
        try:
            mtime = os.path.getmtime(status.STATE_FILE)
        except OSError:
            self._records, self._records_mtime = [], None
            return
        if mtime == self._records_mtime:
            return
        try:
            self._records = status.load_records(None, ALL_RECORDS)
            self._records_mtime = mtime
        except Exception:
            pass  # keep the last good records

    def _read_agents(self) -> None:
        value = load_agents_once()
        if value is None:
            return
        self._agents = {str(item["id"]): item for item in value if isinstance(item, dict) and item.get("id")}

    def _run(self) -> None:
        next_agents = 0.0
        while True:
            try:
                self._read_records()
                now = time.time()
                if now >= next_agents:
                    self._read_agents()
                    next_agents = now + AGENTS_PERIOD
                workers = build_workers(self._records, self._agents, now * 1000.0, self._read_lines, self._cwd)
                with self._lock:
                    self._workers = workers
            except Exception:
                pass  # the viewer must never see an exception; keep the last snapshot
            time.sleep(RECORDS_PERIOD)
