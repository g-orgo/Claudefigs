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

HEAD = [
    "....oooooooo....", "..oossssssssoo..", ".ossssssssssssoo"[:15] + ".",
    *[".ossssssssssssо."[:2] + "s" * 12 + "o."] * 6,
    "..ossssssssssо.."[:3] + "s" * 10 + "o..", "...oossssssoo...", ".....oooooo.....",
]
# Eye expressions as (row, text) overlays on the head.
EYES = {
    "open": [(5, "...eW.....eW...."), (6, "...ee.....ee...."), (7, "...ei.....ei....")],
    "blink": [(6, "...ee.....ee....")],
    "happy": [(5, "...ee.....ee...."), (6, "..e..e...e..e...")],
    "down": [(6, "...eW.....eW...."), (7, "...ee.....ee....")],
    "right": [(5, "....eW.....eW..."), (6, "....ee.....ee..."), (7, "....ei.....ei...")],
}
CHEEKS = (8, "..bb...mm...bb..")
GLASSES = [(4, "..ooooo..ooooo.."), (5, "..o...o..o...o.."), (6, "..o...oooo...o.."), (7, "..o...o..o...o..")]

# Hair rows start 2 rows above the head and 2 columns left of it.
HAIR = {
    "neat": ["", "......oooooooo", "....oohHHhhhhhoo", "...ohHHhhhhhhhhho", "...ohHhhhhhhhhhho",
             "...ohhhhhhhhhshho", "...ohhhhsssssshho", "...oh..........ho"],
    "bob": ["", "......oooooooo", "....oohHHhhhhhoo", "...ohHHhhhhhhhhho", "..ohHhhhhhhhhhhhho",
            "..ohhhhhhhhhhhhhho", "..ohhhsshhssshhhho", "..ohh..........hho", "..ohh..........hho",
            "..ohh..........hho", "..ohh..........hho", "...oo..........oo"],
    "spiky": ["", ".......oo..oo", ".....oohHoohHoo", "...ooHHhhhHhhhhoo", "...ohHhhhhhhhhhho",
              "...ohhhshhhshhhho", "...ohsssssssssho", "...o............o"],
    "ponytail": ["", "......oooooooo", "....oohHHhhhhhooooo", "...ohHHhhhhhhhhhoHho", "...ohHhhhhhhhhhhohhho",
                 "...ohhhhhhshhhhho.ohho", "...ohhsssssssshho..ohho", "...oh..........ho..ohho",
                 "...................oho", "....................o"],
    "bun": ["........oooo", ".......oHhho", "......oohhhoo", "....oohHHhhhhhoo", "...ohHhhhhhhhhhho",
            "...ohhhhhhhhhhhho", "...ohsshhhhhsshho", "...o............o"],
    "curly": ["......oooooo", "....oohHhhHhoo", "...ohHhhhhhhHho", "..ohhHhhhhHhhhho", "..ohhhhhhhhhhHho",
              "..ohHhhshhhshhhho", "..ohhsssssssssho", "...oh..........ho", "...oo..........oo"],
    "long": ["", "......oooooooo", "....oohHHhhhhhoo", "...ohHHhhhhhhhhho", "..ohHhhhhhhhhhhhho",
             "..ohhhhhhshhhhhhho", "..ohhhsssssssshhho", "..ohh..........hho", "..ohh..........hho",
             "..ohh..........hho", "..ohh..........hho", "..ohh..........hho", "..ohh..........hho", "..ooo..........ooo"],
    "cap": ["", "......oooooooo", "....ooHHHHHHHHoo", "...oHHHHHHHHHHHHo", "...oHHHHHHHHHHHHo",
            ".oooKKKKKKKKKKKKKo", ".oKKKKKKKKKKKKKKKo", "...oh..........ho"],
}

