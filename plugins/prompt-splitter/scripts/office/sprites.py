"""Chibi characters of the office viewer: pixel art as text rows, recolored per Look."""
from dataclasses import dataclass


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
    lashes: bool = False  # a lash dot beside each eye.


# LOOKS[0] is the main character: white dress shirt and red tie.
LOOKS = [
    Look("neat", "#ffd9bf", "#3a2c3f", "#5d4a68", "#3a2c3f", "#fbfbff", "#c9cfe0", "#e0405a", "#a92a44"),
    Look("bob", "#ffe0cc", "#e0708f", "#f7a3b8", "#7a3350", "#7fd0c8", "#55a8a3", "#fff4d6", "#e0cfa0", "#54486e", lashes=True),
    Look("spiky", "#e8b48f", "#f2b632", "#ffdc72", "#35527a", "#5c7fd6", "#4260ad", "#dde6ff", "#a9b9e8", "#2f3550"),
    Look("ponytail", "#ffd9bf", "#8a4b2d", "#b56f45", "#3f6b3a", "#f6c6d4", "#d79db0", "#ffffff", "#e7d3da", "#6a4f7c", lashes=True),
    Look("bun", "#c98d67", "#2b2233", "#4b3d57", "#2b2233", "#f4b04f", "#cf8a2e", "#fff0c9", "#e3c98c", glasses=True, lashes=True),
    Look("curly", "#8f5d41", "#2c1f22", "#51393b", "#2c1f22", "#9b6fd6", "#7850ad", "#e7d8ff", "#bda6e6", "#3d3a58", lashes=True),
    Look("long", "#ffe6d6", "#6f7fe0", "#9eaafa", "#2f3a8a", "#ffffff", "#d3d8ea", "#3f4f86", "#2d3a68", "#39405f", lashes=True),
    Look("cap", "#f0c3a2", "#7a4a2a", "#e65f5f", "#40384e", "#6cc47c", "#4c9c5c", "#e6ffe9", "#b5e6be", "#49434f", glasses=True),
]

# Head in a 3/4 view turned toward the monitor on the left: the far side (right) is in shade and shows an ear.
from .poses import LYING, POSES  # noqa: E402  (joint frames of the hotel-style avatar)
from . import poses as _poses  # noqa: E402
from . import figure as _figure  # noqa: E402
from .rig import CELL_W  # noqa: E402


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
        "o": OUTLINE, "F": _tone(rgb(look.shoes), 1.6), "d": _tone(rgb(look.hair), 0.72), "R": rgb(look.hair_hi), "r": _tone(rgb(look.hair_hi), 0.72), "w": _tone(rgb(look.hair_hi), 1.25), "s": skin, "S": _tone(skin, 0.84), "O": _tone(skin, 0.7), "h": rgb(look.hair), "H": rgb(look.hair_hi), "e": (40, 30, 60), "W": (255, 255, 255),
        "i": rgb(look.eyes), "b": (255, 150, 150), "m": (190, 90, 90), "t": rgb(look.top), "T": rgb(look.top_sh),
        "k": rgb(look.accent), "K": rgb(look.accent_sh), "p": rgb(look.pants), "P": tuple(max(0, c - 20) for c in rgb(look.pants)),
        "f": rgb(look.shoes), "c": (250, 250, 250), "n": (90, 200, 255), "g": (170, 175, 195), "G": (52, 46, 66), "Q": (112, 106, 128),
    }


def _stamp(canvas: Canvas, x: int, y: int, rows: list[str], pal: dict[str, Color], flip: bool, mirror: int = 15) -> None:
    for j, row in enumerate(rows):
        for i, ch in enumerate(row):
            if ch != "." and ch != " ":
                canvas.put(x + (mirror - i if flip else i), y + j, pal[ch])


def frame_of(pose: str, tick: int) -> tuple:
    speed, frames = POSES[pose]
    return frames[(tick // speed) % len(frames)]


def draw(canvas: Canvas, x: int, y: int, look: Look, pose: str, tick: int, layer: str = "all", flip: bool = False, eyes: str = "",
         small: bool = False) -> str:
    """Draws the avatar whose CELL_W wide cell starts at x and whose head top is at y; returns the frame's fx name.

    "back" goes behind the desk, "front" over it (arms, and a head lying on the desk). small draws it at half size,
    like the hotel's zoomed-out view, for the hall and the warehouse."""
    frame = frame_of(pose, tick)
    mood = eyes or frame[3]
    if mood != "blink" and (tick + x) % 41 < 2:
        mood = "blink"
    grid = _poses.frame_grid(frame, look.hair_style, mood, look.glasses, layer, face=not small, lashes=look.lashes)
    pal = _palette(look)
    px = {p: pal[c] for p, c in grid.px.items()}
    if small:
        px = _half(px)
        if _poses.shows_head(frame, layer):
            skin = {pal["s"], pal["S"], pal["O"]}
            row = _figure.small_eye_row(mood, frame[2])
            cols = [x for (x, y), c in px.items() if y == row and c in skin]
            if cols:
                span = (min(cols), max(cols))
                for p, c in _figure.small_face(mood, frame[2], look.glasses, look.lashes, span).items():
                    if p in px and px[p] != OUTLINE:
                        px[p] = pal[c]
    width = CELL_W // 2 if small else CELL_W
    layer_px = _Layer(shade=False)
    for (gx, gy), color in px.items():
        layer_px.put(x + (width - 1 - gx if flip else gx), y + gy, color)
    layer_px.flush(canvas)
    return frame[4]


def _half(px: dict) -> dict:
    """Half-size copy: each 2x2 block keeps its most common color, the outline wins on the silhouette."""
    blocks: dict = {}
    for (x, y), color in px.items():
        blocks.setdefault((x // 2, y // 2), []).append(color)
    out = {}
    for key, colors in blocks.items():
        if len(colors) < 2:
            continue
        fills = [c for c in colors if c != OUTLINE]
        out[key] = max(set(fills), key=fills.count) if len(fills) >= 3 or (fills and len(colors) == len(fills)) else OUTLINE
    return out
