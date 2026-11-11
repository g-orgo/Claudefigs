"""Shapes shared by the data, scene and entry layers of the office viewer."""
from dataclasses import dataclass, field


@dataclass
class Line:
    role: str  # "voce" | "claude" | "tool"
    text: str
    count: int = 1


@dataclass(frozen=True)
class Question:
    """One question of an AskUserQuestion call a session left without an answer."""
    ask: str  # id of the tool_use block; one call may hold several questions
    header: str
    text: str
    options: tuple[tuple[str, str], ...] = ()  # (label, description) pairs
    multi: bool = False  # several options may be chosen
    asked_ms: float = 0.0


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
    parent: str = ""  # id of the session that dispatched this split
    in_cwd: bool = True  # the split or its parent session ran under the viewer's working directory
    questions: list[Question] = field(default_factory=list)  # pending AskUserQuestion items, only in the "ask" state
    limit: str = ""  # "5-hour" | "session" | "weekly" when the last record is a usage-limit stop
    limit_at_ms: float = 0.0
    limit_reset_ms: float = 0.0  # 0 when the reset time is unknown

    @property
    def room_key(self) -> str:
        """What one door of the hall stands for: the parent session, or the group for records without one."""
        return self.parent or self.group
