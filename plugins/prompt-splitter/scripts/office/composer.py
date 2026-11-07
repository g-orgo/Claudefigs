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
WORD_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")
# Pixels cut from the first rows of each corner, per ring of the border.
RINGS = ((0, (3, 1, 1)), (1, (2, 1)), (2, (1,)), (3, (1,)))  # (inset, cuts) from the outside in.


class Composer:
    def __init__(self):
        self._text = ""
        self.focused = False
        self.hovered = False  # the pointer is over the box; hover never gives focus.
        self.images: dict[int, str] = {}  # placeholder number -> absolute image path, for this draft.
        self.spaced: set[int] = set()  # placeholders that got a separator space from attach(), removed with them.
        self.highlight = 0  # index of the highlighted suggestion.
        self._highlight_text = ""  # the draft the highlight belongs to; a new draft starts at the top.
        self.dismissed: str | None = None  # the draft whose popup Esc closed; it stays closed until the draft changes.
        self.cursor = 0  # text index of the caret, always between 0 and len(text).
        self.anchor: int | None = None  # where a selection started; None when nothing is selected.
        self.dragging = False  # a left button is held down over the text.
        self._lines: tuple[str, ...] | None = None  # wrapped lines of the last draw, for mouse mapping.
        self._starts: tuple[int, ...] = ()  # text index where each wrapped line starts.
        self._first = 0  # terminal row of the first text line.
        self._x = 0  # terminal column of the first text cell.
        self._window = 0  # index of the first wrapped line in the visible window.
        self._capacity = 1  # wrapped lines the box shows.

    @property
    def text(self) -> str:
        return self._text

    @text.setter
    def text(self, value: str) -> None:
        """A draft assigned from outside puts the caret at its end; the editing methods set it again."""
        self._text = value
        self.cursor = len(value)

    def focus(self) -> None:
        self.focused = True

    def blur(self) -> None:
        self.focused = False
        self.anchor = None
        self.dragging = False

    def selection(self) -> tuple[int, int] | None:
        """(start, end) of the selected text, or None when nothing is selected."""
        if self.anchor is None:
            return None
        start, end = sorted((self.anchor, self.cursor))
        return (start, end) if start != end else None

    def selected_text(self) -> str:
        """The selected draft text as shown, placeholders included; empty when nothing is selected."""
        span = self.selection()
        return self.text[span[0]:span[1]] if span else ""

    def _spans(self) -> list[tuple[int, int]]:
        """Text ranges of the placeholders, which the caret never enters."""
        return [(match.start(), match.end()) for match in PLACEHOLDER_RE.finditer(self.text)]

    def _snap(self, index: int, direction: int) -> int:
        """`index` clamped to the draft and pushed out of any placeholder toward `direction`."""
        index = max(0, min(index, len(self.text)))
        for start, end in self._spans():
            if start < index < end:
                return start if direction < 0 else end
        return index

    def _snap_nearest(self, index: int) -> int:
        """`index` clamped to the draft, moved to the nearer edge of a placeholder it lands inside."""
        index = max(0, min(index, len(self.text)))
        for start, end in self._spans():
            if start < index < end:
                return start if index - start <= end - index else end
        return index

    def _move_to(self, index: int, extend: bool, direction: int) -> None:
        """Puts the caret at a snapped index, starting or keeping a selection when `extend` is set."""
        if extend:
            if self.anchor is None:
                self.anchor = self.cursor
        else:
            self.anchor = None
        self.cursor = self._snap(index, direction)

    def move_left(self) -> None:
        span = self.selection()
        self._move_to(span[0] if span else self.cursor - 1, False, -1)

    def move_right(self) -> None:
        span = self.selection()
        self._move_to(span[1] if span else self.cursor + 1, False, 1)

    def shift_left(self) -> None:
        self._move_to(self.cursor - 1, True, -1)

    def shift_right(self) -> None:
        self._move_to(self.cursor + 1, True, 1)

    def move_home(self, extend: bool = False) -> None:
        self._move_to(0, extend, -1)

    def move_end(self, extend: bool = False) -> None:
        self._move_to(len(self.text), extend, 1)

    def _word_left(self) -> int:
        index = self.cursor
        while index > 0 and self.text[index - 1] not in WORD_CHARS:
            index -= 1
        while index > 0 and self.text[index - 1] in WORD_CHARS:
            index -= 1
        return index

    def _word_right(self) -> int:
        index = self.cursor
        while index < len(self.text) and self.text[index] not in WORD_CHARS:
            index += 1
        while index < len(self.text) and self.text[index] in WORD_CHARS:
            index += 1
        return index

    def move_word_left(self, extend: bool = False) -> None:
        self._move_to(self._word_left(), extend, -1)

    def move_word_right(self, extend: bool = False) -> None:
        self._move_to(self._word_right(), extend, 1)

    def insert(self, string: str) -> None:
        """Inserts text at the caret, replacing a selection; line breaks and tabs become one space."""
        self.dismissed = None
        out = []
        for ch in string:
            if ch in "\r\n\t":
                out.append(" ")
            elif ch.isprintable():
                out.append(ch)
        self._insert_text("".join(out))

    def _insert_text(self, payload: str) -> None:
        span = self.selection()
        start, end = span if span else (self.cursor, self.cursor)
        self.text = (self.text[:start] + payload + self.text[end:])[:MAX_TEXT]
        self.cursor = min(start + len(payload), len(self.text))
        self.anchor = None

    def paste(self, string: str) -> None:
        """A paste of image file paths attaches those images; any other paste is inserted as text."""
        paths = image_paths_from_paste(string)
        if paths is None:
            self.insert(string)
            return
        for path in paths:
            self.attach(path)

    def attach(self, path: str) -> bool:
        """Inserts an image placeholder at the caret; returns False when the draft has no room left for it."""
        self.dismissed = None
        token = f"[Imagem #{max(self.images, default=0) + 1}]"
        number = max(self.images, default=0) + 1
        span = self.selection()
        start, end = span if span else (self.cursor, self.cursor)
        before = self.text[:start]
        sep = " " if before and not before.endswith(" ") else ""
        if len(self.text) - (end - start) + len(sep) + len(token) > MAX_TEXT:
            return False
        self.text = self.text[:start] + sep + token + self.text[end:]
        self.cursor = start + len(sep) + len(token)
        self.anchor = None
        self.images[number] = os.path.abspath(path)
        if sep:
            self.spaced.add(number)
        return True

    def _drop_placeholder(self, start: int, end: int, number: int) -> None:
        """Removes a placeholder, its image and the separator space attach() gave it."""
        left = start - 1 if number in self.spaced and start > 0 else start
        del self.images[number]
        self.spaced.discard(number)
        self.text = self.text[:left] + self.text[end:]
        self.cursor = left
        self.anchor = None

    def backspace(self) -> None:
        """Deletes the selection, or the character or whole placeholder before the caret."""
        self.dismissed = None
        span = self.selection()
        if span is not None:
            self._insert_text("")
            return
        if self.cursor == 0:
            return
        for match in PLACEHOLDER_RE.finditer(self.text):
            number = int(match.group(1))
            if match.end() == self.cursor and number in self.images:
                self._drop_placeholder(match.start(), match.end(), number)
                return
        position = self.cursor - 1
        self.text = self.text[:position] + self.text[self.cursor:]
        self.cursor = position

    def delete(self) -> None:
        """Deletes the selection, or the character or whole placeholder after the caret."""
        self.dismissed = None
        span = self.selection()
        if span is not None:
            self._insert_text("")
            return
        for match in PLACEHOLDER_RE.finditer(self.text):
            number = int(match.group(1))
            if match.start() == self.cursor and number in self.images:
                self._drop_placeholder(match.start(), match.end(), number)
                return
        if self.cursor < len(self.text):
            position = self.cursor
            self.text = self.text[:position] + self.text[position + 1:]
            self.cursor = position

    def prompt_text(self) -> str:
        """The draft as sent to Claude: each placeholder becomes an `@<absolute path>` mention."""
        def mention(match: re.Match) -> str:
            path = self.images.get(int(match.group(1)))
            return f"@{path}" if path else match.group(0)
        return PLACEHOLDER_RE.sub(mention, self.text)

    def trigger(self) -> tuple[str, str, int] | None:
        """(kind, query, start) of the token before the caret: a slash command at the very start, or an @ token."""
        head = self.text[:self.cursor]
        if head.startswith("/") and " " not in head:
            return "command", head[1:], 0
        match = re.search(r"(?:^|\s)@(\S*)$", head)
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
        inserted = items[self.highlight][1]
        tail = self.text[self.cursor:]
        self.text = self.text[:trig[2]] + inserted + tail
        self.cursor = trig[2] + len(inserted)
        self.anchor = None
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
        self.cursor = len(self.text)
        self.anchor = None

    def clear(self) -> None:
        self.dismissed = None
        self.text = ""
        self.images = {}
        self.spaced = set()
        self.cursor = 0
        self.anchor = None
        self.dragging = False

    def index_at(self, col: int, row: int) -> int | None:
        """Draft index under a terminal cell of the last draw, or None before the first draw."""
        if self._lines is None:
            return None
        lines = self._lines
        line = self._window + max(0, row - self._first) // pixelfont.LINE_ROWS
        line = max(self._window, min(line, len(lines) - 1))
        line = min(line, self._window + self._capacity - 1)
        text = lines[line]
        font_x = (col - self._x) * pixelfont.CELL_X
        offset = 0
        pixels = 0
        if font_x > 0:
            for ch in text:
                width = pixelfont.glyph(ch)[0]
                if not width:
                    continue
                if font_x < pixels + width:
                    break
                pixels += width + 1
                offset += 1
        return self._snap_nearest(self._starts[line] + offset)

    def begin_drag(self, index: int) -> None:
        """A left press on the text: the caret goes to the clicked index and a drag starts there."""
        self.cursor = self._snap_nearest(index)
        self.anchor = self.cursor
        self.dragging = True

    def drag_to(self, index: int) -> None:
        """The pointer moved with the left button held: the selection follows it."""
        if not self.dragging:
            return
        self.cursor = self._snap_nearest(index)
        if self.anchor is None:
            self.anchor = self.cursor

    def end_drag(self) -> str:
        """The left button was released; returns the text the drag selected, or an empty string."""
        self.dragging = False
        return self.selected_text()


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