SHOULDERS = "...oottkkttoo..."
TORSO = ["..otttttkktttto."[:3] + "ttttkktttt" + "o..", "..otTttkkttTto..", "..otTttKKttTto.."]
ARMS_DOWN = ["..osottKKttoso..", "...oottKKttoo..."]
LEGS = ["....oppppppo....", "....oppPPppo....", "....oppooppo....", "....oppooppo....", "...offfoofffo...", "...oooo..oooo..."]
STEP_A = ["....oppppppo....", "....oppPPppo....", "....oppooppo....", "....oppoofffo...", "...offfooooo....", "...oooo........."]
STEP_B = ["....oppppppo....", "....oppPPppo....", "....oppooppo....", "...offfooppo....", "....ooooofffo...", ".........oooo..."]
LOW = ["..otTotKKtoTto..", "..otoTtKKtToto..", "...otoTTTToto..."]

# name: (ticks per frame, frames); frame: (body rows, head dy, eyes, arm overlays, fx).
# Body rows from index FRONT_ROW on are drawn after the desk, resting on it.
FRONT_ROW = 6
# Seated overlays are stamped again after the desk, so an arm always rests on top of the furniture.
# The right arm is longer because the desk's rear edge runs down-right and its hand must still reach the keyboard.
ARM_L = (2, 2, ["otTo", "otTo", "otTo", "otto", "osso", ".oo."])
ARM_L_TAP = (2, 2, ["otTo", "otTo", "otTo", "otTo", "otto", "osso", ".oo."])
ARM_R = (2, 10, ["oTto", "oTto", "oTto", "oTto", "oTto", "otto", "osso", ".oo."])
ARM_R_TAP = (2, 10, ["oTto", "oTto", "oTto", "oTto", "otto", "osso", ".oo."])
ARM_R_HOLD = (2, 10, ["oTto", "oTto", "oTto", "otto", "osso", ".oo."])
SHEET = (4, 4, ["oooooooo", "oWWWWWWo", "oWggWWWo", "oWWWWWWo", "oWggggWo", "oWWWWWWo", "oooooooo"])
FOLDED = (5, 1, [".ooooooooooooo", "ottTTTTTTTTttso", "ottttttttttttso", ".ooooooooooooo"])
CUP_UP = (-2, 12, ["oooo.", "occoo", "occ.o", "oooo.", "oTo", "oTo"])
CUP_LOW = (3, 12, ["oooo.", "occoo", "occ.o", "oooo."])
PHONE = (-6, 14, ["ooo", "ono", "ono", "oso", "oTo", "oTo", "oto"])
CHIN = (-1, 11, ["oso", "oso", "oTo", "oTo", "oTo", "oTo", "oTo", "oto", ".o."])
sit = [SHOULDERS, *TORSO, *LOW[:2]]
standing = [SHOULDERS, *TORSO, *ARMS_DOWN, *LEGS]
HAND = (2, 12, ["oso", "oTo"])
REST = [ARM_L, ARM_R]
POSES = {
    "look": (9, [(sit, 0, "open", REST, ""), (sit, 0, "right", REST, ""), (sit, 1, "open", REST, ""), (sit, 0, "blink", REST, "")]),
    "chat": (6, [(standing, 0, "open", [], ""), (standing, 1, "happy", [HAND], ""), (standing, 0, "right", [HAND], ""), (standing, 1, "open", [], "")]),
    "bob": (5, [(standing, 0, "happy", [], ""), (standing, 1, "open", [], "")]),
    "stand": (7, [([SHOULDERS, *TORSO, *ARMS_DOWN, *LEGS], 0, "open", [], ""), ([SHOULDERS, *TORSO, *ARMS_DOWN, *LEGS], 1, "open", [], "")]),
    "walk": (2, [([SHOULDERS, *TORSO, *ARMS_DOWN, *STEP_A], 0, "open", [], ""), ([SHOULDERS, *TORSO, *ARMS_DOWN, *LEGS], 1, "open", [], ""),
                 ([SHOULDERS, *TORSO, *ARMS_DOWN, *STEP_B], 0, "open", [], ""), ([SHOULDERS, *TORSO, *ARMS_DOWN, *LEGS], 1, "open", [], "")]),
    "wait": (9, [([SHOULDERS, *TORSO, *ARMS_DOWN, *LEGS], 0, "right", [CUP_LOW], ""), ([SHOULDERS, *TORSO, *ARMS_DOWN, *LEGS], 1, "right", [CUP_LOW], ""),
                 ([SHOULDERS, *TORSO, *ARMS_DOWN, *LEGS], 1, "right", [CUP_UP], "steam"), ([SHOULDERS, *TORSO, *ARMS_DOWN, *LEGS], 0, "happy", [CUP_LOW], "")]),
    "type": (2, [(sit, 0, "down", [ARM_L_TAP, ARM_R], ""), (sit, 1, "down", [ARM_L, ARM_R_TAP], "")]),
    "read": (8, [(sit, 0, "down", [SHEET, ARM_L, ARM_R_HOLD], ""), (sit, 1, "down", [SHEET, ARM_L, ARM_R_HOLD], ""),
                 (sit, 1, "down", [SHEET, ARM_L, ARM_R_HOLD], ""), (sit, 0, "open", [SHEET, ARM_L, ARM_R_HOLD], "")]),
    "think": (10, [(sit, 0, "open", [ARM_L, CHIN], "dots"), (sit, 1, "right", [ARM_L, CHIN], "dots")]),
    "phone": (6, [(sit, 0, "open", [ARM_L, PHONE], ""), (sit, 1, "happy", [ARM_L, PHONE], "")]),
    "coffee": (12, [(sit, 0, "happy", [ARM_L, CUP_LOW], "done"), (sit, 1, "blink", [ARM_L, CUP_UP], "steam"), (sit, 0, "open", [ARM_L, CUP_LOW], "done")]),
    "nap": (14, [(sit, 6, "blink", [FOLDED], "zzz"), (sit, 7, "blink", [FOLDED], "zzz")]),
    "slump": (14, [(sit, 6, "blink", [FOLDED], "fail"), (sit, 7, "blink", [FOLDED], "fail")]),
}
LYING = 4  # from this head drop on, the head rests on the desk and is drawn over it.


