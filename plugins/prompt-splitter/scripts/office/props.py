"""Isometric furniture, room and small effect icons of the office viewer."""
from dataclasses import dataclass

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
BADGE_RIMS = {  # (top shine, bottom shade) of the coloured rim on the round status badges.
    "done": ((132, 232, 168), (52, 164, 100)),
    "fail": ((255, 142, 150), (160, 34, 50)),
}
LEG_DROP = 6  # floor contact of a leg, below the desk corner it hangs from.


SKIRT = 4  # height of the desk's side faces.


@dataclass(frozen=True)
class Kit:
    """One furniture set: the desk's materials, the monitor model and what sits on the desk."""
    name: str
    top: Color
    top_hi: Color
    grain: Color
    left: Color
    right: Color
    trim: Color
    seam: Color
    knob: Color
    leg: Color
    leg_hi: Color
    chair: Color
    chair_hi: Color
    chair_lo: Color
    monitor: str  # "flat" | "crt" | "wide" | "candy"
    bezel: Color
    case: Color
    case_hi: Color
    stand: Color
    stand_hi: Color
    neck: Color
    keys: Color
    key_cap: Color
    key_gap: Color
    rgb: bool
    mat: Color | None
    items: tuple  # (near the keyboard options, far corner, flat note or None)


CLASSIC = Kit("classica", WOOD, (250, 216, 170), (214, 170, 120), WOOD_L, WOOD_R, (212, 164, 116), (136, 94, 64), (250, 214, 120),
              METAL_D, METAL, (98, 112, 160), (130, 146, 196), (70, 82, 124), "flat", BEZEL, (84, 90, 112), (150, 158, 180),
              METAL, (168, 176, 198), METAL_D, (226, 230, 240), (250, 252, 255), (150, 156, 176), False, None,
              (("mug", "papers"), "plant", "note_yellow"))
RETRO = Kit("retro", (168, 108, 70), (204, 146, 100), (140, 86, 54), (124, 76, 48), (100, 60, 38), (150, 96, 62), (72, 42, 28), (236, 200, 110),
            (70, 54, 48), (108, 86, 74), (150, 74, 60), (190, 104, 84), (108, 50, 42), "crt", (214, 204, 176), (170, 160, 134), (232, 224, 200),
            (200, 190, 162), (232, 224, 200), (150, 140, 116), (204, 194, 166), (236, 228, 204), (140, 130, 108), False, None,
            (("floppies", "mug"), "banker", None))
GAMER = Kit("gamer", (62, 66, 84), (92, 98, 124), (52, 56, 72), (44, 46, 62), (34, 36, 50), (80, 220, 232), (22, 24, 34), (255, 90, 170),
            (30, 32, 44), (70, 74, 96), (52, 54, 74), (232, 70, 110), (34, 36, 50), "wide", (40, 42, 56), (28, 30, 42), (70, 74, 96),
            (44, 46, 62), (120, 232, 240), (28, 30, 42), (30, 32, 44), (90, 96, 120), (18, 20, 28), True, None,
            (("soda", "soda"), "headset", None))
ATELIER = Kit("atelie", (244, 240, 232), (255, 255, 255), (226, 220, 210), (206, 216, 214), (176, 190, 190), (232, 234, 228), (130, 150, 150), (240, 130, 150),
              (222, 150, 160), (246, 190, 196), (120, 200, 190), (170, 232, 220), (80, 160, 152), "candy", (96, 206, 200), (60, 160, 158), (150, 232, 224),
              (244, 240, 232), (255, 255, 255), (180, 190, 190), (250, 226, 232), (255, 246, 248), (222, 150, 170), False, None,
              (("pencils", "sketch"), "cactus", "note_pink"))
STUDY = Kit("biblioteca", (122, 58, 48), (166, 92, 74), (98, 44, 38), (92, 42, 36), (72, 32, 30), (178, 140, 80), (50, 22, 20), (240, 206, 120),
            (58, 34, 30), (96, 62, 50), (56, 110, 84), (92, 152, 118), (36, 78, 60), "flat", (64, 60, 66), (40, 38, 44), (98, 92, 100),
            (178, 140, 80), (232, 200, 130), (120, 92, 50), (58, 54, 60), (116, 110, 116), (28, 26, 30), False, (60, 112, 86),
            (("books", "inkwell"), "globe", None))
KITS = [CLASSIC, RETRO, GAMER, ATELIER, STUDY]


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


