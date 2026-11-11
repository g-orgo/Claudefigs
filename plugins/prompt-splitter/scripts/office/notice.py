"""Pixel-art pop-up of the viewer: usage-limit stops and resume batches, drawn in the composer's box style."""
from collections import Counter
from datetime import datetime
from typing import NamedTuple

from . import pixelfont
from .composer import BORDER_PX, INK_BROWN, PAD_CELLS, PARCHMENT, PLATE_PAD, PLATE_ROWS, PLATE_TEXT, TEXT_TOP_ROWS, WOOD, _box, _plate, _plate_width, overlay
from .term import Frame

SHOW_TICKS = 80  # about 10 s at the viewer's 1/8 s frame.
MIN_COLS = 40  # narrower viewers hide the pop-up.
MIN_ROWS = 16  # shorter viewers hide the pop-up.
MAX_WIDTH = 64  # widest box, in cells.
MARGIN_COLS = 2  # cells between the box and the right edge.
MARGIN_ROWS = 1  # rows between the box and the top edge.
LIMIT_PLATE = "Limite de uso"
RESUME_PLATE = "Limite liberado"
LIMIT_LABELS = {"5-hour": "limite de 5 horas", "session": "limite da sessão", "weekly": "limite semanal"}
RESET_KNOWN = "Libera às {when}. Continuo sozinho quando você voltar."
RESET_UNKNOWN = "Libera em breve. Continuo sozinho quando você voltar."


class Placed(NamedTuple):
    col: int
    top: int
    width: int
    rows: int
    text: tuple[str, ...]  # wrapped lines, already clipped to the viewer's height.


def limit_content(workers) -> tuple[str, tuple[str, ...]]:
    """Plate and lines for the sessions stopped by a usage limit; the most common kind names the limit."""
    count = len(workers)
    kind = Counter(w.limit for w in workers).most_common(1)[0][0]
    label = LIMIT_LABELS.get(kind, "limite de uso")
    if count == 1:
        first = f"1 sessão parou no {label}"
    else:
        first = f"{count} sessões pararam no {label}"
    resets = [w.limit_reset_ms for w in workers if w.limit_reset_ms > 0]
    if resets:
        when = datetime.fromtimestamp(max(resets) / 1000).strftime("%H:%M")
        second = RESET_KNOWN.format(when=when)
    else:
        second = RESET_UNKNOWN
    return LIMIT_PLATE, (first, second)


def resume_content(sent: int, failed: int) -> tuple[str, tuple[str, ...]] | None:
    """Plate and lines after a resume batch; None when nothing was sent and nothing failed."""
    lines = []
    if sent:
        lines.append("Continuando 1 sessão" if sent == 1 else f"Continuando {sent} sessões")
    if failed:
        lines.append("1 não pôde continuar" if failed == 1 else f"{failed} não puderam continuar")
    if not lines:
        return None
    return RESUME_PLATE, tuple(lines)


def place(cols: int, rows: int, lines: tuple[str, ...]) -> Placed | None:
    """Where the pop-up goes in a viewer of cols x rows: top-right, or None when the viewer is too small."""
    if cols < MIN_COLS or rows < MIN_ROWS or not lines:
        return None
    width = min(MAX_WIDTH, cols - 2 * MARGIN_COLS)
    wrap_px = (width - 2 * PAD_CELLS) * pixelfont.CELL_X
    text: list[str] = []
    for line in lines:
        text.extend(pixelfont.wrap(line, wrap_px))
    room = rows - 2 * MARGIN_ROWS - PLATE_ROWS - TEXT_TOP_ROWS - 1
    text = text[:max(1, room // pixelfont.LINE_ROWS)]
    box_rows = PLATE_ROWS + TEXT_TOP_ROWS + len(text) * pixelfont.LINE_ROWS + 1
    return Placed(cols - MARGIN_COLS - width, MARGIN_ROWS, width, box_rows, tuple(text))


def draw(frame: Frame, placed: Placed, plate: str) -> None:
    """Draws the box, its wooden plate and the text lines over the frame."""
    canvas = _box(placed.width, placed.rows, False, False).copy()
    plate_x = BORDER_PX + 1
    _plate(canvas, plate_x, _plate_width(plate), False)
    overlay(frame, canvas, placed.col, placed.top)
    pixelfont.draw_text(frame, placed.col + plate_x + 1 + PLATE_PAD, placed.top + 1, plate, PLATE_TEXT, WOOD)
    first = placed.top + PLATE_ROWS + TEXT_TOP_ROWS
    for i, line in enumerate(placed.text):
        pixelfont.draw_text(frame, placed.col + PAD_CELLS, first + i * pixelfont.LINE_ROWS, line, INK_BROWN, PARCHMENT)


class Notice:
    """The pop-up's state: what it says and until which tick it stays up."""

    def __init__(self) -> None:
        self.plate = ""
        self.lines: tuple[str, ...] = ()
        self.until = -1

    def show(self, plate: str, lines: tuple[str, ...], tick: int) -> None:
        self.plate, self.lines, self.until = plate, tuple(lines), tick + SHOW_TICKS

    def visible(self, tick: int) -> bool:
        return bool(self.lines) and tick < self.until

    def close(self) -> None:
        self.until = -1
