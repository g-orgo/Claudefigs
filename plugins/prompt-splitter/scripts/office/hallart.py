"""Art of the hall and the warehouse: office fronts with glass, the roller door, the break corner and the crates."""
from .props import OUTLINE, fill_poly
from .sprites import Canvas, Color
from .term import WHITE

BAY_W, BAY_H, DEPTH = 58, 34, 6
CAP = 3  # roof strip of a free-standing office.
PADDING = 8  # spare interior rows, so an angled window never reads outside the room.
DOOR = (3, 7, 14, BAY_H - 8)  # column, row, width, height inside the front wall.
ROLLER = (6, 6, BAY_W - 12, BAY_H - 7)  # column, row, width, height of the warehouse roller door.
WINDOW = (20, 4, BAY_W - 23, BAY_H - 10)
WALLS = ((226, 214, 190), (206, 222, 214), (222, 208, 224), (214, 218, 234), (232, 214, 200), (210, 224, 196))
WOOD, WOOD_D = (176, 122, 84), (138, 92, 62)
GLASS: Color = (176, 214, 240)
INSIDE, INSIDE_FLOOR = (240, 234, 216), (206, 196, 176)
LAMPS = {"run": (90, 230, 130), "wait": (255, 190, 60), "fail": (240, 90, 90), "idle": (150, 154, 170)}


def rect(canvas: Canvas, x: int, y: int, w: int, h: int, color: Color) -> None:
    for j in range(h):
        for i in range(w):
            canvas.put(x + i, y + j, color)


def box(canvas: Canvas, x: int, y: int, w: int, h: int, color: Color, edge: Color = OUTLINE) -> None:
    rect(canvas, x, y, w, h, edge)
    rect(canvas, x + 1, y + 1, w - 2, h - 2, color)


def shade(color: Color, factor: float) -> Color:
    return tuple(min(255, int(c * factor)) for c in color)


def draw_shell(canvas: Canvas, x: int, y: int, wall: Color, roof: bool = True) -> None:
    """The box of one office seen from outside: roof edge and right side when free standing, and the front wall."""
    if roof:
        run = 2 * DEPTH  # the depth recedes along a 2:1 diagonal, like every other isometric edge.
        fill_poly(canvas, [(x, y), (x + run, y - DEPTH), (x + BAY_W + run - 1, y - DEPTH), (x + BAY_W - 1, y)], shade(wall, 1.08))
        fill_poly(canvas, [(x + BAY_W - 1, y), (x + BAY_W + run - 1, y - DEPTH), (x + BAY_W + run - 1, y + BAY_H - DEPTH - 1), (x + BAY_W - 1, y + BAY_H - 1)], shade(wall, 0.72))
        for t in range(1, BAY_W - 1):  # lit rim where the roof meets the front wall.
            canvas.put(x + t, y - 1, shade(wall, 1.2))
    box(canvas, x, y, BAY_W, BAY_H, wall)
    rect(canvas, x + 1, y + BAY_H - 3, BAY_W - 2, 2, shade(wall, 0.62))


def draw_office_front(canvas: Canvas, x: int, y: int, wall: Color, roof: bool = True) -> None:
    draw_shell(canvas, x, y, wall, roof)
    dx, dy, dw, dh = DOOR
    box(canvas, x + dx, y + dy, dw, dh, WOOD)
    box(canvas, x + dx + 3, y + dy + 3, dw - 6, 8, GLASS)
    rect(canvas, x + dx + 3, y + dy + 14, dw - 6, 1, WOOD_D)
    rect(canvas, x + dx + dw - 3, y + dy + 13, 2, 2, (250, 220, 120))
    wx, wy, ww, wh = WINDOW
    box(canvas, x + wx - 1, y + wy - 1, ww + 2, wh + 2, INSIDE)


def window_left(panel) -> int:
    return BAY_W - WINDOW[0] - WINDOW[2] if panel.mirror else WINDOW[0]


