"""The writing field at the bottom of the office: a text draft, and the bubble-styled strip that draws it."""
from .bubble import CREAM, INK, TOOL, clip, width_of, wrap
from .term import Frame

COMPOSER_ROWS = 4
MIN_ROWS = 18  # below this height there is no field and the office keeps its full height.
MAX_TEXT = 4000
MAX_WIDTH = 120
BACKDROP = (38, 34, 54)
GOLD = (232, 178, 92)
TAN = (196, 172, 138)
WOOD = (138, 92, 62)
PLACEHOLDER_IDLE = "Aperte Tab para escrever..."
PLACEHOLDER_FOCUSED = "Escreva aqui..."
PIXEL = "▪ "  # plain-text square marker before the destination


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


def field_geometry(cols: int) -> tuple[int, int]:
    """Width and first column of the field, centered."""
    width = min(cols - 4, MAX_WIDTH)
    return width, max(0, (cols - width) // 2)


def draw_composer(frame: Frame, top: int, composer: Composer, destination: str, hint: str, tick: int) -> None:
    """Draws the field in the four rows starting at `top`, over the footer's dark backdrop."""
    width, col = field_geometry(frame.cols)
    if width < 8:
        return
    inner = width - 2
    right = clip(hint, inner)
    left = clip(PIXEL + destination, max(0, inner - width_of(right) - 2))
    bar = (" " + left).ljust(inner - width_of(right))[:inner - width_of(right)] + right
    frame.text(col, top, "╭" + bar + "╮", INK, GOLD if composer.focused else TAN)

    for i in range(2):
        frame.text(col, top + 1 + i, "│", WOOD, CREAM)
        frame.text(col + 1, top + 1 + i, " " * inner, INK, CREAM)
        frame.text(col + width - 1, top + 1 + i, "│", WOOD, CREAM)

    placeholder = not composer.text
    if placeholder:
        lines = [PLACEHOLDER_FOCUSED if composer.focused else PLACEHOLDER_IDLE]
    else:
        lines = wrap(composer.text, inner - 3)[-2:]
    for i, text in enumerate(lines):
        frame.text(col + 2, top + 1 + i, text, TOOL if placeholder else INK, CREAM)
    if composer.focused and not placeholder and (tick // 4) % 2 == 0:
        end = col + 2 + width_of(lines[-1])
        if end < col + width - 1:
            frame.text(end, top + len(lines), " ", INK, INK)

    frame.text(col, top + 3, "╰" + "─" * inner + "╯", WOOD, CREAM)