def _palette(look: Look) -> dict[str, Color]:
    skin = rgb(look.skin)
    return {
        "o": (46, 34, 58), "s": skin, "h": rgb(look.hair), "H": rgb(look.hair_hi), "e": (40, 30, 60), "W": (255, 255, 255),
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


def _draw_head(canvas: Canvas, x: int, y: int, look: Look, pal: dict, dy: int, mood: str, tick: int, flip: bool) -> None:
    _stamp(canvas, x, y + dy, HEAD, pal, flip)
    if mood != "blink" and (tick + x) % 41 < 2:
        mood = "blink"
    for row, text in EYES[mood]:
        _stamp(canvas, x, y + dy + row, [text], pal, flip)
    _stamp(canvas, x, y + dy + CHEEKS[0], [CHEEKS[1]], pal, flip)
    if look.glasses:
        for row, text in GLASSES:
            _stamp(canvas, x, y + dy + row, [text.replace(" ", ".")], pal, flip)
    _stamp(canvas, x - 2, y + dy - 2, HAIR[look.hair_style], pal, flip, 19)


def _draw_arms(canvas: Canvas, x: int, y: int, arms: list, pal: dict, flip: bool) -> None:
    for top, col, rows in arms:
        wide = max(len(row) for row in rows)
        _stamp(canvas, x + (16 - col - wide if flip else col), y + 11 + top, rows, pal, flip, wide - 1)


def draw(canvas: Canvas, x: int, y: int, look: Look, pose: str, tick: int, layer: str = "all", flip: bool = False, eyes: str = "") -> str:
    """Draws a 16px wide character whose head top is at y; body starts at y+11. Returns the frame's fx name.

    "back" goes behind the desk, "front" over it: arms and a head lying on the desk are repeated there."""
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
