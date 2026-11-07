"""The writing field of the office: a text draft, and the chunky pixel-art dialog box that draws it."""
import os
import re
from functools import lru_cache

from . import pixelfont
from .clipboard import image_paths_from_paste
from . import suggest
from .suggest import matches
from .sprites import Canvas
from .term import Frame

PANEL_ROWS, PANEL_ROWS_SHORT = 14, 11  # two lines of text, or one when the terminal is short.
SHORT_BELOW = 46  # terminals with fewer rows get the one-line box.
MIN_ROWS = 28  # below this the view itself asks for a bigger terminal, so there is no field.
MAX_TEXT = 4000
MAX_WIDTH = 96
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
# Vertical layout in half-cell pixels: the plate's top edge, then its text rows, then the box's top border.
PLATE_ROWS = 4  # one row of edge and three of text; the box's outline closes the plate from below.
PLATE_PAD = 1  # cells of wood each side of the plate text.
PLATE_GAP = 2
DESTINATION_MIN = 30  # the key hints give way before the destination shrinks below this many cells.
BORDER_PX = 3
TEXT_TOP_ROWS = 2  # rows from the box's top edge to the first line of text.
PAD_CELLS = 6  # cells from the box's left edge to the text.
CARET = "_"
POPUP_ROWS = 5  # most suggestions shown above the box.
PLACEHOLDER_RE = re.compile(r"\[Imagem #(\d+)\]")
PLACEHOLDER_TAIL_RE = re.compile(r"\[Imagem #(\d+)\]$")
# Pixels cut from the first rows of each corner, per ring of the border.
RINGS = ((0, (3, 1, 1)), (1, (2, 1)), (2, (1,)), (3, (1,)))  # (inset, cuts) from the outside in.


