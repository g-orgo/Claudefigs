"""Poses of the hotel-style avatar: joint positions per frame, and the drawing of one frame into a letter grid.

A frame is (legs, arms, head dy, eyes, fx): legs is None when seated (the desk hides them) or
(back knee, back foot, front knee, front foot); arms is ((elbow, hand) of the back arm, (elbow, hand) of the front
arm, prop or ""). Index 4 is the effect icon name, as the callers expect.
"""
from . import figure as F
from .rig import Grid, ellipse, polygon

STAND_LEGS = ((12, 63), (11, 74), (20, 64), (19, 76))
STEP_A = ((9, 63), (5, 73), (21, 64), (24, 75))
STEP_B = ((14, 63), (16, 74), (18, 64), (13, 76))
HANG = (((6, 42), (6, 51)), ((26, 44), (24, 53)), "")
SWING_A = (((8, 42), (11, 50)), ((25, 44), (21, 52)), "")
SWING_B = (((4, 42), (1, 50)), ((27, 44), (28, 52)), "")
WAVE = (((6, 42), (6, 51)), ((29, 40), (30, 29)), "")
CUP_LOW = (((6, 42), (6, 51)), ((25, 44), (20, 45)), "cup")
CUP_UP = (((6, 42), (6, 51)), ((22, 38), (13, 30)), "cup")
DESK = ((4, 41), (-2, 47))  # back hand on the keyboard
TYPE_A = (DESK, ((25, 45), (17, 50)), "")
TYPE_B = (((4, 40), (-1, 45)), ((25, 44), (18, 48)), "")
READ = (((3, 38), (-3, 41)), ((20, 42), (8, 43)), "sheet")
THINK = (DESK, ((22, 40), (14, 26)), "")
PHONE = (DESK, ((28, 36), (23, 22)), "phone")
SIP_LOW = (DESK, ((21, 45), (12, 46)), "cup")
SIP_UP = (DESK, ((20, 39), (11, 30)), "cup")  # the cup rim stays at the mouth, clear of the eyes
FOLDED = (((2, 46), (12, 47)), ((24, 47), (12, 49)), "")


def _frames(rows: list) -> list:
    return [tuple(r) for r in rows]


SIT = None
POSES = {
    "look": (9, _frames([(SIT, TYPE_A, 0, "open", ""), (SIT, TYPE_A, 0, "right", ""), (SIT, TYPE_A, 1, "open", ""), (SIT, TYPE_A, 0, "blink", "")])),
    "chat": (6, _frames([(STAND_LEGS, HANG, 0, "open", ""), (STAND_LEGS, WAVE, 1, "happy", ""), (STAND_LEGS, WAVE, 0, "right", ""),
                         (STAND_LEGS, HANG, 1, "open", "")])),
    "bob": (5, _frames([(STAND_LEGS, HANG, 0, "happy", ""), (STAND_LEGS, HANG, 1, "open", "")])),
    "stand": (7, _frames([(STAND_LEGS, HANG, 0, "open", ""), (STAND_LEGS, HANG, 1, "open", "")])),
    "walk": (2, _frames([(STEP_A, SWING_A, 0, "open", ""), (STAND_LEGS, HANG, 1, "open", ""), (STEP_B, SWING_B, 0, "open", ""),
                         (STAND_LEGS, HANG, 1, "open", "")])),
    "wait": (9, _frames([(STAND_LEGS, CUP_LOW, 0, "right", ""), (STAND_LEGS, CUP_LOW, 1, "right", ""), (STAND_LEGS, CUP_UP, 1, "right", "steam"),
                         (STAND_LEGS, CUP_LOW, 0, "happy", "")])),
    "type": (2, _frames([(SIT, TYPE_A, 0, "down", ""), (SIT, TYPE_B, 1, "down", "")])),
    "read": (8, _frames([(SIT, READ, 0, "down", ""), (SIT, READ, 1, "down", ""), (SIT, READ, 1, "down", ""), (SIT, READ, 0, "open", "")])),
    "think": (10, _frames([(SIT, THINK, 0, "open", "dots"), (SIT, THINK, 1, "right", "dots")])),
    "phone": (6, _frames([(SIT, PHONE, 0, "open", ""), (SIT, PHONE, 1, "happy", "")])),
    "coffee": (12, _frames([(SIT, SIP_LOW, 0, "happy", "done"), (SIT, SIP_UP, 1, "blink", "steam"), (SIT, SIP_LOW, 0, "open", "done")])),
    "nap": (14, _frames([(SIT, FOLDED, 18, "blink", "zzz"), (SIT, FOLDED, 19, "blink", "zzz")])),
    "slump": (14, _frames([(SIT, FOLDED, 18, "blink", "fail"), (SIT, FOLDED, 19, "blink", "fail")])),
}
LYING = 10  # from this head drop on, the head rests on the desk and is drawn over it.


def _prop(g: Grid, kind: str, hand: tuple) -> None:
    hx, hy = hand
    if kind == "cup":
        g.paint(polygon([(hx - 3, hy - 6), (hx + 2, hy - 6), (hx + 2, hy), (hx - 3, hy)]), lambda x, y: "W" if y == hy - 5 else "c")
    elif kind == "phone":
        g.paint(polygon([(hx - 1, hy - 7), (hx + 2, hy - 7), (hx + 2, hy + 1), (hx - 1, hy + 1)]), lambda x, y: "n" if y < hy - 2 else "g")
    elif kind == "sheet":
        g.paint(polygon([(hx - 1, hy - 12), (hx + 10, hy - 10), (hx + 10, hy + 3), (hx - 1, hy + 1)]),
                lambda x, y: "g" if (y - hy) % 3 == 0 and x < hx + 8 else "W")


def frame_grid(frame: tuple, style: str, mood: str, glasses: bool, layer: str, face: bool = True, lashes: bool = False) -> Grid:
    """Letter grid of one frame. layer "back" is the whole figure behind the desk, "front" only the arms (and a
    head lying on the desk) drawn over it, "all" everything for a standing character."""
    legs, (back, front, prop), dy, _, _ = frame
    g = Grid()
    lying = dy >= LYING
    if layer in ("all", "back"):
        F.arm(g, F.SHOULDER_BACK, *back)
        if legs:
            F.legs(g, *legs)
        F.torso(g)
        if not lying:
            F.head(g, style, mood, dy, glasses, face, lashes)
        F.arm(g, F.SHOULDER_FRONT, *front)
    else:
        # The back arm sits behind the torso: over the desk only its part outside the torso shows, otherwise it
        # would be painted across the chest.
        behind = Grid()
        F.arm(behind, F.SHOULDER_BACK, *back)
        chest = polygon(F.TORSO)
        g.px.update({p: c for p, c in behind.px.items() if p not in chest})
        F.arm(g, F.SHOULDER_FRONT, *front)
        if lying:
            F.head(g, style, mood, dy, glasses, face, lashes)
    if prop:
        _prop(g, prop, front[1])
    return g


def shows_head(frame: tuple, layer: str) -> bool:
    lying = frame[2] >= LYING
    return layer == "all" or (layer == "back") != lying
