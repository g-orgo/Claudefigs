"""Isometric furniture, room and small effect icons of the office viewer."""
from .sprites import Canvas, Color

OUTLINE: Color = (46, 34, 58)
WOOD, WOOD_L, WOOD_R = (232, 190, 140), (190, 140, 96), (160, 112, 78)
METAL, METAL_D = (120, 128, 150), (84, 90, 112)

# Size of a workstation: x, y of draw_desk are the desk's rear-left top corner.
DESK_W, DESK_H = 42, 30
SEAT_DX, SEAT_DY = 20, -8  # head top of a seated character, relative to the desk corner.

# Screen content per activity: rows of colored dashes that scroll.
SCREENS = {
    "code": [(120, 220, 160), (250, 200, 110), (140, 190, 255), (235, 130, 160)],
    "term": [(110, 240, 130), (110, 240, 130), (70, 170, 90), (150, 255, 170)],
    "doc": [(235, 238, 250), (190, 196, 220), (235, 238, 250), (210, 214, 235)],
    "web": [(120, 190, 255), (255, 255, 255), (150, 220, 190), (120, 190, 255)],
    "idle": [],
}
SCREEN_BG = {"code": (32, 36, 60), "term": (16, 26, 24), "doc": (120, 130, 170), "web": (52, 82, 140), "idle": (64, 92, 142)}
SCREEN_SHINE = (136, 168, 216)
BEZEL = (112, 120, 146)
BADGE_LIGHT, BADGE_DARK = (132, 232, 168), (52, 164, 100)  # top shine and bottom shade of the done badge.
LEG_DROP = 6  # floor contact of a leg, below the desk corner it hangs from.