class Composer:
    def __init__(self):
        self.text = ""
        self.focused = False
        self.hovered = False  # the pointer is over the box; hover never gives focus.
        self.images: dict[int, str] = {}  # placeholder number -> absolute image path, for this draft.
        self.spaced: set[int] = set()  # placeholders that got a separator space from attach(), removed with them.
        self.highlight = 0  # index of the highlighted suggestion.
        self._highlight_text = ""  # the draft the highlight belongs to; a new draft starts at the top.
        self.dismissed: str | None = None  # the draft whose popup Esc closed; it stays closed until the draft changes.

    def focus(self) -> None:
        self.focused = True

    def blur(self) -> None:
        self.focused = False

    def insert(self, string: str) -> None:
        """Adds text at the end; line breaks and tabs become one space and other control characters are dropped."""
        self.dismissed = None
        out = []
        for ch in string:
            if ch in "\r\n\t":
                out.append(" ")
            elif ch.isprintable():
                out.append(ch)
        self.text = (self.text + "".join(out))[:MAX_TEXT]

    def paste(self, string: str) -> None:
        """A paste of image file paths attaches those images; any other paste is inserted as text."""
        paths = image_paths_from_paste(string)
        if paths is None:
            self.insert(string)
            return
        for path in paths:
            self.attach(path)

    def attach(self, path: str) -> bool:
        """Adds an image placeholder at the end; returns False when the draft has no room left for it."""
        self.dismissed = None
        token = f"[Imagem #{max(self.images, default=0) + 1}]"
        number = max(self.images, default=0) + 1
        sep = " " if self.text and not self.text.endswith(" ") else ""
        if len(self.text) + len(sep) + len(token) > MAX_TEXT:
            return False
        self.text += sep + token
        self.images[number] = os.path.abspath(path)
        if sep:
            self.spaced.add(number)
        return True

    def backspace(self) -> None:
        """Removes the last character, or the whole placeholder and its image when the text ends with one."""
        self.dismissed = None
        tail = PLACEHOLDER_TAIL_RE.search(self.text)
        if tail and int(tail.group(1)) in self.images:
            number = int(tail.group(1))
            start = tail.start() - 1 if number in self.spaced and tail.start() > 0 else tail.start()
            del self.images[number]
            self.spaced.discard(number)
            self.text = self.text[:start]
            return
        self.text = self.text[:-1]

    def prompt_text(self) -> str:
        """The draft as sent to Claude: each placeholder becomes an `@<absolute path>` mention."""
        def mention(match: re.Match) -> str:
            path = self.images.get(int(match.group(1)))
            return f"@{path}" if path else match.group(0)
        return PLACEHOLDER_RE.sub(mention, self.text)

    def trigger(self) -> tuple[str, str, int] | None:
        """(kind, query, start) of the token being typed: a slash command at the very start, or an @ token at the end."""
        if self.text.startswith("/") and " " not in self.text:
            return "command", self.text[1:], 0
        match = re.search(r"(?:^|\s)@(\S*)$", self.text)
        if match:
            return "file", match.group(1), match.start(1) - 1
        return None

    def suggestions(self, cwd: str) -> list[tuple[str, str, str]]:
        """Up to POPUP_ROWS items as (label, text to insert, description); empty when no token is open or Esc closed it."""
        trig = self.trigger()
        if trig is None or self.dismissed == self.text:
            return []
        if self._highlight_text != self.text:  # a new query starts at the top of the list.
            self.highlight, self._highlight_text = 0, self.text
        kind, query, _ = trig
        if kind == "command":
            return [(f"/{name}", f"/{name} ", desc) for name, desc in matches(suggest.commands(cwd), query, POPUP_ROWS)]
        return [(rel, f"@{rel} ", "") for rel in suggest.files(cwd, query, POPUP_ROWS)]

    def move(self, delta: int, cwd: str) -> None:
        count = len(self.suggestions(cwd))
        if count:
            self.highlight = (self.highlight + delta) % count

    def accept(self, cwd: str, index: int | None = None) -> bool:
        """Replaces the open token with the suggestion (the highlighted one, or `index`); False when nothing is open."""
        items = self.suggestions(cwd)
        if not items:
            return False
        if index is not None and 0 <= index < len(items):
            self.highlight = index
        trig = self.trigger()
        self.text = self.text[:trig[2]] + items[self.highlight][1]
        self.dismissed = None
        return True

    def dismiss(self, cwd: str) -> bool:
        """Esc closes the popup and keeps the draft; False when no popup was open."""
        if not self.suggestions(cwd):
            return False
        self.dismissed = self.text
        return True

    def state(self) -> tuple[str, dict[int, str], set[int]]:
        return self.text, dict(self.images), set(self.spaced)

    def restore(self, state: tuple[str, dict[int, str], set[int]]) -> None:
        self.text, self.images, self.spaced = state[0], dict(state[1]), set(state[2])

    def clear(self) -> None:
        self.dismissed = None
        self.text = ""
        self.images = {}
        self.spaced = set()


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
def _box(width: int, rows: int, focused: bool, lit: bool) -> Canvas:
    """The empty box; `None` pixels keep whatever the view has behind them, so the corners stay round.
    `lit` (focused or hovered) turns the two outer rings white."""
    canvas = Canvas(width, rows * 2, None)
    top = PLATE_ROWS * 2
    height = rows * 2 - top
    outer = WHITE if lit else OUTLINE
    colors = (outer, WHITE if lit else (WOOD_FOCUSED if focused else WOOD), GOLD_FOCUSED if focused else GOLD, PARCHMENT)
    for (inset, cuts), color in zip(RINGS, colors):
        _rounded(canvas, inset, top + inset, width - 2 * inset, height - 2 * inset, color, cuts)
    for x in range(BORDER_PX + 1, width - BORDER_PX - 1):
        canvas.put(x, top + BORDER_PX, PARCHMENT_SHADE)
    return canvas


def _plate_width(text: str) -> int:
    return (pixelfont.text_width(text) + 1) // pixelfont.CELL_X + 2 * PLATE_PAD + 2


def _plate(canvas: Canvas, x: int, width: int, focused: bool) -> None:
    """A wooden name plate resting on the top edge of the box."""
    fill = WOOD_FOCUSED if focused else WOOD
    height = PLATE_ROWS * 2 + 1
    _rounded(canvas, x, 0, width, height, OUTLINE, (1,))
    _rounded(canvas, x + 1, 1, width - 2, height - 1, fill, ())


POPUP_RINGS = ((0, (2, 1)), (1, (1,)), (2, ()))  # (inset, cuts) of outline, wood and parchment, outside in.


def draw_popup(frame: Frame, col: int, top: int, width: int, items: list[tuple[str, str, str]], highlight: int) -> None:
    """Suggestion list framed like the box: outline, wood and parchment, with a border row above and below the items.
    The first item sits one row under `top`, which is the top border row."""
    if not items or width < 2 * PAD_CELLS:
        return
    canvas = Canvas(width, (len(items) + 2) * 2, None)
    for (inset, cuts), color in zip(POPUP_RINGS, (OUTLINE, WOOD, PARCHMENT)):
        _rounded(canvas, inset, inset, width - 2 * inset, canvas.height - 2 * inset, color, cuts)
    overlay(frame, canvas, col, top)
    for i, (label, _insert, desc) in enumerate(items):
        row = top + 1 + i
        if not 0 <= row < frame.nrows:
            continue
        selected = i == highlight
        bg = GOLD_FOCUSED if selected else PARCHMENT
        cells = frame.cells[row]
        for x in range(col + 2, min(col + width - 2, frame.cols)):
            cells[x] = (" ", None, bg, False)
        room = width - 2 * PAD_CELLS
        if len(label) > room:  # file paths lose their start, so the name at the end stays readable.
            label = "..." + label[-(room - 3):]
        for k, ch in enumerate(label[:room]):
            if col + PAD_CELLS + k < frame.cols:
                cells[col + PAD_CELLS + k] = (ch, INK_BROWN, bg, selected)
        start = PAD_CELLS + len(label) + 2
        for k, ch in enumerate(desc[: max(0, width - start - PAD_CELLS)]):
            if col + start + k < frame.cols:
                cells[col + start + k] = (ch, INK_BROWN if selected else FADED, bg, False)


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


