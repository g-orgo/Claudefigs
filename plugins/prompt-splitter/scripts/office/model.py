"""Shapes shared by the data, scene and entry layers of the office viewer."""
from dataclasses import dataclass, field


@dataclass
class Line:
    role: str  # "voce" | "claude" | "tool"
    text: str
    count: int = 1


@dataclass
class Worker:
    id: str
    session_id: str
    name: str
    title: str
    item_label: str
    group: str
    index: int
    cwd: str
    started_ms: float
    state: str  # "working" | "thinking" | "waiting" | "ask" | "blocked" | "done" | "failed"
    activity: str = "none"  # "code" | "term" | "doc" | "web" | "delegate" | "none"
    after: list[int] = field(default_factory=list)
    lines: list[Line] = field(default_factory=list)
    subagents: int = 0
    attachable: bool = False  # the agent registry knows this session, so `claude attach` can open it
    room_title: str = ""  # title of the parent session of this split's group
