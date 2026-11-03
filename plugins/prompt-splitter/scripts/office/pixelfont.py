"""A small bitmap font drawn in canvas pixels: five rows tall, one descender row, pt-BR accents composed on top."""
import re
import unicodedata
from functools import lru_cache

from .sprites import Canvas, Color

LINE_PX = 8  # one accent row above capitals, five rows, one descender row and a gap.

# Rows from the cap line down, separated by "|"; a sixth row is the descender.
GLYPHS = {
    " ": "..|..|..|..|..",
    "a": "...|##.|..#|#.#|###", "b": "#..|#..|###|#.#|###", "c": "...|###|#..|#..|###", "d": "..#|..#|###|#.#|###",
    "e": "...|###|#.#|##.|###", "f": ".##|#..|###|#..|#..", "g": "...|###|#.#|###|..#|###", "h": "#..|#..|###|#.#|#.#",
    "i": "#|.|#|#|#", "j": ".#|..|.#|.#|.#|#.", "k": "#..|#.#|##.|#.#|#.#", "l": "#|#|#|#|#",
    "m": ".....|####.|#.#.#|#.#.#|#.#.#", "n": "...|##.|#.#|#.#|#.#", "o": "...|###|#.#|#.#|###",
    "p": "...|###|#.#|###|#..|#..", "q": "...|###|#.#|###|..#|..#", "r": "...|#.#|##.|#..|#..",
    "s": "...|.##|#..|..#|##.", "t": "#..|###|#..|#..|.##", "u": "...|#.#|#.#|#.#|###", "v": "...|#.#|#.#|#.#|.#.",
    "w": ".....|#...#|#.#.#|#.#.#|.#.#.", "x": "...|#.#|.#.|.#.|#.#", "y": "...|#.#|#.#|###|..#|###", "z": "...|###|..#|#..|###",
    "A": ".#.|#.#|###|#.#|#.#", "B": "##.|#.#|##.|#.#|##.", "C": ".##|#..|#..|#..|.##", "D": "##.|#.#|#.#|#.#|##.",
    "E": "###|#..|##.|#..|###", "F": "###|#..|##.|#..|#..", "G": ".##|#..|#.#|#.#|.##", "H": "#.#|#.#|###|#.#|#.#",
    "I": "###|.#.|.#.|.#.|###", "J": "..#|..#|..#|#.#|.#.", "K": "#.#|#.#|##.|#.#|#.#", "L": "#..|#..|#..|#..|###",
    "M": "#...#|##.##|#.#.#|#...#|#...#", "N": "#..#|##.#|#.##|#..#|#..#", "O": ".#.|#.#|#.#|#.#|.#.",
    "P": "##.|#.#|##.|#..|#..", "Q": ".#.|#.#|#.#|##.|.##", "R": "##.|#.#|##.|#.#|#.#", "S": ".##|#..|.#.|..#|##.",
    "T": "###|.#.|.#.|.#.|.#.", "U": "#.#|#.#|#.#|#.#|###", "V": "#.#|#.#|#.#|#.#|.#.",
    "W": "#...#|#...#|#.#.#|##.##|#...#", "X": "#.#|#.#|.#.|#.#|#.#", "Y": "#.#|#.#|.#.|.#.|.#.", "Z": "###|..#|.#.|#..|###",
    "0": "###|#.#|#.#|#.#|###", "1": ".#.|##.|.#.|.#.|###", "2": "##.|..#|.#.|#..|###", "3": "##.|..#|.#.|..#|##.",
    "4": "#.#|#.#|###|..#|..#", "5": "###|#..|##.|..#|##.", "6": ".##|#..|###|#.#|###", "7": "###|..#|.#.|.#.|.#.",
    "8": "###|#.#|###|#.#|###", "9": "###|#.#|###|..#|##.",
    ".": ".|.|.|.|#", ",": ".|.|.|.|#|#", ":": ".|#|.|#|.", ";": ".|#|.|#|#", "!": "#|#|#|.|#", "?": "##.|..#|.#.|...|.#.",
    "-": "...|...|###|...|...", "_": "...|...|...|...|...|###", "+": "...|.#.|###|.#.|...", "=": "...|###|...|###|...",
    "/": "..#|..#|.#.|#..|#..", "\\": "#..|#..|.#.|..#|..#", "|": "#|#|#|#|#", "(": ".#|#.|#.|#.|.#", ")": "#.|.#|.#|.#|#.",
    "[": "##|#.|#.|#.|##", "]": "##|.#|.#|.#|##", "{": ".##|.#.|##.|.#.|.##", "}": "##.|.#.|.##|.#.|##.",
    "<": "..#|.#.|#..|.#.|..#", ">": "#..|.#.|..#|.#.|#..", "'": "#|#|.|.|.", '"': "#.#|#.#|...|...|...", "`": "#.|.#|..|..|..",
    "*": "#.#|.#.|#.#|...|...", "#": "#.#|###|#.#|###|#.#", "%": "#.#|..#|.#.|#..|#.#", "&": ".#.|#.#|.#.|#.#|.##",
    "@": "###|#.#|#.#|#..|###", "$": ".##|##.|.#.|.##|##.", "^": ".#.|#.#|...|...|...", "~": "...|.##|##.|...|...",
    "…": ".....|.....|.....|.....|#.#.#",
}
UNKNOWN = "###|#.#|#.#|#.#|###"
ACCENTS = {"́": "..#", "̀": "#..", "̂": "#.#", "̃": "###", "̈": "#.#"}
CEDILLA = "̧"