BACK_W = 16  # cols of the back button.
BACK_H = 8  # rows of the back button: 16 half-cell pixels tall.
WHITE = (255, 255, 255)
ARROW = (  # 8x8 left arrow in INK_BROWN, drawn at the center of the button.
    "...#....",
    "..##....",
    ".###....",
    "########",
    "########",
    ".###....",
    "..##....",
    "...#....",
)


@lru_cache(maxsize=2)
def _back_canvas(selected: bool) -> Canvas:
    """The back button: the box's rounded rings and colors, with the outer two rings white when selected."""
    canvas = Canvas(BACK_W, BACK_H * 2, None)
    height = BACK_H * 2
    outer = WHITE if selected else OUTLINE
    colors = (outer, WHITE if selected else WOOD, GOLD, PARCHMENT)
    for (inset, cuts), color in zip(RINGS, colors):
        _rounded(canvas, inset, inset, BACK_W - 2 * inset, height - 2 * inset, color, cuts)
    for y, line in enumerate(ARROW):
        for x, ch in enumerate(line):
            if ch == "#":
                canvas.put(4 + x, 4 + y, INK_BROWN)
    return canvas


def draw_back_button(frame: Frame, col: int, top: int, selected: bool) -> None:
    """Draws the round back button with its top-left cell at (col, top)."""
    overlay(frame, _back_canvas(selected), col, top)


def draw_composer(frame: Frame, top: int, col: int, width: int, rows: int, composer: "Composer", destination: str, hints: tuple[str, ...], tick: int) -> None:
    """Draws the box in the `rows` rows from (`col`, `top`), over whatever the view drew there."""
    if width < 24:
        return
    canvas = _box(width, rows, composer.focused, composer.focused or composer.hovered).copy()
    inner = width - 2 * PAD_CELLS
    span = width - 2 * (BORDER_PX + 1)
    wanted = min(_plate_width(destination), DESTINATION_MIN)
    hint = next((h for h in hints if _plate_width(h) + PLATE_GAP + wanted <= span), "")
    hint_w = _plate_width(hint) if hint else 0
    room = span - (hint_w + PLATE_GAP if hint else 0) - 2 * PLATE_PAD - 2
    plate = pixelfont.clip(destination, room * pixelfont.CELL_X)
    plate_x, hint_x = BORDER_PX + 1, width - BORDER_PX - 1 - hint_w
    fill = WOOD_FOCUSED if composer.focused else WOOD
    if plate:
        _plate(canvas, plate_x, _plate_width(plate), composer.focused)
    if hint:
        _plate(canvas, hint_x, hint_w, composer.focused)
    overlay(frame, canvas, col, top)

    if plate:
        pixelfont.draw_text(frame, col + plate_x + 1 + PLATE_PAD, top + 1, plate, PLATE_TEXT, fill)
    if hint:
        pixelfont.draw_text(frame, col + hint_x + 1 + PLATE_PAD, top + 1, hint, PLATE_TEXT, fill)

    capacity = 2 if rows == PANEL_ROWS else 1
    first = top + PLATE_ROWS + TEXT_TOP_ROWS
    x = col + PAD_CELLS
    if composer.text:
        lines = pixelfont.wrap(composer.text, inner * pixelfont.CELL_X - pixelfont.text_width(CARET) - 1)[-capacity:]
        for i, line in enumerate(lines):
            pixelfont.draw_text(frame, x, first + i * pixelfont.LINE_ROWS, line, INK_BROWN, PARCHMENT)
    else:
        lines = ("",)
        if not composer.focused:
            pixelfont.draw_text(frame, x, first, pixelfont.clip(PLACEHOLDER_IDLE, inner * pixelfont.CELL_X), FADED, PARCHMENT)
    if composer.focused and (tick // 4) % 2 == 0:
        pixelfont.draw_text(frame, x, first + (len(lines) - 1) * pixelfont.LINE_ROWS, lines[-1] + CARET, INK_BROWN, PARCHMENT)

