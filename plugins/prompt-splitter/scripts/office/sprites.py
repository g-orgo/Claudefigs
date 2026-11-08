"""Chibi characters of the office viewer: pixel art as text rows, recolored per Look."""
from dataclasses import dataclass

from . import avatar as A

Color = tuple[int, int, int]


def rgb(value: str) -> Color:
    return int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16)


class Canvas:
    def __init__(self, width: int, height: int, fill: Color = (0, 0, 0)):
        self.width, self.height = width, height
        self.rows = [[fill] * width for _ in range(height)]

    def copy(self) -> "Canvas":
        out = Canvas.__new__(Canvas)
        out.width, out.height, out.rows = self.width, self.height, [row[:] for row in self.rows]
        return out

    def put(self, x: int, y: int, color: Color) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            self.rows[y][x] = color


@dataclass(frozen=True)
class Look:
    hair_style: str
    skin: str
    hair: str
    hair_hi: str
    eyes: str
    top: str
    top_sh: str
    accent: str
    accent_sh: str
    pants: str = "#3b4262"
    shoes: str = "#2a2433"
    glasses: bool = False


# LOOKS[0] is the main character: white dress shirt and red tie.
LOOKS = [
    Look("neat", "#ffd9bf", "#3a2c3f", "#5d4a68", "#3a2c3f", "#fbfbff", "#c9cfe0", "#e0405a", "#a92a44"),
    Look("bob", "#ffe0cc", "#e0708f", "#f7a3b8", "#7a3350", "#7fd0c8", "#55a8a3", "#fff4d6", "#e0cfa0", "#54486e"),
    Look("spiky", "#e8b48f", "#f2b632", "#ffdc72", "#35527a", "#5c7fd6", "#4260ad", "#dde6ff", "#a9b9e8", "#2f3550"),
    Look("ponytail", "#ffd9bf", "#8a4b2d", "#b56f45", "#3f6b3a", "#f6c6d4", "#d79db0", "#ffffff", "#e7d3da", "#6a4f7c"),
    Look("bun", "#c98d67", "#2b2233", "#4b3d57", "#2b2233", "#f4b04f", "#cf8a2e", "#fff0c9", "#e3c98c", glasses=True),
    Look("curly", "#8f5d41", "#2c1f22", "#51393b", "#2c1f22", "#9b6fd6", "#7850ad", "#e7d8ff", "#bda6e6", "#3d3a58"),
    Look("long", "#ffe6d6", "#6f7fe0", "#9eaafa", "#2f3a8a", "#ffffff", "#d3d8ea", "#3f4f86", "#2d3a68", "#39405f"),
    Look("cap", "#f0c3a2", "#7a4a2a", "#e65f5f", "#40384e", "#6cc47c", "#4c9c5c", "#e6ffe9", "#b5e6be", "#49434f", glasses=True),
]

# Head in a 3/4 view turned toward the monitor on the left: the far side (right) is in shade and shows an ear.
# Head turned to the left, toward the monitor: features sit on the left half, the right half is nape and ear.
HEAD = [
    "....oooooooo....", "..oossssssssoo..", ".osssssssssssSo.", ".osssssssssssSo.", "ossssssssssssSo.",
    "osssssssssSSoSo.", "osssssssssSSSSo.", ".ossssssssSSoSo.", ".osssssssssSSSo.",
    "..osssssssssSSo.", "...oosssssSSoo..", ".....oooooo.....",
]
# Eye expressions as (row, text) overlays; the far eye is a narrow sliver, the near one is full.
EYES = {
    "open": [(5, ".eW...ei........"), (6, ".ee...e........."), (7, ".ei.............")],
    "blink": [(6, ".ee...e.........")],
    "happy": [(5, ".ee...e........."), (6, "e..e..e.........")],
    "down": [(6, ".eW...e........."), (7, ".ee.............")],
    "right": [(5, "..eW...e........"), (6, "..ee...e........"), (7, "..ei............")],
}
CHEEKS = (8, ".bbm..bb........")
GLASSES = [(4, "..ooooo..ooooo.."), (5, "..o...o..o...o.."), (6, "..o...oooo...o.."), (7, "..o...o..o...o..")]

