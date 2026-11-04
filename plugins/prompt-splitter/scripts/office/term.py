"""Terminal output of the office viewer: cell frames, minimal ANSI diffs and the raw screen."""
import sys
import termios
import tty
import unicodedata

from .sprites import Canvas, Color

MOUSE_ON = "\x1b[?1000h\x1b[?1003h\x1b[?1006h"  # button and motion reports, in SGR coordinates
MOUSE_OFF = "\x1b[?1006l\x1b[?1003l\x1b[?1000l"

Cell = tuple[str, Color | None, Color | None, bool]
BLANK: Cell = (" ", None, None, False)
WHITE = (255, 255, 255)  # the selection ring of doors, bubbles and the composer.


def char_width(ch: str) -> int:
    """Terminal cells used by one character: 0 for combining marks, 2 for wide East Asian ones, else 1."""
    if unicodedata.combining(ch):
        return 0
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


class Frame:
    """A grid of cells; each cell is (char, fg, bg, bold). A wide character is followed by a cell holding ""."""

    def __init__(self, cols: int, rows: int):
        self.cols = cols
        self.nrows = rows
        self.cells: list[list[Cell]] = [[BLANK] * cols for _ in range(rows)]

    @classmethod
    def from_canvas(cls, canvas: Canvas, cols: int, rows: int) -> "Frame":
        """Each cell packs two vertical pixels: '▀' with fg=top and bg=bottom, or a space with bg when equal."""
        frame = cls(cols, rows)
        for r in range(rows):
            top_y, bottom_y = 2 * r, 2 * r + 1
            if top_y >= canvas.height:
                break
            top_row = canvas.rows[top_y]
            bottom_row = canvas.rows[bottom_y] if bottom_y < canvas.height else None
            line = frame.cells[r]
            for c in range(min(cols, canvas.width)):
                top = top_row[c]
                bottom = bottom_row[c] if bottom_row is not None else None
                if bottom is None or top == bottom:
                    line[c] = (" ", None, top, False)
                else:
                    line[c] = ("▀", top, bottom, False)
        return frame

    def text(self, col: int, row: int, string: str, fg: Color | None, bg: Color | None, bold: bool = False) -> None:
        """Writes a string at (col, row), honouring wide characters; anything outside the grid is clipped."""
        if not 0 <= row < self.nrows:
            return
        line = self.cells[row]
        for ch in string:
            width = char_width(ch)
            if width == 0:
                continue
            if col < 0:
                col += width
                continue
            if col + width > self.cols:
                break
            if line[col][0] == "" and col > 0:
                line[col - 1] = (" ", fg, bg, False)  # overwriting a wide character's second half
            line[col] = (ch, fg, bg, bold)
            if width == 2:
                line[col + 1] = ("", fg, bg, bold)
            col += width


def _sgr(fg: Color | None, bg: Color | None, bold: bool) -> str:
    params = ["0"]
    if bold:
        params.append("1")
    params.append("39" if fg is None else "38;2;{};{};{}".format(*fg))
    params.append("49" if bg is None else "48;2;{};{};{}".format(*bg))
    return "\x1b[" + ";".join(params) + "m"


def diff(prev: Frame | None, frame: Frame) -> tuple[str, int]:
    """ANSI sequence that turns prev into frame, and the number of changed cells.

    Unchanged frames give ("", 0). A missing or differently sized prev redraws everything.
    Cursor moves are skipped when the cursor is already in place, SGR is only emitted when the style changes.
    """
    full = prev is None or prev.cols != frame.cols or prev.nrows != frame.nrows
    out: list[str] = []
    changed = 0
    style: tuple | None = None
    pos: tuple[int, int] | None = None
    for r, line in enumerate(frame.cells):
        old_line = None if full else prev.cells[r]
        for c, cell in enumerate(line):
            if not full and old_line[c] == cell:
                continue
            char, fg, bg, bold = cell
            if char == "":  # second half of a wide character, written with its first half
                continue
            if pos != (r, c):
                out.append(f"\x1b[{r + 1};{c + 1}H")
            key = (fg, bg, bold)
            if key != style:
                out.append(_sgr(fg, bg, bold))
                style = key
            out.append(char)
            changed += 1
            pos = (r, c + char_width(char))
    if changed == 0:
        return "", 0
    return "\x1b[?2026h" + "".join(out) + "\x1b[?2026l", changed


class Screen:
    """Owns the terminal: alternate screen, hidden cursor, no echo, mouse reports and incremental frames."""

    def __init__(self, stream=None):
        self.stream = stream or sys.stdout
        self.prev: Frame | None = None
        self._fd: int | None = None
        self._saved = None

    def enter(self) -> None:
        self._fd = sys.stdin.fileno()
        self._saved = termios.tcgetattr(self._fd)
        tty.setcbreak(self._fd)
        attrs = termios.tcgetattr(self._fd)
        attrs[3] &= ~termios.ECHO
        termios.tcsetattr(self._fd, termios.TCSADRAIN, attrs)
        self._write("\x1b[?1049h\x1b[?25l\x1b[2J" + MOUSE_ON)
        self.prev = None

    def exit(self) -> None:
        """Restores the terminal; TCSAFLUSH drops mouse reports still queued, so they never reach the shell."""
        try:
            self._write(MOUSE_OFF + "\x1b[0m\x1b[?25h\x1b[?1049l")
        finally:
            if self._saved is not None:
                termios.tcsetattr(self._fd, termios.TCSAFLUSH, self._saved)
                self._saved = None

    def present(self, frame: Frame) -> None:
        text, _ = diff(self.prev, frame)
        self.prev = frame
        if text:
            self._write(text)

    def _write(self, text: str) -> None:
        self.stream.write(text)
        self.stream.flush()
