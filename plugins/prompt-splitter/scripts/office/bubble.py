"""The container above each character: a filled title bar and the tail of the split's activity."""
import re
from functools import lru_cache

from .model import Worker
from .term import WHITE, Frame, char_width

CREAM = (255, 253, 245)
INK = (50, 44, 70)
TOOL = (112, 112, 134)
ROLES = {"voce": ("Você", (0, 128, 140)), "claude": ("Claude", (160, 60, 170))}
STATE_COLORS = {
    "working": (24, 136, 78), "thinking": (24, 136, 78), "waiting": (200, 110, 0), "ask": (190, 120, 0),
    "blocked": (190, 120, 0), "failed": (205, 50, 60), "done": (112, 112, 134),
}
STATE_TEXT = {
    "working": "Estou trabalhando", "thinking": "Estou trabalhando", "ask": "Preciso da sua resposta",
    "blocked": "Terminei, aguardo você", "failed": "Algo falhou aqui", "done": "Terminei",
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
    names = ", ".join(group[i].title if i in group else f"item {i}" for i in worker.after)
    return f"Estou aguardando {names}" if names else "Estou aguardando"


@lru_cache(maxsize=4096)
def _wrapped(text: str, width: int) -> tuple[str, ...]:
    """Cached wrap: the activity lines do not change between frames, so each one is wrapped once."""
    return tuple(wrap(text, width))


def chat_rows(worker: Worker, width: int) -> list[tuple[str, tuple, bool]]:
    """Every wrapped activity row of the worker, oldest first, without the state line."""
    rows: list[tuple[str, tuple, bool]] = []
    for line in worker.lines:
        if line.role == "tool":
            label = f"· {clean(line.text)}" + (f" (x{line.count})" if line.count > 1 else "")
            rows += [(row, TOOL, False) for row in _wrapped(label, width)]
        else:
            name, color = ROLES.get(line.role, (line.role, INK))
            rows.append((name, color, True))
            rows += [(row, INK, False) for row in _wrapped(line.text, width)]
    if worker.subagents > 0:
        count = worker.subagents
        rows.append((f"Tenho {count} subagent{'s' if count > 1 else ''} rodando", TOOL, False))
    return rows


def chat_geometry(worker: Worker, width: int, height: int) -> tuple[int, int]:
    """(total body rows, visible body rows) for a bubble of this box size; the state line takes one row."""
    return len(chat_rows(worker, width - 4)), max(0, height - 3)


def body_rows(worker: Worker, workers: list[Worker], width: int, height: int, note: str = "", offset: int = 0) -> list[tuple[str, tuple, bool]]:
    """The activity window, as (text, color, bold), with the state always on the last one.

    `offset` is how many rows back from the newest the window ends; 0 shows the tail."""
    rows = chat_rows(worker, width)
    keep = max(0, height - 1)
    offset = max(0, min(offset, max(0, len(rows) - keep)))
    end = len(rows) - offset
    scrolled = " (rolando: Baixo volta)" if offset > 0 else ""
    state = clip(state_text(worker, workers) + (f", {note}" if note else "") + scrolled, width)
    body = rows[max(0, end - keep):end] if keep else []
    return body + [(state, STATE_COLORS.get(worker.state, INK), True)]


def draw_bubble(frame: Frame, col: int, row: int, width: int, height: int, worker: Worker, workers: list[Worker],
                color: tuple, tail_col: int, note: str = "", offset: int = 0) -> None:
    dark = tuple(int(c * 0.6) for c in color)
    left, right, low_l, low_r, bar, side = "╭", "╮", "╰", "╯", "─", "│"
    inner = width - 2
    title = clip(f" {worker.item_label} {clean(worker.title)} ", inner)
    frame.text(col, row, left + title + " " * (inner - width_of(title)) + right, (28, 24, 40), color, False)
    rows = body_rows(worker, workers, inner - 2, height - 2, note, offset)
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


def draw_selection(frame: Frame, col: int, row: int, width: int, height: int, tail_col: int, color: tuple) -> None:
    """The white ring of the selected bubble: solid white end columns, bottom row and a half-block row above the title."""
    dark = tuple(int(c * 0.6) for c in color)
    if row > 0:
        for c in range(col, col + width):
            _, fg, bg, _ = frame.cells[row - 1][c]
            upper = fg if frame.cells[row - 1][c][0] == "▀" else bg
            frame.text(c, row - 1, "▄", WHITE, upper)
    for r in range(row, row + height):
        frame.text(col, r, " ", None, WHITE)
        frame.text(col + width - 1, r, " ", None, WHITE)
        if r > row:  # a dark line on the inner edge, so the white does not melt into the cream body.
            frame.text(col + 1, r, "▏", dark, CREAM)
            frame.text(col + width - 2, r, "▕", dark, CREAM)
    for c in range(col, col + width):
        frame.text(c, row + height - 1, "▔" if col < c < col + width - 1 else " ", dark, WHITE)
    if col < tail_col < col + width - 1:
        frame.text(tail_col, row + height - 1, "▼", dark, WHITE)