# Hair rows start 2 rows above the head and 2 columns left of it.
# name: (ticks per frame, frames); frame: (body rows, head dy, eyes, arm overlays, fx). Rows are avatar rows
# padded into the 16-wide cell; overlays are (row from the body top, avatar column, rows).
SIT = A.pad(A.SIT)
STAND = A.pad(A.STAND)
STEP_A, STEP_B = A.pad(A.STEP_A), A.pad(A.STEP_B)
FRONT_ROW = len(A.SIT)  # the seated body stays behind the desk; only overlays are drawn over it.
REST = [A.ARM_DESK]
HANG = [A.ARM_HANG]
POSES = {
    "look": (9, [(SIT, 0, "open", REST, ""), (SIT, 0, "right", REST, ""), (SIT, 1, "open", REST, ""), (SIT, 0, "blink", REST, "")]),
    "chat": (6, [(STAND, 0, "open", HANG, ""), (STAND, 1, "happy", [A.HAND_UP], ""), (STAND, 0, "right", [A.HAND_UP], ""), (STAND, 1, "open", HANG, "")]),
    "bob": (5, [(STAND, 0, "happy", HANG, ""), (STAND, 1, "open", HANG, "")]),
    "stand": (7, [(STAND, 0, "open", HANG, ""), (STAND, 1, "open", HANG, "")]),
    "walk": (2, [(STEP_A, 0, "open", HANG, ""), (STAND, 1, "open", HANG, ""), (STEP_B, 0, "open", HANG, ""), (STAND, 1, "open", HANG, "")]),
    "wait": (9, [(STAND, 0, "right", [A.CUP_LOW], ""), (STAND, 1, "right", [A.CUP_LOW], ""), (STAND, 1, "right", [A.CUP_UP], "steam"),
                 (STAND, 0, "happy", [A.CUP_LOW], "")]),
    "type": (2, [(SIT, 0, "down", [A.ARM_TAP], ""), (SIT, 1, "down", [A.ARM_DESK], "")]),
    "read": (8, [(SIT, 0, "down", [A.SHEET, A.ARM_DESK], ""), (SIT, 1, "down", [A.SHEET, A.ARM_DESK], ""),
                 (SIT, 1, "down", [A.SHEET, A.ARM_DESK], ""), (SIT, 0, "open", [A.SHEET, A.ARM_DESK], "")]),
    "think": (10, [(SIT, 0, "open", [A.ARM_DESK, A.FAR_HAND_CHIN], "dots"), (SIT, 1, "right", [A.ARM_DESK, A.FAR_HAND_CHIN], "dots")]),
    "phone": (6, [(SIT, 0, "open", [A.ARM_DESK, A.PHONE], ""), (SIT, 1, "happy", [A.ARM_DESK, A.PHONE], "")]),
    "coffee": (12, [(SIT, 0, "happy", [A.ARM_DESK, A.CUP_LOW], "done"), (SIT, 1, "blink", [A.ARM_DESK, A.CUP_UP], "steam"),
                    (SIT, 0, "open", [A.ARM_DESK, A.CUP_LOW], "done")]),
    "nap": (14, [(SIT, 6, "blink", [A.FOLDED], "zzz"), (SIT, 7, "blink", [A.FOLDED], "zzz")]),
    "slump": (14, [(SIT, 6, "blink", [A.FOLDED], "fail"), (SIT, 7, "blink", [A.FOLDED], "fail")]),
}
LYING = 4  # from this head drop on, the head rests on the desk and is drawn over it.


OUTLINE: Color = (46, 34, 58)


def _tone(color: Color, factor: float) -> Color:
    return tuple(max(0, min(255, int(c * factor))) for c in color)


def soften_lines(px: dict) -> dict:
    """Selective outline: an outline pixel with drawn pixels on all four sides is an inner line, so it takes a dark tone
    of the fill around it; the silhouette keeps the full dark outline."""
    out = dict(px)
    for (x, y), color in px.items():
        if color != OUTLINE:
            continue
        around = [px.get(p) for p in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))]
        if None in around:
            continue
        fills = [c for c in around if c != OUTLINE]
        if fills:
            base = max(set(fills), key=fills.count)
            out[(x, y)] = _tone(base, 0.62)
    return out


class _Layer:
    """Collects one character's pixels so they can be shaded as a whole before reaching the canvas."""

    def __init__(self, shade: bool = True):
        self.px: dict[tuple[int, int], Color] = {}
        self.shade = shade  # characters are shaded by hand; small decor gets the automatic rims.

    def put(self, x: int, y: int, color: Color) -> None:
        self.px[(x, y)] = color

    def flush(self, canvas: Canvas) -> None:
        """Light from the top-left: a fill pixel touching the outline (or the edge) on its right or below gets a shade
        tone, one touching it on its left or above gets a highlight, which gives every pose a rounded volume."""
        px = soften_lines(self.px)
        for (x, y), color in px.items():
            if self.shade and color != OUTLINE:
                right, below = px.get((x + 1, y), OUTLINE), px.get((x, y + 1), OUTLINE)
                left, above = px.get((x - 1, y), OUTLINE), px.get((x, y - 1), OUTLINE)
                if right == OUTLINE or below == OUTLINE:
                    color = _tone(color, 0.82)
                elif left == OUTLINE or above == OUTLINE:
                    color = _tone(color, 1.12)
            canvas.put(x, y, color)


