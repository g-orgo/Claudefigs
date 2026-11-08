"""Composition of a hotel-style avatar: head, face, hair styles, torso, arms and legs per pose (see rig.py)."""
from .rig import Grid, ellipse, limb, lit, polygon

HEAD_C, HEAD_R = (16.0, 13.0), (11.5, 12.5)
SHOULDER_BACK, SHOULDER_FRONT = (9, 31), (24, 34)  # up-left (far) and down-right (near) shoulders.
HIP_BACK, HIP_FRONT = (12, 50), (20, 52)
TORSO = [(9, 27), (15, 26), (25, 30), (26, 34), (24, 52), (9, 50), (7, 32)]


def _skull() -> set:
    return ellipse(*HEAD_C, *HEAD_R)


def _hair_cells(style: str) -> set:
    """Hair covers the crown and the back of the head (right side), leaving the face on the left."""
    cx, cy = HEAD_C
    crown = ellipse(cx + 0.5, cy - 1.5, 12.5, 11.5)
    fringe = {  # lowest hair row over the forehead, per column: each cut has its own fringe.
        "neat": lambda x: 9 + max(0, (13 - x) // 3),  # side-swept toward the face edge
        "bob": lambda x: 11,
        "spiky": lambda x: 9 + (2 if x % 4 == 1 else 0),
        "ponytail": lambda x: 7 + (1 if x > 12 else 0),
        "bun": lambda x: 7,
        "curly": lambda x: 10,
        "long": lambda x: 8 if 9 <= x <= 13 else 10,  # middle part
        "cap": lambda x: 9,
    }[style]
    cells = {(x, y) for x, y in crown if y <= fringe(x) or x > 19 and y < 21}
    if style == "bob":
        cells |= {(x, y) for x, y in ellipse(cx + 1, cy + 1, 13, 12.5) if (x > 18 or x < 6) and y < 24} | {(x, y) for x, y in crown if y <= 11}
    elif style == "spiky":
        for tip in (6, 11, 16, 21, 26):
            cells |= polygon([(tip - 3, 4), (tip, -3), (tip + 3, 4)])
    elif style == "ponytail":
        cells |= polygon([(24, 6), (31, 9), (33, 18), (31, 30), (27, 27), (27, 14)])
    elif style == "bun":
        cells |= ellipse(21, 0, 5.5, 4.5)
    elif style == "curly":
        cells = {(x, y) for x, y in ellipse(cx + 0.5, cy - 1, 14.5, 13) if y < 10 or x > 18 and y < 24 or x < 5 and y < 18}
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


def _face(g: Grid, mood: str, dy: int, glasses: bool) -> None:
    """Both eyes visible, the far one (left) narrower; nose as a shade, small mouth, blush, ear on the right."""
    eyes = {"open": (14, False), "right": (14, False), "down": (15, False), "blink": (15, True), "happy": (14, True)}
    row, closed = eyes[mood]
    shift = 1 if mood == "right" else 0
    for ex, w in ((7, 1), (13, 2)):
        if closed:
            for i in range(w + 1):
                g.px[(ex + i + shift, row + dy + (1 if mood == "blink" else 0))] = "e"
        else:
            for i in range(w):
                g.px[(ex + i + shift, row + dy)] = "W" if i == 0 and w == 2 else "e"
                g.px[(ex + i + shift, row + 1 + dy)] = "e"
                g.px[(ex + i + shift, row + 2 + dy)] = "e"
    g.px[(9, 18 + dy)] = "S"
    g.px[(9, 19 + dy)] = "S"
    for x in (9, 10, 11):
        g.px[(x, 22 + dy)] = "m" if x != 9 else "S"
    g.px[(14, 19 + dy)] = "b"
    g.px[(15, 19 + dy)] = "b"
    if glasses:
        for x in range(5, 18):
            g.px[(x, 13 + dy)] = "g"
        for y in (14, 15, 16):
            for x in (5, 10, 12, 17):
                g.px[(x, y + dy)] = "g"


def head(g: Grid, style: str, mood: str, dy: int = 0, glasses: bool = False) -> None:
    move = lambda cells: {(x, y + dy) for x, y in cells}
    g.paint(move(limb((16, 23), (16, 27), 4)), lit("s", "S", lambda x, y: x - 16))  # neck
    g.paint(move(_skull()), lit("s", "S", lambda x, y: x - 19 + (y - dy - 13) // 3))
    g.paint(move(ellipse(22.5, 16, 2.5, 3.2)), lit("s", "S", lambda x, y: x - 22))  # ear
    _face(g, mood, dy, glasses)
    hair = _hair_fill(style)
    g.paint(move(_hair_cells(style)), lambda x, y: hair(x, y - dy))
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