def _shade_area(canvas: Canvas, points: list[tuple[int, int]], factor: float = 0.82) -> None:
    """Darkens what is already painted inside a convex polygon: the soft contact shadow of a furniture."""
    ys = [p[1] for p in points]
    for y in range(min(ys), max(ys) + 1):
        xs = []
        for (ax, ay), (bx, by) in zip(points, points[1:] + points[:1]):
            if ay != by and min(ay, by) <= y <= max(ay, by):
                xs.append(ax + (y - ay) * (bx - ax) // (by - ay))
        if xs and 0 <= y < canvas.height:
            for col in range(max(0, min(xs)), min(canvas.width, max(xs) + 1)):
                r, g, b = canvas.rows[y][col]
                canvas.rows[y][col] = (int(r * factor), int(g * factor), int(b * factor))


def draw_chair(canvas: Canvas, x: int, y: int, kit: Kit = CLASSIC) -> None:
    """Padded backrest with rounded top, seams and a shaded side."""
    left, right, top, bottom = x + 20, x + 36, y - 4, y + 12
    fill_poly(canvas, [(left + 2, top), (right - 2, top), (right, top + 2), (right, bottom), (left, bottom), (left, top + 2)], kit.chair)
    for col in range(left + 2, right - 1):
        canvas.put(col, top + 1, kit.chair_hi)
    for row in range(top + 2, bottom):
        canvas.put(left + 1, row, kit.chair_hi)
        canvas.put(right - 1, row, kit.chair_lo)


def _draw_desk_top(canvas: Canvas, x: int, y: int, kit: Kit, corners: tuple) -> None:
    p0, p1, p2, p3 = corners
    fill_poly(canvas, [p0, p1, p2, p3], kit.top)
    for lane, phase in ((1, 0), (2, 5), (3, 2)):  # grain lanes along the long axis, broken so they read as wood.
        bx, by = x + 3 * lane, y + 6 - lane * 3 // 2
        for t in range(2, 26):
            if (t * 3 + phase) % 11 < 7:
                canvas.put(bx + t, by + t // 2, kit.grain)
    for t in range(1, 27):  # bright rim along the edge closest to the camera.
        canvas.put(p3[0] + 1 + t, p3[1] - 1 + (t + 1) // 2, kit.top_hi)
    for t in range(1, 11):
        canvas.put(p3[0] + 1 + t, p3[1] - t // 2, kit.top_hi)


def draw_desk(canvas: Canvas, x: int, y: int, kit: Kit = CLASSIC) -> None:
    """A long desk along the down-right axis; the character sits behind its rear edge."""
    p0, p1, p2, p3 = (x + 12, y), (x + 40, y + 14), (x + 28, y + 20), (x, y + 6)
    drop = LEG_DROP
    _shade_area(canvas, [(p3[0] + 1, p3[1] + drop), (p2[0], p2[1] + drop + 1), (p1[0] - 1, p1[1] + drop), (p1[0] - 1, p1[1]), (p3[0] + 1, p3[1])])
    for lx, (_, ly) in ((p3[0] + 1, p3), (p2[0] - 1, p2), (p1[0] - 3, p1)):
        # Each leg starts inside the skirt, which is drawn over its top, so it can never float below the desk.
        fill_poly(canvas, [(lx, ly + 1), (lx + 2, ly + 1), (lx + 2, ly + drop), (lx, ly + drop)], kit.leg, None)
        for leg_y in range(ly + 1, ly + drop + 1):
            canvas.put(lx, leg_y, kit.leg_hi)
    fill_poly(canvas, [p3, p2, (p2[0], p2[1] + SKIRT), (p3[0], p3[1] + SKIRT)], kit.left)
    fill_poly(canvas, [p2, p1, (p1[0], p1[1] + SKIRT), (p2[0], p2[1] + SKIRT)], kit.right)
    for t in range(3, 25):  # bright lip below the top, then a drawer with its handle on the long face.
        canvas.put(p3[0] + t, p3[1] + (t + 1) // 2 + 1, kit.trim)
    for t in range(8, 21):
        canvas.put(p3[0] + t, p3[1] + (t + 1) // 2 + 2, kit.seam)
    canvas.put(p3[0] + 14, p3[1] + 9, kit.knob)
    canvas.put(p3[0] + 15, p3[1] + 10, kit.knob)
    _draw_desk_top(canvas, x, y, kit, (p0, p1, p2, p3))


def _screen_pixels(canvas: Canvas, mx: int, my: int, cols: int, height: int, slope: int, bg: Color, rows: list, tick: int, idle: bool) -> None:
    for col in range(cols):
        top = my + 2 + ((col + 2) * 6) // slope
        for row in range(height):
            color = bg
            if idle and 4 <= col + row <= 5 and row <= 4:
                color = SCREEN_SHINE
            if rows and row % 2 == 0:
                line = (row // 2 + tick // 3)
                width = 3 + (line * 7) % 8
                if col < width:
                    color = rows[line % len(rows)]
            elif rows and col + row == cols - 1:
                color = tuple(min(255, c + 34) for c in bg)  # diagonal glare over a lit screen.
            canvas.put(mx - 2 - col, top + row, color)


def draw_monitor(canvas: Canvas, x: int, y: int, screen: str, tick: int, glow: bool = True, kit: Kit = CLASSIC) -> None:
    """A monitor on the left of the desk: a cased screen facing the camera, on a stand over the desk top."""
    wide = kit.monitor == "wide"
    mx, my = x + (15 if wide else 13), y - 10
    width, tall, cols, rows_tall = (16, 9, 13, 6) if wide else (13, 10, 10, 7)
    depth = {"crt": 3, "flat": 1, "wide": 1, "candy": 2}[kit.monitor]
    cx = x + 7
    fill_poly(canvas, [(cx - 6, y + 7), (cx, y + 4), (cx + 6, y + 7), (cx, y + 10)], kit.stand)
    for t in range(1, 6):  # lit rim of the foot.
        canvas.put(cx - t, y + 4 + (t + 1) // 2, kit.stand_hi)
    # The neck goes over the base and has no bottom edge, so the two read as a single outlined piece.
    for neck_y in range(my + 11, y + 7):
        canvas.put(cx - 1, neck_y, OUTLINE)
        canvas.put(cx, neck_y, kit.neck)
        canvas.put(cx + 1, neck_y, OUTLINE)
    drop = (width * 6) // 13
    back = (-depth * 2, -depth)
    fill_poly(canvas, [(mx - width, my + drop), (mx - width, my + drop + tall), (mx - width + back[0], my + drop + tall + back[1]), (mx - width + back[0], my + drop + back[1])], kit.case)
    fill_poly(canvas, [(mx, my), (mx - width, my + drop), (mx - width + back[0], my + drop + back[1]), (mx + back[0], my + back[1])], kit.case_hi)
    fill_poly(canvas, [(mx, my), (mx, my + tall), (mx - width, my + drop + tall), (mx - width, my + drop)], kit.bezel)
    bg = SCREEN_BG[screen] if glow else SCREEN_BG["idle"]
    rows = SCREENS[screen] if glow else []
    _screen_pixels(canvas, mx, my, cols, rows_tall, 13, bg, rows, tick, not glow)
    canvas.put(mx - 2, my + tall - 1, (120, 240, 150) if glow else (90, 96, 110))  # power light.


ICONS = {
    "dots": ("#8a8fa8", ["ooooooooo", "oWWWWWWWo", "oWkWkWkWo", "oWWWWWWWo", "ooooooooo", "...oo"]),
    "ask": ("#ffd24a", ["ooooooo", "oWkkkWo", "oWWWkWo", "oWWkkWo", "oWWkWWo", "oWWWWWo", "oWWkWWo", "ooooooo", "..oo"]),
    "alert": ("#ffd24a", ["ooooo", "oWkWo", "oWkWo", "oWkWo", "oWWWo", "oWkWo", "ooooo", ".oo"]),
    "done": ("#4fcf7f", ["..ooooo..", ".oLLLLLo.", "oLggggWLo", "oggggWWgo", "ogWgWWggo", "ogWWWgggo", "oggWggggo", ".oDDDDDo.", "..ooooo.."]),
    "fail": ("#dc3c4c", ["..ooooo..", ".oLLLLLo.", "oLWgggWLo", "oggWgWggo", "ogggWgggo", "oggWgWggo", "ogWgggWgo", ".oDDDDDo.", "..ooooo.."]),
    "heart": ("#ff7fa8", [".oo.oo.", "oWkokWo", "okkkkko", ".okkko.", "..oko..", "...o..."]),
    "zzz": ("#5d6fe0", ["oooo", "..o.", ".o..", "oooo"]),
    "steam": ("#ffffff", [".W.", "W..", ".W."]),
}


def draw_icon(canvas: Canvas, x: int, y: int, name: str) -> None:
    from .sprites import rgb
    tone, rows = ICONS[name]
    color = rgb(tone)
    light, dark = BADGE_RIMS.get(name, (color, color))
    pal = {"o": OUTLINE, "W": color if name == "steam" else (255, 255, 255), "k": color if name == "heart" else OUTLINE,
           "g": color, "L": light, "D": dark}
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

    # The first desk line's bubbles end 6 pixels above floor_y: the lintel stays below them, so no bubble cuts the door.
    door = range(right - 15, right - 6)
    lintel = room.floor_y - 4
    for x in door:
        b = base(x)
        frame = x in (door[0], door[-1])
        for y in range(lintel, b):
            canvas.put(x, y, WOOD_L if frame or y == lintel else DOOR_DARK)
        canvas.put(x, lintel - 1, OUTLINE)
        canvas.put(x, b, WOOD)
    for x in (door.start - 1, door.stop):
        for y in range(lintel - 1, base(x)):
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