def _palette(look: Look) -> dict[str, Color]:
    skin = rgb(look.skin)
    return {
        "o": OUTLINE, "F": _tone(rgb(look.shoes), 1.6), "d": _tone(rgb(look.hair), 0.72), "R": rgb(look.hair_hi), "s": skin, "S": _tone(skin, 0.84), "O": _tone(skin, 0.7), "h": rgb(look.hair), "H": rgb(look.hair_hi), "e": (40, 30, 60), "W": (255, 255, 255),
        "i": rgb(look.eyes), "b": (255, 150, 150), "m": (190, 90, 90), "t": rgb(look.top), "T": rgb(look.top_sh),
        "k": rgb(look.accent), "K": rgb(look.accent_sh), "p": rgb(look.pants), "P": tuple(max(0, c - 20) for c in rgb(look.pants)),
        "f": rgb(look.shoes), "c": (250, 250, 250), "n": (90, 200, 255), "g": (170, 175, 195),
    }


def _stamp(canvas: Canvas, x: int, y: int, rows: list[str], pal: dict[str, Color], flip: bool, mirror: int = 15) -> None:
    for j, row in enumerate(rows):
        for i, ch in enumerate(row):
            if ch != "." and ch != " ":
                canvas.put(x + (mirror - i if flip else i), y + j, pal[ch])


def frame_of(pose: str, tick: int) -> tuple:
    speed, frames = POSES[pose]
    return frames[(tick // speed) % len(frames)]


def _overlay(canvas: Canvas, x: int, y: int, row: int, col: int, rows: list[str], pal: dict, flip: bool) -> None:
    """Stamps avatar-coordinate rows; a flipped character mirrors them inside its 16-wide cell."""
    wide = max(len(r) for r in rows)
    left = x + 3 + col
    if flip:
        left = x + 15 - (3 + col + wide - 1)
    _stamp(canvas, left, y + row, rows, pal, flip, wide - 1)


def _draw_head(canvas: Canvas, x: int, y: int, look: Look, pal: dict, dy: int, mood: str, tick: int, flip: bool) -> None:
    rows, above = A.STYLES[look.hair_style]
    if look.hair_style == "long" and dy < LYING:
        _overlay(canvas, x, y + dy, A.BODY_TOP, 0, A.LONG_TAIL, pal, flip)
    _overlay(canvas, x, y + dy - above, 0, -2, rows, pal, flip)
    if mood != "blink" and (tick + x) % 41 < 2:
        mood = "blink"
    for row, col, eye in A.EYES[mood]:
        _overlay(canvas, x, y + dy, row, col, eye, pal, flip)
    for row, col, part in (A.MOUTH, A.CHEEK):
        _overlay(canvas, x, y + dy, row, col, part, pal, flip)
    if look.glasses:
        _overlay(canvas, x, y + dy, *A.GLASSES, pal, flip)


def _draw_arms(canvas: Canvas, x: int, y: int, arms: list, pal: dict, flip: bool) -> None:
    for row, col, rows in arms:
        _overlay(canvas, x, y, A.BODY_TOP + row, col, rows, pal, flip)


def draw(canvas: Canvas, x: int, y: int, look: Look, pose: str, tick: int, layer: str = "all", flip: bool = False, eyes: str = "") -> str:
    """Draws a 16px wide character whose head top is at y; body starts at y+11. Returns the frame's fx name.

    "back" goes behind the desk, "front" over it: arms and a head lying on the desk are repeated there."""
    target, canvas = canvas, _Layer(shade=False)
    try:
        return _draw(canvas, x, y, look, pose, tick, layer, flip, eyes)
    finally:
        canvas.flush(target)


def _draw(canvas, x: int, y: int, look: Look, pose: str, tick: int, layer: str, flip: bool, eyes: str) -> str:
    body, dy, expression, arms, fx = frame_of(pose, tick)
    pal = _palette(look)
    mood = eyes or expression
    if layer in ("all", "front"):
        _stamp(canvas, x, y + 11 + FRONT_ROW, body[FRONT_ROW:], pal, flip)
    if layer == "front":
        _draw_arms(canvas, x, y, arms, pal, flip)
        if dy >= LYING:
            _draw_head(canvas, x, y, look, pal, dy, mood, tick, flip)
        return fx
    _stamp(canvas, x, y + 11 + dy // 3, body[:FRONT_ROW], pal, flip)
    _draw_head(canvas, x, y, look, pal, dy, mood, tick, flip)
    _draw_arms(canvas, x, y, arms, pal, flip)
    return fx