def _pixels(pattern: str, top: int = 0) -> list[tuple[int, int]]:
    return [(x, top + y) for y, row in enumerate(pattern.split("|")) for x, ch in enumerate(row) if ch == "#"]


@lru_cache(maxsize=512)
def glyph(ch: str) -> tuple[int, tuple[tuple[int, int], ...]]:
    """Width in pixels and the lit pixels of one character; anything outside the font is an empty box."""
    if unicodedata.combining(ch):
        return 0, ()
    parts = unicodedata.normalize("NFD", ch)
    pattern = GLYPHS.get(parts[0], UNKNOWN)
    width = len(pattern.split("|")[0])
    pixels = _pixels(pattern)
    for mark in parts[1:]:
        if mark == CEDILLA:
            pixels.append((width // 2, 5))
        elif mark in ACCENTS:
            if width < 3:  # the mark takes the place of the dot of i and j.
                pixels = [p for p in pixels if p[1] != 0] + [(width // 2, 0)]
            else:  # one row above the cap line, so a free row keeps it apart from a lowercase letter.
                pixels += [(x + (width - 3) // 2, y) for x, y in _pixels(ACCENTS[mark], -1)]
    return width, tuple(pixels)


def text_width(text: str) -> int:
    return max(0, sum(glyph(ch)[0] + 1 for ch in text if glyph(ch)[0]) - 1)


def draw_text(canvas: Canvas, x: int, y: int, text: str, color: Color) -> int:
    """Draws one line with its cap line at y and returns the column right after it."""
    for ch in text:
        width, pixels = glyph(ch)
        if not width:
            continue
        for dx, dy in pixels:
            canvas.put(x + dx, y + dy, color)
        x += width + 1
    return x


def clip(text: str, width: int) -> str:
    """The longest start of `text` that fits, with an ellipsis when something was cut."""
    if text_width(text) <= width:
        return text
    room = width - text_width("…") - 1
    out = ""
    for ch in text:
        if text_width(out + ch) > room:
            break
        out += ch
    return out.rstrip() + "…" if out else ""


@lru_cache(maxsize=8)
def wrap(text: str, width: int) -> tuple[str, ...]:
    """Breaks at spaces and inside words longer than a line; trailing spaces stay, since the caret follows them."""
    lines = [""]
    for token in re.findall(r"\S+|\s+", text):
        if text_width(lines[-1] + token) <= width:
            lines[-1] += token
            continue
        if token.isspace():
            lines.append("")
            continue
        if text_width(token) <= width:
            lines.append(token)
            continue
        for ch in token:
            if text_width(lines[-1] + ch) > width:
                lines.append("")
            lines[-1] += ch
    return tuple(lines)
