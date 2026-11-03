"""Art of the hall and the warehouse: office fronts with glass, the roller door, the break corner and the crates."""
from .props import OUTLINE, fill_poly
from .sprites import Canvas, Color

BAY_W, BAY_H, DEPTH = 58, 34, 6
PADDING = 8  # spare interior rows, so an angled window never reads outside the room.
DOOR = (3, 7, 14, BAY_H - 8)  # column, row, width, height inside the front wall.
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
        fill_poly(canvas, [(x, y), (x + DEPTH, y - DEPTH), (x + BAY_W + DEPTH - 1, y - DEPTH), (x + BAY_W - 1, y)], shade(wall, 1.08))
        fill_poly(canvas, [(x + BAY_W - 1, y), (x + BAY_W + DEPTH - 1, y - DEPTH), (x + BAY_W + DEPTH - 1, y + BAY_H - DEPTH - 1), (x + BAY_W - 1, y + BAY_H - 1)], shade(wall, 0.72))
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
    rx, ry, rw, rh = 6, 6, BAY_W - 12, BAY_H - 7
    box(canvas, x + rx, y + ry, rw, rh, (128, 138, 156) if not back else WOOD)
    for j in range(2, rh - 1, 3):
        rect(canvas, x + rx + 1, y + ry + j, rw - 2, 1, (98, 106, 124) if not back else WOOD_D)
    stripe = (250, 200, 60)
    for i in range(0, rw, 4):
        rect(canvas, x + rx + i, y + ry + rh - 2, 2, 1, stripe)


def draw_table(canvas: Canvas, x: int, y: int, tick: int, selected: bool) -> None:
    """The central table: red parcel to the warehouse, coffee machine with a green led, plant and water cooler."""
    box(canvas, x + 2, y + 17, 42, 18, (196, 150, 108))
    box(canvas, x, y + 14, 46, 4, (234, 226, 214))
    parcel = (240, 90, 90) if not selected else (255, 130, 110)
    box(canvas, x + 2, y + 7, 10, 8, parcel)
    rect(canvas, x + 6, y + 8, 2, 6, (250, 214, 150))
    box(canvas, x + 15, y + 2, 13, 13, (72, 76, 96))
    box(canvas, x + 17, y + 4, 7, 3, (120, 220, 200))
    box(canvas, x + 18, y + 9, 5, 4, (250, 250, 250))
    led = (90, 240, 130) if (tick // 6) % 2 else (40, 110, 70)
    rect(canvas, x + 25, y + 4, 2, 2, led)
    box(canvas, x + 32, y + 8, 8, 7, (200, 130, 90))
    for dx, dy in ((-3, -3), (0, -6), (4, -5), (7, -3), (2, -3)):
        rect(canvas, x + 34 + dx, y + 8 + dy, 4, 3, (92, 186, 118))
    box(canvas, x + 48, y + 21, 11, 14, (232, 236, 244))
    box(canvas, x + 49, y + 7, 9, 15, (150, 214, 248))
    rect(canvas, x + 50, y + 8, 7, 7 + (tick // 90) % 5, (205, 236, 252))
    rect(canvas, x + 50, y + 26, 3, 2, (90, 150, 230))
    rect(canvas, x + 55, y + 26, 3, 2, (235, 90, 90))


def draw_side_walls(canvas: Canvas, plan) -> None:
    """Back wall with chamfers and the two side walls, for the wide floor plan."""
    tone, edge_tone = (168, 186, 216), (120, 128, 150)
    for x in range(canvas.width):
        edge = min(plan.floor_edge(x), canvas.height)
        rect(canvas, x, 0, 1, edge, tone if x < canvas.width // 2 else shade(tone, 1.06))
        canvas.put(x, edge, OUTLINE)
        canvas.put(x, edge + 1, edge_tone)
    for y in range(canvas.height):
        for x in (plan.side_wall, canvas.width - 1 - plan.side_wall):
            canvas.put(x, y, OUTLINE)


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
