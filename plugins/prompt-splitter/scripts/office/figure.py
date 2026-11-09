"""Composition of a hotel-style avatar: head, face, hair styles, torso, arms and legs per pose (see rig.py)."""
from .rig import Grid, ellipse, limb, lit, polygon

HEAD_C, HEAD_R = (16.0, 13.0), (11.5, 12.5)
SHOULDER_BACK, SHOULDER_FRONT = (10, 34), (23, 36)  # up-left (far) and down-right (near) shoulders.
HIP_BACK, HIP_FRONT = (12, 50), (20, 52)
TORSO = [(9, 27), (15, 26), (25, 30), (26, 34), (24, 52), (9, 50), (7, 32)]


JAW = [(4.5, 12), (4.5, 22), (6.5, 26), (9.5, 28.6), (16, 28.6), (20, 26), (23, 19)]  # long face down to a soft chin.


def _skull() -> set:
    return ellipse(*HEAD_C, *HEAD_R) | polygon(JAW)


def _hair_cells(style: str) -> set:
    """Hair covers the crown and the back of the head (right side), leaving the face on the left."""
    cx, cy = HEAD_C
    crown = ellipse(cx + 0.5, cy - 1.5, 12.5, 11.5)
    fringe = {  # lowest hair row over the forehead, per column: each cut has its own fringe.
        "neat": lambda x: 11 + max(0, (13 - x) // 4),  # side-swept toward the face edge
        "bob": lambda x: 12,
        "spiky": lambda x: 11 + (1 if x % 4 == 1 else 0),
        "ponytail": lambda x: 10 + (1 if x > 12 else 0),
        "bun": lambda x: 10,
        "curly": lambda x: 11,
        "long": lambda x: 10 if 9 <= x <= 13 else 12,  # middle part
        "cap": lambda x: 9,
    }[style]
    cells = {(x, y) for x, y in crown if y <= fringe(x) or x > 19 and y < 21}
    if style == "bob":
        cells |= {(x, y) for x, y in ellipse(cx + 1, cy + 1, 13, 12.5) if (x > 18 or x < 5) and y < 24} | {(x, y) for x, y in crown if y <= 11}
    elif style == "spiky":
        for tip in (6, 11, 16, 21, 26):
            cells |= polygon([(tip - 3, 4), (tip, -3), (tip + 3, 4)])
    elif style == "ponytail":
        cells |= polygon([(24, 6), (31, 9), (33, 18), (31, 30), (27, 27), (27, 14)])
    elif style == "bun":
        cells |= ellipse(21, 0, 5.5, 4.5)
    elif style == "curly":
        cells = {(x, y) for x, y in ellipse(cx + 0.5, cy - 1, 14.5, 13) if y < 12 or x > 18 and y < 24 or x < 5 and y < 18}
    elif style == "long":
        cells |= polygon([(19, 8), (29, 10), (30, 40), (26, 46), (20, 42), (21, 22)]) | {(x, y) for x, y in crown if x < 6 and y < 22}
    elif style == "cap":
        cells = {(x, y) for x, y in crown if x > 19 and y < 21}
    return cells


def _hair_fill(style: str):
    def fill(x: int, y: int) -> str:
        if style == "curly" and (x * 5 + y * 3) % 7 == 0:
            return "H"
        if 2 <= y <= 3 and 6 + (3 - y) <= x <= 16 - (3 - y) or y == 4 and 9 <= x <= 13:
            return "H"  # one solid shine band across the crown.
        return "d" if x >= 22 or y >= 18 else "h"
    return fill


EYE_ROW = 15
NEAR_EYE = ("eW", "ee", "ie")  # 2x3: catch light on top, a touch of iris colour below.
FAR_EYE = NEAR_EYE  # both eyes alike, so neither reads as closed or smaller.


def _face(g: Grid, mood: str, dy: int, glasses: bool, lashes: bool = False) -> None:
    """Far eye (left) foreshortened, near eye with iris and catch light, nose shade, lips, blush, ear on the right."""
    row = EYE_ROW + dy + (1 if mood == "down" else 0)
    shift = 1 if mood == "right" else 0
    put = lambda x, y, c: g.px.__setitem__((x, y), c)
    closed = mood in ("blink", "happy")
    for ex, eye in ((7, FAR_EYE), (13, NEAR_EYE)):
        x0, w = ex + shift, len(eye[0])
        if lashes:  # a lash dot beside the top of each eye, on its outer side; it follows a closed lid.
            if closed:  # an upward flick at the outer end of the lid line.
                put(x0 - 2 if ex < 10 else x0 + w + 1, row, "e")
            else:  # touching the top of the eye.
                put(x0 - 1 if ex < 10 else x0 + w, row, "e")
        if mood in ("blink", "happy"):
            for i in range(-1, w + 1 if w > 1 else 1):  # a closed eye is a line, never a single dot.
                arc = mood == "happy" and w > 1 and i in (-1, w)
                put(x0 + i, row + 1 + (1 if arc else 0), "e")
        else:
            for j, line in enumerate(eye):
                for i, c in enumerate(line):
                    put(x0 + i, row + j, c)
    put(11, 18 + dy, "S")  # nose: a short shaded ridge ending in a nostril shadow.
    put(11, 19 + dy, "O")
    put(12, 19 + dy, "S")
    if mood == "happy":
        for x, y in ((9, 21), (10, 22), (11, 22), (12, 22), (13, 21)):
            put(x, y + dy, "m")
    else:
        put(9, 22 + dy, "O")  # mouth corner
        put(10, 22 + dy, "m")
        put(11, 22 + dy, "m")
        put(12, 22 + dy, "m")
    put(15, 19 + dy, "b")
    put(16, 19 + dy, "b")
    put(19, 25 + dy, "S")  # jaw shade under the cheek
    put(20, 24 + dy, "S")
    if glasses:  # two closed rectangular rims sharing one column as the bridge, 1 px of clear lens on all four
        top, low = row - 2, row + 4  # sides of each eye, and a temple arm from the outer rim toward the ear.
        for x0, x1 in ((5 + shift, 11 + shift), (11 + shift, 17 + shift)):
            for x in range(x0, x1 + 1):
                put(x, top, "G")
                put(x, low, "G")
            for y in range(top, low + 1):
                put(x0, y, "G")
                put(x1, y, "G")
        for x in range(18 + shift, 20 + shift):  # temple, ends where the hair or ear starts
            put(x, top, "G")


def head(g: Grid, style: str, mood: str, dy: int = 0, glasses: bool = False, face: bool = True, lashes: bool = False) -> None:
    move = lambda cells: {(x, y + dy) for x, y in cells}
    g.paint(move(limb((16, 25), (16, 30), 4)), lit("S", "O", lambda x, y: x - 16))  # neck, in the chin's shadow
    g.paint(move(_skull()), lit("s", "S", lambda x, y: x - 19 + (y - dy - 13) // 3))
    g.paint(move(ellipse(22.5, 16, 2.5, 3.2)), lit("s", "S", lambda x, y: x - 22))  # ear
    if face:
        _face(g, mood, dy, glasses, lashes)
    hair = _hair_fill(style)
    hair_cells = move(_hair_cells(style))
    g.paint(hair_cells, lambda x, y: hair(x, y - dy))
    for x, y in hair_cells:  # the fringe casts a soft shadow band on the forehead.
        if (x, y + 1) not in hair_cells and g.px.get((x, y + 2)) == "s":
            g.px[(x, y + 2)] = "S"
    if style == "cap":
        crown = {(x, y) for x, y in ellipse(17, 5, 12, 7) if y <= 9}
        g.paint(move(crown), lambda x, y: "w" if 2 <= y - dy <= 3 and 8 <= x <= 14 else ("r" if x > 22 else "R"))
        g.paint(move(polygon([(2, 9), (14, 8), (16, 11), (3, 13)])), lambda x, y: "r")  # brim toward the face


def torso(g: Grid, low: int = 0) -> None:
    cells = polygon([(x, y + low) for x, y in TORSO])
    g.paint(cells, lit("t", "T", lambda x, y: x - 19 + (y - 30) // 4))
    for y in range(28, 50):  # placket or tie down the front, along the body's diagonal.
        g.px[(13 + (y - 28) // 8, y + low)] = "k" if y < 46 else "K"


def arm(g: Grid, shoulder: tuple, elbow: tuple, hand: tuple) -> None:
    g.paint(limb(shoulder, elbow, 6) | limb(elbow, hand, 5), lit("t", "T", lambda x, y: x - max(shoulder[0], hand[0]) + 1))
    g.paint(ellipse(hand[0] + 0.5, hand[1] + 0.5, 2.6, 2.6), lit("s", "S", lambda x, y: x - hand[0]))


def legs(g: Grid, back_knee: tuple, back_foot: tuple, front_knee: tuple, front_foot: tuple) -> None:
    for hip, knee, foot in ((HIP_BACK, back_knee, back_foot), (HIP_FRONT, front_knee, front_foot)):
        g.paint(limb(hip, knee, 8) | limb(knee, foot, 7), lit("p", "P", lambda x, y, k=knee: x - k[0] - 1))
        g.paint(ellipse(foot[0] - 2, foot[1] + 2, 5, 2.8), lit("f", "F", lambda x, y, f=foot: f[0] - x - 3))


def small_eye_row(mood: str, dy: int) -> int:
    return (EYE_ROW + 1 + dy) // 2 + (1 if mood == "down" else 0)  # first clean skin row under every fringe


def small_face(mood: str, dy: int, glasses: bool, lashes: bool, span: tuple) -> dict:
    """Face of the half-size avatar on the half grid: downsampled eyes would merge into a bar, so the small view gets
    two equal dot eyes at fixed columns, like the hotel's zoomed-out avatars (no sideways glance: a shifted eye would
    touch the face edge and look bigger). Lashes add a dot beside the top of each eye, on its outer side; span is the
    skin (left, right) of the eye row, for the glasses rim."""
    row = small_eye_row(mood, dy)
    closed = mood in ("blink", "happy")
    px = {}
    for ex, out in ((4, -1), (7, 1)):
        px[(ex, row + 1)] = "e"
        if not closed:  # both eyes open or close together.
            px[(ex, row)] = "e"
        if lashes:
            px[(ex + out, row + 1 if closed else row)] = "e"
    px[(5, row + 3)] = "m"
    px[(6, row + 3)] = "m"
    if glasses:  # one mid-grey rim per eye: a top bar meeting at the bridge and an outer post beside the eye.
        # The rim is lighter than the eyes, so it never merges with them into a band; nothing goes below the eyes.
        for ex, out in ((4, -1), (7, 1)):
            for x in (ex - 1, ex, ex + 1):
                px[(x, row - 1)] = "Q"
            px[(ex + out, row)] = "Q"
            px[(ex + out, row + 1)] = "Q"
    return px