def fill_poly(canvas: Canvas, points: list[tuple[int, int]], color: Color, edge: Color | None = OUTLINE) -> None:
    """Scanline fill of a convex polygon, with an optional outline."""
    ys = [p[1] for p in points]
    for y in range(min(ys), max(ys) + 1):
        xs = []
        for (ax, ay), (bx, by) in zip(points, points[1:] + points[:1]):
            if ay == by:
                if y == ay:
                    xs += [ax, bx]
            elif min(ay, by) <= y <= max(ay, by):
                xs.append(ax + (y - ay) * (bx - ax) // (by - ay))
        if xs:
            lo, hi = min(xs), max(xs)
            for x in range(lo, hi + 1):
                canvas.put(x, y, edge if edge and (x in (lo, hi)) else color)
    if edge:
        for (ax, ay), (bx, by) in zip(points, points[1:] + points[:1]):
            steps = max(abs(bx - ax), abs(by - ay), 1)
            for t in range(steps + 1):
                canvas.put(ax + (bx - ax) * t // steps, ay + (by - ay) * t // steps, edge)


def draw_chair(canvas: Canvas, x: int, y: int, color: Color) -> None:
    fill_poly(canvas, [(x + 21, y - 3), (x + 35, y - 3), (x + 36, y + 12), (x + 20, y + 12)], color)


def draw_desk(canvas: Canvas, x: int, y: int) -> None:
    """A long desk along the down-right axis; the character sits behind its rear edge."""
    p0, p1, p2, p3 = (x + 12, y), (x + 40, y + 14), (x + 28, y + 20), (x, y + 6)
    for lx, (_, ly) in ((p3[0] + 1, p3), (p2[0] - 1, p2), (p1[0] - 3, p1)):
        # Each leg starts inside the skirt, which is drawn over its top, so it can never float below the desk.
        fill_poly(canvas, [(lx, ly + 1), (lx + 2, ly + 1), (lx + 2, ly + LEG_DROP), (lx, ly + LEG_DROP)], METAL_D, None)
        for leg_y in range(ly + 1, ly + LEG_DROP + 1):
            canvas.put(lx, leg_y, METAL)
    fill_poly(canvas, [p3, p2, (p2[0], p2[1] + 3), (p3[0], p3[1] + 3)], WOOD_L)
    fill_poly(canvas, [p2, p1, (p1[0], p1[1] + 3), (p2[0], p2[1] + 3)], WOOD_R)
    fill_poly(canvas, [p0, p1, p2, p3], WOOD)


def draw_monitor(canvas: Canvas, x: int, y: int, screen: str, tick: int, glow: bool = True) -> None:
    """A small monitor on the left of the desk: a bezeled screen facing the camera, on a stand over the desk top."""
    mx, my = x + 13, y - 10
    cx = mx - 6
    fill_poly(canvas, [(cx - 6, y + 7), (cx, y + 4), (cx + 6, y + 7), (cx, y + 10)], METAL)
    # The neck goes over the base and has no bottom edge, so the two read as a single outlined piece.
    for neck_y in range(my + 11, y + 7):
        canvas.put(cx - 1, neck_y, OUTLINE)
        canvas.put(cx, neck_y, METAL_D)
        canvas.put(cx + 1, neck_y, OUTLINE)
    fill_poly(canvas, [(mx, my), (mx, my + 10), (mx - 13, my + 16), (mx - 13, my + 6)], BEZEL)
    bg = SCREEN_BG[screen] if glow else SCREEN_BG["idle"]
    rows = SCREENS[screen] if glow else []
    for col in range(10):
        top = my + 2 + ((col + 2) * 6) // 13
        for row in range(7):
            color = bg
            if not glow and 4 <= col + row <= 5 and row <= 4:
                color = SCREEN_SHINE
            if rows and row % 2 == 0:
                line = (row // 2 + tick // 3)
                width = 3 + (line * 7) % 8
                if col < width:
                    color = rows[line % len(rows)]
            canvas.put(mx - 2 - col, top + row, color)


def draw_keyboard(canvas: Canvas, x: int, y: int) -> None:
    fill_poly(canvas, [(x + 24, y + 9), (x + 33, y + 13), (x + 27, y + 16), (x + 18, y + 12)], (238, 240, 248))


def draw_props(canvas: Canvas, x: int, y: int, seed: int) -> None:
    """A small object per desk, varied by seed: mug, paper stack or tiny plant."""
    kind = seed % 3
    px, py = x + 13, y + 9
    if kind == 0:
        fill_poly(canvas, [(px, py), (px + 3, py), (px + 3, py + 3), (px, py + 3)], (240, 110, 110))
    elif kind == 1:
        fill_poly(canvas, [(px - 2, py + 1), (px + 3, py - 1), (px + 7, py + 1), (px + 2, py + 3)], (250, 250, 255))
    else:
        fill_poly(canvas, [(px, py + 1), (px + 3, py + 1), (px + 3, py + 3), (px, py + 3)], (200, 130, 90))
        fill_poly(canvas, [(px - 1, py - 3), (px + 4, py - 3), (px + 3, py), (px, py)], (96, 190, 120), None)


ICONS = {
    "dots": ("#8a8fa8", ["ooooooooo", "oWWWWWWWo", "oWkWkWkWo", "oWWWWWWWo", "ooooooooo", "...oo"]),
    "ask": ("#ffd24a", ["ooooooo", "oWkkkWo", "oWWWkWo", "oWWkkWo", "oWWkWWo", "oWWWWWo", "oWWkWWo", "ooooooo", "..oo"]),
    "alert": ("#ffd24a", ["ooooo", "oWkWo", "oWkWo", "oWkWo", "oWWWo", "oWkWo", "ooooo", ".oo"]),
    "done": ("#4fcf7f", ["..ooooo..", ".oLLLLLo.", "oLggggWLo", "oggggWWgo", "ogWgWWggo", "ogWWWgggo", "oggWggggo", ".oDDDDDo.", "..ooooo.."]),
    "fail": ("#ff6b6b", ["oo...oo", "oWo.oWo", ".oWoWo.", "..oWo..", ".oWoWo.", "oWo.oWo", "oo...oo"]),
    "heart": ("#ff7fa8", [".oo.oo.", "oWkokWo", "okkkkko", ".okkko.", "..oko..", "...o..."]),
    "zzz": ("#5d6fe0", ["oooo", "..o.", ".o..", "oooo"]),
    "steam": ("#ffffff", [".W.", "W..", ".W."]),
}


def draw_icon(canvas: Canvas, x: int, y: int, name: str) -> None:
    from .sprites import rgb
    tone, rows = ICONS[name]
    color = rgb(tone)
    pal = {"o": OUTLINE, "W": color if name in ("fail", "steam") else (255, 255, 255), "k": color if name == "heart" else OUTLINE,
           "g": color, "L": BADGE_LIGHT, "D": BADGE_DARK}
    if name == "zzz":
        pal = {"o": color}
    for j, row in enumerate(rows):
        for i, ch in enumerate(row):
            if ch != ".":
                canvas.put(x + i, y + j, pal[ch])


DOOR_DARK = (38, 34, 54)
CHAMFER_CELLS = 12  # wall corner setback, must match rooms.CHAMFER
# tile_light, tile_dark, grout, wall_left, wall_center, wall_right, cap
ROOM_PALETTES = [
    ((236, 222, 190), (224, 208, 172), (204, 186, 150), (176, 152, 120), (196, 172, 138), (160, 136, 106), (224, 206, 174)),
    ((206, 232, 210), (190, 222, 198), (166, 202, 176), (122, 160, 136), (144, 182, 156), (106, 144, 120), (200, 226, 206)),
    ((222, 212, 240), (208, 196, 232), (186, 172, 214), (146, 130, 180), (166, 150, 200), (130, 114, 164), (220, 210, 238)),
    ((246, 218, 200), (238, 204, 184), (218, 180, 160), (186, 136, 116), (206, 156, 134), (168, 120, 102), (242, 214, 196)),
    ((202, 230, 240), (186, 220, 234), (160, 200, 218), (108, 156, 180), (130, 178, 200), (94, 140, 164), (196, 226, 238)),
    ((244, 210, 220), (236, 194, 208), (216, 170, 186), (178, 124, 146), (200, 144, 166), (160, 108, 130), (240, 206, 218)),
]
CORRIDOR_TILES = ((204, 214, 226), (190, 201, 216), (172, 183, 200))  # light, dark, grout


def tile_color(x: int, y: int, light: Color, dark: Color, grout: Color) -> Color:
    """Isometric floor tile colour at a pixel: grout on the tile edges, checker light and dark otherwise."""
    a, b = (x + 2 * y) // 28, (2 * y - x) // 28
    on_edge = (x + 2 * y) % 28 == 0 or (2 * y - x) % 28 == 0
    return grout if on_edge else (light if (a + b) % 2 == 0 else dark)


def _shade(color: Color, factor: float) -> Color:
    return tuple(int(c * factor) for c in color)


def draw_corridor(canvas: Canvas) -> None:
    """Plain tiled floor behind the rooms."""
    light, dark, grout = CORRIDOR_TILES
    for y in range(canvas.height):
        for x in range(canvas.width):
            canvas.rows[y][x] = tile_color(x, y, light, dark, grout)


def draw_room_shell(canvas: Canvas, room, sign_width: int) -> None:
    """Walls, floor, corner posts, door and sign backing of one room. room is a rooms.Room (duck-typed)."""
    tile_light, tile_dark, grout, wall_left, wall_center, wall_right, cap = ROOM_PALETTES[room.palette]
    left, right, top, bottom = room.left, room.right, room.top, room.bottom
    base = room.floor_edge
    height = room.floor_y - top - 2
    k = CHAMFER_CELLS

    for x in range(left, right + 1):
        for y in range(base(x), bottom + 1):
            canvas.put(x, y, tile_color(x, y, tile_light, tile_dark, grout))

    for x in range(left, right + 1):
        b = base(x)
        t = b - height
        wall = wall_left if x < left + 2 * k else wall_right if x > right - 2 * k else wall_center
        for y in range(t, b):
            if y - t < 3:
                color = cap
            elif y - t == 3:
                color = _shade(wall, 0.8)
            elif y >= b - 2:
                color = _shade(wall, 0.75)
            else:
                color = wall
            canvas.put(x, y, color)
        canvas.put(x, t - 1, OUTLINE)
        canvas.put(x, b, OUTLINE)

    for x in (left + 2 * k, right - 2 * k):
        b = base(x)
        for y in range(b - height, b + 1):
            canvas.put(x, y, OUTLINE)
    for x in list(range(left, left + 3)) + list(range(right - 2, right + 1)):
        b = base(x)
        for y in range(b - height, b):
            canvas.put(x, y, cap)
    for x in (left, right):
        b = base(x)
        for y in range(b - height - 1, bottom + 1):
            canvas.put(x, y, OUTLINE)
    for x in (left + 3, right - 3):
        b = base(x)
        for y in range(b - height, b + 1):
            canvas.put(x, y, OUTLINE)

    depth = min(14, height - 3)
    door = range(right - 19, right - 6)
    for x in door:
        b = base(x)
        frame = x in (door[0], door[-1])
        for y in range(b - depth, b):
            canvas.put(x, y, WOOD_L if frame or y == b - depth else DOOR_DARK)
        canvas.put(x, b, WOOD)
    for x in (door.start - 1, door.stop):
        b = base(x)
        for y in range(b - depth - 1, b):
            canvas.put(x, y, OUTLINE)

    for x in range(left + 1, right):
        canvas.put(x, bottom - 1, _shade(grout, 0.8))
    for x in range(left, right + 1):
        canvas.put(x, bottom, OUTLINE)

    x0, x1 = room.sign_col - 1, room.sign_col + sign_width
    y0, y1 = top - 1, top + 2
    for x in range(x0, x1 + 1):
        canvas.put(x, y0, OUTLINE)
        canvas.put(x, y1, OUTLINE)
    for y in range(y0, y1 + 1):
        canvas.put(x0, y, OUTLINE)
        canvas.put(x1, y, OUTLINE)
