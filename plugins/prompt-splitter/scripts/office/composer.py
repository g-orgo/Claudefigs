"""The writing field of the office: a text draft, and the chunky pixel-art dialog box that draws it."""
from functools import lru_cache

from . import pixelfont
from .sprites import Canvas
from .term import Frame

PANEL_ROWS, PANEL_ROWS_SHORT = 18, 14  # two lines of text, or one when the terminal is short.
SHORT_BELOW = 46  # terminals with fewer rows get the one-line box.
MIN_ROWS = 28  # below this the view itself asks for a bigger terminal, so there is no field.
MAX_TEXT = 4000
MAX_WIDTH = 120
BACKDROP = (38, 34, 54)
OUTLINE = (58, 36, 40)
WOOD = (166, 98, 52)
WOOD_FOCUSED = (214, 122, 48)
GOLD = (240, 190, 104)
GOLD_FOCUSED = (255, 224, 128)
PARCHMENT = (255, 238, 196)
PARCHMENT_SHADE = (240, 212, 160)
INK_BROWN = (74, 40, 32)
FADED = (158, 118, 86)
PLATE_TEXT = (255, 243, 214)
PLACEHOLDER_IDLE = "Aperte Tab para escrever..."
PLATE_PX, PLATE_OVERLAP, PLATE_GAP = 10, 3, 3
DESTINATION_MIN_PX = 60  # the key hints give way before the destination shrinks below this.
BORDER_PX, PAD_X = 4, 3
CARET_PX = 3
# Pixels cut from the first rows of each corner, per ring of the border.
CUTS = ((4, 2, 1, 1), (3, 1, 1), (2, 1), (1,))
RINGS = ((0, 0), (1, 1), (3, 2), (4, 3))  # (inset, index into CUTS) from the outside in.


class Composer:
    def __init__(self):
        self.text = ""
        self.focused = False

    def focus(self) -> None:
        self.focused = True

    def blur(self) -> None:
        self.focused = False

    def insert(self, string: str) -> None:
        """Adds text at the end; line breaks and tabs become one space and other control characters are dropped."""
        out = []
        for ch in string:
            if ch in "\r\n\t":
                out.append(" ")
            elif ch.isprintable():
                out.append(ch)
        self.text = (self.text + "".join(out))[:MAX_TEXT]

    def backspace(self) -> None:
        self.text = self.text[:-1]

    def clear(self) -> None:
        self.text = ""


def field_geometry(cols: int, room: int | None = None) -> tuple[int, int]:
    """Width and first column of the field, centered; `room` narrows it to a free span of the view."""
    width = min(cols - 4 if room is None else room, MAX_WIDTH)
    return width, max(0, (cols - width) // 2)


def panel_rows(rows: int) -> int:
    return PANEL_ROWS if rows >= SHORT_BELOW else PANEL_ROWS_SHORT


def _rounded(canvas: Canvas, x: int, y: int, width: int, height: int, color, cuts: tuple[int, ...]) -> None:
    for dy in range(height):
        edge = min(dy, height - 1 - dy)
        cut = cuts[edge] if edge < len(cuts) else 0
        for dx in range(cut, width - cut):
            canvas.put(x + dx, y + dy, color)


@lru_cache(maxsize=8)
def _box(width: int, rows: int, focused: bool) -> Canvas:
    """The empty box; `None` pixels keep whatever the view has behind them, so the corners stay round."""
    canvas = Canvas(width, rows * 2, None)
    top = PLATE_PX - PLATE_OVERLAP
    height = rows * 2 - top
    colors = (OUTLINE, WOOD_FOCUSED if focused else WOOD, GOLD_FOCUSED if focused else GOLD, PARCHMENT)
    for (inset, cut), color in zip(RINGS, colors):
        _rounded(canvas, inset, top + inset, width - 2 * inset, height - 2 * inset, color, CUTS[cut])
    for x in range(BORDER_PX + 1, width - BORDER_PX - 1):
        canvas.put(x, top + BORDER_PX, PARCHMENT_SHADE)
    return canvas


def _plate(canvas: Canvas, x: int, text: str, focused: bool) -> None:
    """A wooden name plate resting on the top edge of the box."""
    width = pixelfont.text_width(text) + 6
    _rounded(canvas, x, 0, width, PLATE_PX, OUTLINE, (2, 1))
    _rounded(canvas, x + 1, 1, width - 2, PLATE_PX - 2, WOOD_FOCUSED if focused else WOOD, (1,))
    pixelfont.draw_text(canvas, x + 3, 3, text, PLATE_TEXT)


def overlay(frame: Frame, canvas: Canvas, col: int, top: int) -> None:
    """Writes the non-empty pixels over the frame, keeping both half-cell colors of what is already there."""
    for r in range(canvas.height // 2):
        row = top + r
        if not 0 <= row < frame.nrows:
            continue
        upper, lower = canvas.rows[2 * r], canvas.rows[2 * r + 1]
        line = frame.cells[row]
        for c in range(canvas.width):
            x = col + c
            if not 0 <= x < frame.cols or (upper[c] is None and lower[c] is None):
                continue
            ch, fg, bg, _ = line[x]
            a = upper[c] if upper[c] is not None else (fg if ch == "▀" else bg)
            b = lower[c] if lower[c] is not None else bg
            line[x] = (" ", None, a, False) if a == b else ("▀", a, b, False)


def draw_composer(frame: Frame, top: int, col: int, width: int, rows: int, composer: "Composer", destination: str, hints: tuple[str, ...], tick: int) -> None:
    """Draws the box in the `rows` rows from (`col`, `top`), over whatever the view drew there."""
    if width < 24:
        return
    canvas = _box(width, rows, composer.focused).copy()
    inner = width - 2 * (BORDER_PX + PAD_X)
    span = width - 2 * (BORDER_PX + 1)
    wanted = min(pixelfont.text_width(destination), DESTINATION_MIN_PX) + 6
    hint = next((h for h in hints if pixelfont.text_width(h) + 6 + PLATE_GAP + wanted <= span), "")
    hint_w = pixelfont.text_width(hint) + 6 if hint else 0
    plate = pixelfont.clip(destination, span - 6 - (hint_w + PLATE_GAP if hint else 0))
    if plate:
        _plate(canvas, BORDER_PX + 1, plate, composer.focused)
    if hint:
        _plate(canvas, width - BORDER_PX - 1 - hint_w, hint, composer.focused)

    box_top = PLATE_PX - PLATE_OVERLAP + BORDER_PX
    capacity = 2 if rows == PANEL_ROWS else 1
    free = rows * 2 - box_top - BORDER_PX
    first = box_top + (free - capacity * pixelfont.LINE_PX) // 2 + 2
    x = BORDER_PX + PAD_X
    if composer.text:
        lines = pixelfont.wrap(composer.text, inner - CARET_PX - 1)[-capacity:]
        for i, line in enumerate(lines):
            pixelfont.draw_text(canvas, x, first + i * pixelfont.LINE_PX, line, INK_BROWN)
    else:
        lines = ("",)
        if not composer.focused:
            pixelfont.draw_text(canvas, x, first, pixelfont.clip(PLACEHOLDER_IDLE, inner), FADED)
    if composer.focused and (tick // 4) % 2 == 0:
        end = x + pixelfont.text_width(lines[-1]) + (1 if lines[-1] else 0)
        pixelfont.draw_text(canvas, end, first + (len(lines) - 1) * pixelfont.LINE_PX, "_", INK_BROWN)
    overlay(frame, canvas, col, top)