def draw_glass(canvas: Canvas, panel, inside: Canvas, tick: int) -> None:
    """Copies the room's interior through tinted glass; the people stay upright even on an angled wall."""
    left, wy, ww, wh = window_left(panel), WINDOW[1], WINDOW[2], WINDOW[3]
    shine = tick // 3
    middle = panel.shift(left + ww // 2)
    for i in range(ww):
        col = left + i
        shift = panel.shift(col)
        for j in range(wh):
            r, g, b = inside.rows[j + shift - middle + PADDING][i]
            mix = 0.84 if (i + j - shine) % 34 > 3 else 0.62
            canvas.put(panel.x + col, panel.y + shift + wy + j, (int(r * mix + GLASS[0] * (1 - mix)), int(g * mix + GLASS[1] * (1 - mix)), int(b * mix + GLASS[2] * (1 - mix))))
    for j in range(wh):
        canvas.put(panel.x + left + ww // 2, panel.y + middle + wy + j, OUTLINE)


def draw_dark_window(flat: Canvas) -> None:
    """An office with nobody in it: lights off behind the glass."""
    wx, wy, ww, wh = WINDOW
    rect(flat, wx, wy, ww, wh, (64, 70, 96))
    rect(flat, wx + ww // 2, wy, 1, wh, OUTLINE)
    for i in range(8):
        rect(flat, wx + 4 + i, wy + 12 - i, 2, 1, (92, 100, 130))


def blit_panel(canvas: Canvas, flat: Canvas, panel) -> None:
    """Draws a flat office front onto the wall, mirrored and following the wall's slope."""
    for col in range(BAY_W):
        source = BAY_W - 1 - col if panel.mirror else col
        shift = panel.shift(col)
        for j in range(BAY_H):
            canvas.put(panel.x + col, panel.y + shift + j, flat.rows[j][source])


def new_interior() -> Canvas:
    inside = Canvas(WINDOW[2], WINDOW[3] + 2 * PADDING, INSIDE)
    rect(inside, 0, WINDOW[3] + PADDING - 6, WINDOW[2], 6 + PADDING, INSIDE_FLOOR)
    return inside


def draw_desk_edge(inside: Canvas) -> None:
    """The desks seen through the glass, hiding the characters' lower bodies."""
    top = WINDOW[3] + PADDING - 5
    rect(inside, 0, top, WINDOW[2], 1, OUTLINE)
    rect(inside, 0, top + 1, WINDOW[2], 3, (226, 184, 136))
    rect(inside, 0, top + 4, WINDOW[2], 1, OUTLINE)
    rect(inside, 0, top + 5, WINDOW[2], PADDING, INSIDE_FLOOR)


def draw_lamp(canvas: Canvas, panel, status: str, tick: int) -> None:
    color = LAMPS[status]
    if status == "wait" and (tick // 6) % 2:
        color = shade(color, 0.6)
    col = DOOR[0] + 5
    col = BAY_W - col - 4 if panel.mirror else col
    box(canvas, panel.x + col, panel.y + panel.shift(col) + 2, 4, 4, color)


def draw_roller_front(canvas: Canvas, x: int, y: int, back: bool) -> None:
    """The warehouse's roller door; back marks the one that returns to the office, which is wooden."""
    draw_shell(canvas, x, y, (190, 196, 206) if not back else (226, 214, 190))
    rx, ry, rw, rh = ROLLER
    box(canvas, x + rx, y + ry, rw, rh, (128, 138, 156) if not back else WOOD)
    for j in range(2, rh - 1, 3):
        rect(canvas, x + rx + 1, y + ry + j, rw - 2, 1, (98, 106, 124) if not back else WOOD_D)
    stripe = (250, 200, 60)
    for i in range(0, rw, 4):
        rect(canvas, x + rx + i, y + ry + rh - 2, 2, 1, stripe)


def frame_ring(canvas: Canvas, x: int, y: int, w: int, h: int) -> None:
    """A white ring 2 pixels thick just outside a flat rectangle."""
    rect(canvas, x - 2, y - 2, w + 4, 2, WHITE)
    rect(canvas, x - 2, y + h, w + 4, 2, WHITE)
    rect(canvas, x - 2, y, 2, h, WHITE)
    rect(canvas, x + w, y, 2, h, WHITE)


def draw_roller_selection(canvas: Canvas, panel) -> None:
    """The ring around the warehouse's back roller door, which is flat."""
    rx, ry, rw, rh = ROLLER
    frame_ring(canvas, panel.x + rx, panel.y + ry, rw, rh)


def draw_door_selection(canvas: Canvas, panel) -> None:
    """The ring around an office door, following the wall's slope and the mirror, 2 pixels thick."""
    dx, dy, dw, dh = DOOR
    col = BAY_W - dx - dw if panel.mirror else dx
    for c in range(col - 2, col + dw + 2):
        top = panel.y + panel.shift(c) + dy
        inside = col <= c < col + dw
        rows = (top - 2, top - 1, top + dh, top + dh + 1) if inside else range(top - 2, top + dh + 2)
        for r in rows:
            canvas.put(panel.x + c, r, WHITE)


def _iso_box(canvas: Canvas, bx: int, by: int, w: int, d: int, h: int, color: Color) -> tuple:
    """A 2:1 box standing on (bx, by), its bottom back vertex; lit top, mid left face, dark right face, outlined."""
    from .props import fill_poly
    ty = by - h
    back, right, left = (bx, ty), (bx + 2 * w, ty + w), (bx - 2 * d, ty + d)
    front = (bx + 2 * w - 2 * d, ty + w + d)
    fill_poly(canvas, [left, front, (front[0], front[1] + h), (left[0], left[1] + h)], shade(color, 0.86))
    fill_poly(canvas, [front, right, (right[0], right[1] + h), (front[0], front[1] + h)], shade(color, 0.66))
    fill_poly(canvas, [back, right, front, left], shade(color, 1.1))
    for t in range(1, 2 * d - 1):  # bright rim on the top's front-left edge.
        canvas.put(left[0] + t, left[1] + t // 2, shade(color, 1.25))
    return back, right, front, left


def draw_table(canvas: Canvas, x: int, y: int, tick: int, selected: bool) -> None:
    """The central counter in 2:1 isometry: red parcel to the warehouse, coffee machine with a green led, plant and
    water cooler, all shaded with a lit top, a mid left face and a dark right face."""
    from .props import _shade_area
    _shade_area(canvas, [(x + 4, y + 30), (x + 34, y + 36), (x + 58, y + 26), (x + 30, y + 18)], 0.8)  # floor shadow
    cooler = (232, 236, 244)
    _iso_box(canvas, x + 52, y + 26, 3, 3, 14, cooler)  # cooler body, behind the counter's right end.
    _iso_box(canvas, x + 52, y + 12, 3, 3, 8, (150, 214, 248))  # bottle
    level = 1 + (tick // 90) % 5
    for t in range(level):
        canvas.put(x + 51, y + 9 - t, (205, 236, 252))
        canvas.put(x + 52, y + 9 - t, (205, 236, 252))
    canvas.put(x + 48, y + 21, (90, 150, 230))
    canvas.put(x + 50, y + 22, (235, 90, 90))
    _iso_box(canvas, x + 22, y + 13, 14, 8, 7, (196, 150, 108))  # counter
    parcel = (240, 90, 90) if not selected else (255, 130, 110)
    back, right, front, left = _iso_box(canvas, x + 16, y + 13, 3, 3, 6, parcel)
    for t in range(0, 6):  # ribbon across the parcel's top.
        canvas.put(left[0] + 3 + t, left[1] - 1 + t // 2, (250, 214, 150))
    back, right, front, left = _iso_box(canvas, x + 28, y + 12, 3, 3, 11, (72, 76, 96))  # coffee machine
    for t in range(4):
        canvas.put(left[0] + 1 + t, left[1] + 3 + t // 2, (120, 220, 200))  # screen on the lit face
    led = (90, 240, 130) if (tick // 6) % 2 else (40, 110, 70)
    canvas.put(front[0] + 2, front[1] + 2, led)
    canvas.put(left[0] + 2, left[1] + 7, (250, 250, 250))  # cup slot
    canvas.put(left[0] + 3, left[1] + 8, (250, 250, 250))
    _iso_box(canvas, x + 40, y + 17, 3, 3, 4, (200, 130, 90))  # plant pot
    for dx, dy in ((-3, -3), (0, -6), (4, -5), (7, -3), (2, -3)):
        rect(canvas, x + 37 + dx, y + 13 + dy, 4, 3, (92, 186, 118))
        canvas.put(x + 37 + dx, y + 13 + dy, (140, 220, 150))
        canvas.put(x + 40 + dx, y + 15 + dy, (60, 140, 90))


def draw_side_walls(canvas: Canvas, plan) -> None:
    """Back wall of the wide plan: flat behind the table, with diagonal walls falling to both view edges."""
    flat, void, edge_tone = (168, 186, 216), (38, 42, 58), (120, 128, 150)
    left, right = plan.wall_start(), canvas.width - 1 - plan.wall_start()
    for x in range(canvas.width):
        edge = min(plan.floor_edge(x), canvas.height)
        top = max(0, edge - (BAY_H + 4))
        tone = shade(flat, 0.92) if x < left else shade(flat, 1.06) if x > right else flat
        rect(canvas, x, 0, 1, top, void)
        rect(canvas, x, top, 1, max(0, edge - 3 - top), tone)
        rect(canvas, x, max(top, edge - 3), 1, min(3, edge - top), shade(tone, 0.8))
        canvas.put(x, edge, OUTLINE)
        canvas.put(x, edge + 1, edge_tone)
    for x in (left, right):
        edge = min(plan.floor_edge(x), canvas.height)
        rect(canvas, x, max(0, edge - (BAY_H + 4)), 1, edge - max(0, edge - (BAY_H + 4)), OUTLINE)
    draw_partitions(canvas, plan)


def draw_partitions(canvas: Canvas, plan) -> None:
    """First pass: partition walls behind every free-standing lower office, under all panels."""
    for panel in plan.panels:
        if panel.free:
            draw_partition(canvas, panel)


def column_start(painted, x: int) -> int:
    """First row a partition may paint in column x: below the window of every painted panel covering that column."""
    start = 0
    for other in painted:
        if other.x <= x < other.x + BAY_W:
            start = max(start, other.y + other.shift(x - other.x) + WINDOW[1] + WINDOW[3] + 1)
    return start


def draw_partition(canvas: Canvas, panel, painted=()) -> None:
    """Partition wall behind one free-standing lower office, closing the gap between it and the back wall.

    Rows at or above the window of a panel in `painted` are left alone, so the partition stays in front
    of earlier panels without ever covering a window.
    """
    from .hallplan import SLOPE  # local import: hallplan imports this module.
    wall = (168, 186, 216)
    inner = panel.x if panel.slope > 0 else panel.x + BAY_W - 1
    top_y = panel.y - CAP
    step = 1 if panel.slope > 0 else -1
    edge = canvas.width - 1 if step > 0 else 0
    tone = shade(wall, 0.82 if step > 0 else 0.98)
    previous = None
    for x in range(inner, edge + step, step):
        dx = abs(x - inner)
        drop = dx // SLOPE
        top = top_y - drop
        bottom = top_y + drop + 1
        start = column_start(painted, x)
        for y in range(max(0, top, start), bottom + 1):
            canvas.put(x, y, tone)
        if top >= start:
            canvas.put(x, top, OUTLINE)
        if drop != previous:
            if top + 1 >= start:
                canvas.put(x, top + 1, OUTLINE)
            previous = drop


def draw_free_office_frame(canvas: Canvas, panel, wall: Color) -> None:
    """The roof strip and the bottom edge of a free-standing office, so it reads as a solid object."""
    for col in range(BAY_W):
        y0 = panel.y + panel.shift(col)
        rect(canvas, panel.x + col, y0 - CAP, 1, CAP, shade(wall, 1.08))
        canvas.put(panel.x + col, y0 - CAP, OUTLINE)
        canvas.put(panel.x + col, y0 + BAY_H, OUTLINE)


def draw_warehouse_floor(canvas: Canvas) -> None:
    light, dark = (136, 142, 152), (124, 130, 140)
    for y in range(canvas.height):
        for x in range(canvas.width):
            canvas.rows[y][x] = light if ((x + 2 * y) // 36 + (2 * y - x) // 36) % 2 == 0 else dark
    for x in range(canvas.width):
        if (x // 6) % 2 == 0:
            rect(canvas, x, canvas.height - 4, 1, 2, (240, 196, 60))


def draw_crates(canvas: Canvas, x: int, y: int, seed: int) -> None:
    """A pallet with stacked crates, filling a free spot of the warehouse."""
    wood, light = (186, 142, 92), (214, 174, 122)
    rect(canvas, x + 4, y + BAY_H - 2, BAY_W - 8, 2, (98, 74, 52))
    for row in range(2 + seed % 2):
        for col in range(3 - row):
            cx, cy = x + 7 + col * 15 + row * 7, y + BAY_H - 15 - row * 13
            box(canvas, cx, cy, 14, 13, wood)
            rect(canvas, cx + 1, cy + 6, 12, 1, light)
            rect(canvas, cx + 6, cy + 1, 1, 11, light)
