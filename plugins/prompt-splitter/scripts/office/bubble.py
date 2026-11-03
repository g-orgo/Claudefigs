"""The container above each character: a filled title bar and the tail of the split's activity."""
import re

from .model import Worker
from .term import Frame, char_width

CREAM = (255, 253, 245)
INK = (50, 44, 70)
TOOL = (112, 112, 134)
ROLES = {"voce": ("Voce", (0, 128, 140)), "claude": ("Claude", (160, 60, 170))}
STATE_COLORS = {
    "working": (24, 136, 78), "thinking": (24, 136, 78), "waiting": (200, 110, 0), "ask": (190, 120, 0),
    "blocked": (190, 120, 0), "failed": (205, 50, 60), "done": (112, 112, 134),
}
STATE_TEXT = {
    "working": "rodando", "thinking": "rodando", "ask": "aguarda sua resposta", "blocked": "concluida, aguarda voce",
    "failed": "falhou", "done": "encerrada",
}


def clean(text: str) -> str:
    return re.sub(r"[\x00-\x1f\x7f]+", " ", re.sub(r"\s+", " ", text)).strip()


def width_of(text: str) -> int:
    return sum(char_width(ch) for ch in text)


def clip(text: str, width: int) -> str:
    out, used = "", 0
    for ch in text:
        used += char_width(ch)
        if used > width:
            return out[:-1] + "…" if out else ""
        out += ch
    return out


def wrap(text: str, width: int) -> list[str]:
    """Greedy word wrap by display width; a word wider than the line is cut."""
    rows, row, used = [], "", 0
    for word in clean(text).split(" "):
        size = width_of(word)
        while size > width:
            if row:
                rows.append(row)
                row, used = "", 0
            head = clip(word, width - 1)[:-1] or word[:1]
            rows.append(head)
            word = word[len(head):]
            size = width_of(word)
        if used + size + (1 if row else 0) > width:
            rows.append(row)
            row, used = "", 0
        row, used = (row + " " + word, used + size + 1) if row else (word, size)
    if row:
        rows.append(row)
    return rows


def state_text(worker: Worker, workers: list[Worker]) -> str:
    if worker.state != "waiting":
        return STATE_TEXT.get(worker.state, worker.state)
    group = {w.index: w for w in workers if w.group == worker.group}
    return "aguardando " + ", ".join(group[i].title if i in group else f"item {i}" for i in worker.after)


def body_rows(worker: Worker, workers: list[Worker], width: int, height: int) -> list[tuple[str, tuple, bool]]:
    """The last rows of the activity, as (text, color, bold), with the state always on the last one."""
    rows: list[tuple[str, tuple, bool]] = []
    for line in worker.lines:
        if line.role == "tool":
            label = f"· {clean(line.text)}" + (f" (x{line.count})" if line.count > 1 else "")
            rows += [(row, TOOL, False) for row in wrap(label, width)]
        else:
            name, color = ROLES.get(line.role, (line.role, INK))
            rows.append((name, color, True))
            rows += [(row, INK, False) for row in wrap(line.text, width)]
    if worker.subagents > 0:
        count = worker.subagents
        rows.append((f"{count} subagent{'s' if count > 1 else ''} rodando", TOOL, False))
    state = clip(state_text(worker, workers), width)
    keep = max(0, height - 1)
    return (rows[-keep:] if keep else []) + [(state, STATE_COLORS.get(worker.state, INK), True)]


def draw_bubble(frame: Frame, col: int, row: int, width: int, height: int, worker: Worker, workers: list[Worker],
                color: tuple, selected: bool, tail_col: int) -> None:
    dark = tuple(int(c * 0.6) for c in color)
    left, right, low_l, low_r, bar, side = ("╔", "╗", "╚", "╝", "═", "║") if selected else ("╭", "╮", "╰", "╯", "─", "│")
    inner = width - 2
    title = clip(f" {worker.item_label} {clean(worker.title)} ", inner)
    frame.text(col, row, left + title + " " * (inner - width_of(title)) + right, (28, 24, 40), color, selected)
    rows = body_rows(worker, workers, inner - 2, height - 2)
    blank = height - 2 - len(rows)
    for i in range(height - 2):
        frame.text(col, row + 1 + i, side, dark, CREAM)
        frame.text(col + 1, row + 1 + i, " " * inner, INK, CREAM)
        frame.text(col + width - 1, row + 1 + i, side, dark, CREAM)
        if i >= blank:
            text, fg, bold = rows[i - blank]
            frame.text(col + 2, row + 1 + i, text, fg, CREAM, bold)
    frame.text(col, row + height - 1, low_l + bar * inner + low_r, dark, CREAM)
    if col < tail_col < col + width - 1:
        frame.text(tail_col, row + height - 1, "▼", dark, CREAM)