def _line_starts(lines: tuple[str, ...], text: str) -> list[int]:
    """Draft index where each wrapped line starts, walking the text in order."""
    starts = []
    position = 0
    for line in lines:
        found = text.find(line, position) if line else position
        if found < 0:
            found = position
        starts.append(found)
        position = found + len(line)
    return starts


def _cursor_line(cursor: int, starts: list[int], count: int) -> int:
    """Index of the wrapped line the caret belongs to; the last line starting at or before it."""
    line = 0
    for i, start in enumerate(starts):
        if start <= cursor:
            line = i
        else:
            break
    return max(0, min(line, count - 1))


def _select_background(frame: Frame, x: int, row: int, line: str, start: int, composer: "Composer") -> None:
    """Paints the gold background under the selected part of one wrapped line."""
    span = composer.selection() if composer.focused else None
    if not span:
        return
    low, high = span
    left, right = max(low, start), min(high, start + len(line))
    if left >= right:
        return
    x0 = pixelfont.text_width(line[:left - start])
    x1 = pixelfont.text_width(line[:right - start])
    for c in range(x + x0 // pixelfont.CELL_X, x + max(x1 - 1, x0) // pixelfont.CELL_X + 1):
        for r in range(row, row + pixelfont.CELL_Y):
            if 0 <= r < frame.nrows and 0 <= c < frame.cols:
                frame.cells[r][c] = (" ", None, GOLD_FOCUSED, False)


def _draw_line(frame: Frame, x: int, row: int, line: str, start: int, composer: "Composer") -> None:
    """Draws one wrapped line, with the selected part in ink over the gold background."""
    span = composer.selection() if composer.focused else None
    low, high = span if span else (0, 0)
    pixels = 0
    run = ""
    painted = None
    for i, ch in enumerate(line):
        selected = span is not None and low <= start + i < high
        if painted is not None and selected != painted:
            pixels = pixelfont.draw_text(frame, x, row, run, INK_BROWN, GOLD_FOCUSED if painted else PARCHMENT, pixels)
            run = ""
        painted = selected
        run += ch
    if run:
        pixelfont.draw_text(frame, x, row, run, INK_BROWN, GOLD_FOCUSED if painted else PARCHMENT, pixels)


def draw_composer(frame: Frame, top: int, col: int, width: int, rows: int, composer: "Composer", destination: str, hints: tuple[str, ...], tick: int) -> None:
    """Draws the box in the `rows` rows from (`col`, `top`), over whatever the view drew there."""
    composer._lines = None
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
    wrap_width = inner * pixelfont.CELL_X - pixelfont.text_width(CARET) - 1
    lines = pixelfont.wrap(composer.text, wrap_width) if composer.text else ("",)
    starts = _line_starts(lines, composer.text)
    cursor_line = _cursor_line(composer.cursor, starts, len(lines))
    window = max(0, cursor_line - capacity + 1)
    window = min(window, max(0, len(lines) - capacity))
    composer._lines, composer._starts = lines, tuple(starts)
    composer._first, composer._x = first, x
    composer._window, composer._capacity = window, capacity
    for i in range(window, min(window + capacity, len(lines))):
        row = first + (i - window) * pixelfont.LINE_ROWS
        _select_background(frame, x, row, lines[i], starts[i], composer)
    if composer.focused and (tick // 4) % 2 == 0:
        # The caret goes under the glyphs so a descender beside it is never erased.
        line = lines[cursor_line]
        offset = max(0, min(composer.cursor - starts[cursor_line], len(line)))
        prefix = line[:offset]
        caret_x = pixelfont.text_width(prefix) + 1 if prefix else 0
        pixelfont.draw_text(frame, x, first + (cursor_line - window) * pixelfont.LINE_ROWS, CARET, INK_BROWN, PARCHMENT, caret_x)
    for i in range(window, min(window + capacity, len(lines))):
        _draw_line(frame, x, first + (i - window) * pixelfont.LINE_ROWS, lines[i], starts[i], composer)
    if not composer.text and not composer.focused:
        pixelfont.draw_text(frame, x, first, pixelfont.clip(PLACEHOLDER_IDLE, inner * pixelfont.CELL_X), FADED, PARCHMENT)

