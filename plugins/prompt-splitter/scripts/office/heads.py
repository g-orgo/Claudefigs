"""Heads of the office characters in a 3/4 view turned to the left, built from shape masks per hair style.

Each head is a 20x16 grid of palette letters whose origin is 2 columns left of and 2 rows above the head's
top-left corner (the old hair overlay origin), so callers stamp it at (x - 2, y - 2). Only the silhouette gets the
dark outline; hair and skin are shaded with light from the top-left.
"""
from functools import lru_cache

W, H = 20, 16
OX, OY = 2, 2  # head origin inside the grid.


def _skull(x: int, y: int) -> bool:
    """Head shape: a rounded skull with the chin pulled toward the front (left)."""
    cx, cy = OX + 7.5, OY + 5.2
    dx, dy = (x - cx) / 7.2, (y - cy) / 5.9
    if y >= OY + 8:  # jaw narrows toward a chin under the face, which looks left.
        dx = (x - (cx - 1.0)) / (7.2 - (y - OY - 8) * 1.4)
    return dx * dx + dy * dy <= 1.0


def _cap(x: int, y: int, lift: float = 0.0) -> bool:
    """Hair volume over the skull: a slightly larger dome."""
    cx, cy = OX + 7.8, OY + 4.6
    dx, dy = (x - cx) / 8.4, (y - cy) / (6.3 + lift)
    return dx * dx + dy * dy <= 1.0


def _hair_mask(style: str):
    def base(x: int, y: int) -> bool:
        top = _cap(x, y) and y <= OY + 3
        nape = _cap(x, y) and x >= OX + 10 and y <= OY + 8
        fringe = OY + 3 < y <= OY + 4 and OX + 1 <= x <= OX + 9 and (x + y) % 3 != 0
        return top or nape or fringe

    extra = {
        "neat": lambda x, y: False,
        "bob": lambda x, y: (OX + 9 <= x <= OX + 15 and y <= OY + 11 and _cap(x, y - 3)) or (OX <= x <= OX + 1 and OY + 3 <= y <= OY + 8 and _cap(x, y, 2.0)),
        "spiky": lambda x, y: y < OY and (x - OX) % 4 in (1, 2) and OX + 1 <= x <= OX + 14 and y >= OY - 2 + (x % 2),
        "ponytail": lambda x, y: OX + 14 <= x <= OX + 17 and OY + 2 <= y <= OY + 10 - abs(x - OX - 15),
        "bun": lambda x, y: (x - OX - 11) ** 2 / 6.5 + (y - OY + 2.5) ** 2 / 3.2 <= 1,
        "curly": lambda x, y: _cap(x, y, 1.2) and (y <= OY + 4 or x >= OX + 9) and not (y == OY - 2 and x % 3 == 0),
        "long": lambda x, y: (OX + 9 <= x <= OX + 16 and y <= OY + 13 and _cap(x, y - 5)) or (OX <= x <= OX + 1 and OY + 3 <= y <= OY + 11 and _cap(x, y, 5.0)),
        "cap": lambda x, y: (y <= OY + 2 and _cap(x, y)) or (y == OY + 3 and OX - 2 <= x <= OX + 8),
    }[style]
    return lambda x, y: base(x, y) or extra(x, y)


@lru_cache(maxsize=None)
def head_rows(style: str) -> tuple[str, ...]:
    hair = _hair_mask(style)
    grid = [["." for _ in range(W)] for _ in range(H)]
    for y in range(H):
        for x in range(W):
            if hair(x, y):
                grid[y][x] = ("R" if y <= OY + 2 else "K") if style == "cap" and y <= OY + 3 else "h"
            elif _skull(x, y):
                grid[y][x] = "s"
    filled = {(x, y) for y in range(H) for x in range(W) if grid[y][x] != "."}
    for y in range(H):  # shading: top-left rim lit, bottom-right rim shaded, plus a hair highlight band.
        for x in range(W):
            ch = grid[y][x]
            if ch == ".":
                continue
            lit = (x - 1, y) not in filled or (x, y - 1) not in filled
            dark = (x + 1, y) not in filled or (x, y + 1) not in filled
            if ch == "h":
                if dark or (y >= OY + 3 and x >= OX + 12):
                    grid[y][x] = "d"
                elif lit or (OY - 1 <= y <= OY + 1 and OX + 3 <= x <= OX + 8 and (x + y) % 2 == 0):
                    grid[y][x] = "H"
                elif style == "curly" and (x * 3 + y * 5) % 7 in (0, 3):
                    grid[y][x] = "H" if (x + y) % 2 else "d"  # ringlets
            elif ch == "s" and (dark or x >= OX + 10):
                grid[y][x] = "S"
    for y in range(H):  # outline only around the silhouette.
        for x in range(W):
            if grid[y][x] == "." and any(p in filled for p in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))):
                grid[y][x] = "o"
    # ear just in front of the nape hair, and a soft line where hair meets the forehead.
    for ey in (OY + 6, OY + 7):
        if grid[ey][OX + 10] in "sS":
            grid[ey][OX + 10] = "S"
            grid[ey][OX + 11] = "O" if grid[ey][OX + 11] in "hdH" else grid[ey][OX + 11]
    return tuple("".join(row) for row in grid)


# Faces in head coordinates (stamped at x, y): far eye at column 2, near eye at columns 6-7, mouth at column 3.
EYES = {
    "open": [(5, "..e...eW........"), (6, "..e...ei........")],
    "blink": [(6, "..e...ee........")],
    "happy": [(5, "......ee........"), (6, ".e.e.e..e.......")],
    "down": [(6, "..e...ee........")],
    "right": [(5, "...e...eW......."), (6, "...e...ei.......")],
}
CHEEKS = (8, "..m....bb.......")
GLASSES = [(4, ".ggg.gggg......."), (5, "g...g...g......."), (6, ".ggg.gggg.......")]
