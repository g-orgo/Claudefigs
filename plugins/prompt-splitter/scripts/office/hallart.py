"""Art of the hall and the warehouse: office fronts with glass, the roller door, the break corner and the crates."""
from .props import OUTLINE, fill_poly
from .sprites import Canvas, Color

BAY_W, BAY_H, DEPTH = 58, 34, 6
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


def draw_shell(canvas: Canvas, x: int, y: int, wall: Color) -> None:
    """The box of one office seen from outside: roof edge, right side and front wall."""
    fill_poly(canvas, [(x, y), (x + DEPTH, y - DEPTH), (x + BAY_W + DEPTH - 1, y - DEPTH), (x + BAY_W - 1, y)], shade(wall, 1.08))
    fill_poly(canvas, [(x + BAY_W - 1, y), (x + BAY_W + DEPTH - 1, y - DEPTH), (x + BAY_W + DEPTH - 1, y + BAY_H - DEPTH - 1), (x + BAY_W - 1, y + BAY_H - 1)], shade(wall, 0.72))
    box(canvas, x, y, BAY_W, BAY_H, wall)
    rect(canvas, x + 1, y + BAY_H - 3, BAY_W - 2, 2, shade(wall, 0.62))


def draw_office_front(canvas: Canvas, x: int, y: int, wall: Color) -> None:
    draw_shell(canvas, x, y, wall)
    dx, dy, dw, dh = DOOR
    box(canvas, x + dx, y + dy, dw, dh, WOOD)
    box(canvas, x + dx + 3, y + dy + 3, dw - 6, 8, GLASS)
    rect(canvas, x + dx + 3, y + dy + 14, dw - 6, 1, WOOD_D)
    rect(canvas, x + dx + dw - 3, y + dy + 13, 2, 2, (250, 220, 120))
    wx, wy, ww, wh = WINDOW
    box(canvas, x + wx - 1, y + wy - 1, ww + 2, wh + 2, INSIDE)


def draw_glass(canvas: Canvas, x: int, y: int, inside: Canvas, tick: int) -> None:
    """Copies the room's interior into the window through tinted glass with a slow moving shine."""
    wx, wy, ww, wh = WINDOW
    shine = tick // 3
    for j in range(wh):
        for i in range(ww):
            r, g, b = inside.rows[j][i]
            mix = 0.84 if (i + j - shine) % 34 > 3 else 0.62
            canvas.put(x + wx + i, y + wy + j, (int(r * mix + GLASS[0] * (1 - mix)), int(g * mix + GLASS[1] * (1 - mix)), int(b * mix + GLASS[2] * (1 - mix))))
    rect(canvas, x + wx + ww // 2, y + wy, 1, wh, OUTLINE)


def new_interior() -> Canvas:
    inside = Canvas(WINDOW[2], WINDOW[3], INSIDE)
    rect(inside, 0, WINDOW[3] - 6, WINDOW[2], 6, INSIDE_FLOOR)
    return inside


def draw_desk_edge(inside: Canvas) -> None:
    """The desks seen through the glass, hiding the characters' lower bodies."""
    rect(inside, 0, WINDOW[3] - 5, WINDOW[2], 1, OUTLINE)
    rect(inside, 0, WINDOW[3] - 4, WINDOW[2], 3, (226, 184, 136))
    rect(inside, 0, WINDOW[3] - 1, WINDOW[2], 1, OUTLINE)


def draw_lamp(canvas: Canvas, x: int, y: int, status: str, tick: int) -> None:
    color = LAMPS[status]
    if status == "wait" and (tick // 6) % 2:
        color = shade(color, 0.6)
    box(canvas, x + DOOR[0] + 5, y + 2, 4, 4, color)


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


def draw_break_corner(canvas: Canvas, x: int, y: int, tick: int) -> None:
    """Counter with a coffee machine, a water cooler and a plant."""
    rect(canvas, x + 2, y + BAY_H + 2, BAY_W - 4, 1, (120, 128, 150))
    box(canvas, x + 2, y + 14, 30, 19, (196, 150, 108))
    box(canvas, x, y + 11, 34, 4, (234, 226, 214))
    box(canvas, x + 6, y, 13, 12, (72, 76, 96))
    box(canvas, x + 9, y + 3, 7, 3, (120, 220, 200))
    box(canvas, x + 10, y + 8, 5, 3, (250, 250, 250))
    if (tick // 4) % 2:
        rect(canvas, x + 12, y + 5, 1, 2, (250, 250, 250))
    box(canvas, x + 38, y + 19, 11, 14, (232, 236, 244))
    box(canvas, x + 39, y + 5, 9, 15, (150, 214, 248))
    level = 7 + (tick // 90) % 5
    rect(canvas, x + 40, y + 6, 7, level, (205, 236, 252))
    rect(canvas, x + 40, y + 24, 3, 2, (90, 150, 230))
    rect(canvas, x + 45, y + 24, 3, 2, (235, 90, 90))
    box(canvas, x + 22, y + 4, 8, 7, (200, 130, 90))
    for dx, dy in ((-3, -3), (0, -6), (4, -5), (7, -3), (2, -3)):
        rect(canvas, x + 24 + dx, y + 4 + dy, 4, 3, (92, 186, 118))


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
