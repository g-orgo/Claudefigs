"""Prototype of the isometric 16-bit station: shaded iso desk, chair, monitor and a seated 3/4 character."""
import sys

sys.path.insert(0, "/var/home/Orgo/.claude/local-plugins/plugins/prompt-splitter/scripts")
from office.sprites import Canvas, rgb  # noqa: E402

OUT = (40, 30, 52)


def shade(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c)


def ramp(c):
    """highlight, base, shade, deep shade."""
    return shade(c, 1.15), c, shade(c, 0.8), shade(c, 0.6)


def poly(cv, pts, color):
    ys = [p[1] for p in pts]
    for y in range(min(ys), max(ys) + 1):
        xs = []
        n = len(pts)
        for i in range(n):
            (x1, y1), (x2, y2) = pts[i], pts[(i + 1) % n]
            if y1 == y2:
                continue
            if min(y1, y2) <= y < max(y1, y2) or (y == max(ys) and max(y1, y2) == y):
                xs.append(x1 + (y - y1) * (x2 - x1) / (y2 - y1))
        xs.sort()
        for i in range(0, len(xs) - 1, 2):
            for x in range(round(xs[i]), round(xs[i + 1]) + 1):
                cv.put(x, y, color)


def line(cv, a, b, color):
    (x1, y1), (x2, y2) = a, b
    steps = max(abs(x2 - x1), abs(y2 - y1), 1)
    for i in range(steps + 1):
        cv.put(round(x1 + (x2 - x1) * i / steps), round(y1 + (y2 - y1) * i / steps), color)


def iso_box(cv, x, y, w, d, h, top, left, right):
    """Box with its top's back vertex at (x, y): w along the down-right axis, d along the down-left axis (2:1)."""
    back = (x, y)
    r = (x + 2 * w, y + w)
    l = (x - 2 * d, y + d)
    f = (x + 2 * w - 2 * d, y + w + d)
    poly(cv, [l, f, (f[0], f[1] + h), (l[0], l[1] + h)], left)
    poly(cv, [f, r, (r[0], r[1] + h), (f[0], f[1] + h)], right)
    poly(cv, [back, r, f, l], top)
    return back, r, f, l


def outline_box(cv, corners, h):
    back, r, f, l = corners
    for a, b in ((back, r), (r, (r[0], r[1] + h)), ((r[0], r[1] + h), (f[0], f[1] + h)), ((f[0], f[1] + h), (l[0], l[1] + h)),
                 ((l[0], l[1] + h), l), (l, back)):
        line(cv, a, b, OUT)


def desk(cv, x, y, wood):
    hi, base, sh, deep = ramp(wood)
    w, d, h = 14, 8, 3
    c = iso_box(cv, x, y, w, d, h, base, sh, deep)
    back, r, f, l = c
    line(cv, (l[0] + 1, l[1]), (f[0], f[1] - 0), hi)  # lit front edge of the top
    line(cv, (f[0], f[1]), (r[0] - 1, r[1]), shade(base, 0.92))
    for i in range(3, 2 * w - 2, 7):  # wood grain
        line(cv, (back[0] + i - 2, back[1] + i // 2 + 3), (back[0] + i + 4, back[1] + i // 2 + 6), shade(base, 0.93))
    outline_box(cv, c, h)
    line(cv, f, (f[0], f[1] + h), shade(deep, 0.85))
    legs = [(l[0] + 1, l[1] + h + 1), (f[0], f[1] + h + 1), (r[0] - 1, r[1] + h + 1)]
    for lx, ly in legs:
        for k in range(7):
            cv.put(lx, ly + k, (70, 74, 96))
            cv.put(lx + 1, ly + k, (120, 128, 150) if k < 6 else (70, 74, 96))
        cv.put(lx - 1, ly + 6, OUT)
        cv.put(lx + 2, ly + 6, OUT)
    return c


def floor_shadow(cv, cx, cy, rx, ry, f=0.78):
    for yy in range(-ry, ry + 1):
        for xx in range(-rx, rx + 1):
            if (xx / rx) ** 2 + (yy / ry) ** 2 <= 1:
                X, Y = cx + xx, cy + yy
                if 0 <= X < cv.width and 0 <= Y < cv.height:
                    cv.rows[Y][X] = shade(cv.rows[Y][X], f)


def chair(cv, x, y, col):
    hi, base, sh, deep = ramp(col)
    c = iso_box(cv, x, y, 5, 5, 2, base, sh, deep)  # seat
    outline_box(cv, c, 2)
    back = c[0]
    poly(cv, [(back[0] - 1, back[1] - 15), (back[0] + 10, back[1] - 10), (back[0] + 10, back[1] + 4), (back[0] - 1, back[1] - 1)], sh)
    poly(cv, [(back[0], back[1] - 14), (back[0] + 3, back[1] - 12), (back[0] + 3, back[1] - 2), (back[0], back[1] - 4)], hi)
    line(cv, (back[0] - 1, back[1] - 15), (back[0] + 10, back[1] - 10), OUT)
    line(cv, (back[0] + 10, back[1] - 10), (back[0] + 10, back[1] + 4), OUT)
    line(cv, (back[0] - 1, back[1] - 15), (back[0] - 1, back[1] - 1), OUT)


# Seated character, 3/4 view facing down-left. Letters map to the palette in pal().
HEAD = [
    ".....ooooooo......",
    "...oolhhhhhhoo....",
    "..olhhhhhhhhhHo...",
    ".olhhhhhhhhhhhHo..",
    ".ohhhhhhhhhhhhHHo.",
    "ohhhhhhhhhhhhhhHo.",
    "ohhhHhhhhhHHhhhHo.",
    "ohhHssHhhHsssHhHHo",
    "ohHsssssssssssHhHo",
    "ohssseeksssseekHHo",
    "oHsssweesssswesSHo",
    ".osssweessssweSSo.",
    ".oscccsssssccSSSo.",
    "..ossssssmssssSo..",
    "...oSsssssssSSo...",
    "....ooSSSSSSoo....",
    "......oSSSo.......",
]
BODY = [
    ".....ootaaatoo....",
    "...oouttaatttTo...",
    "..ouutttaatttTTo..",
    "..outtttaatttTTTo.",
    ".osoutttaatttTToSo",
    ".osSottttttttTosSo",
    "..oo.otttttTTo.oo.",
]


def pal(look):
    s, h = rgb(look.skin), rgb(look.hair)
    t, a = rgb(look.top), rgb(look.accent)
    return {"o": OUT, "s": s, "S": shade(s, 0.82), "h": h, "H": shade(h, 0.72), "l": rgb(look.hair_hi),
            "e": (44, 36, 60), "w": (250, 250, 255), "k": (120, 150, 220), "c": (246, 150, 150), "m": (170, 70, 80),
            "t": t, "T": rgb(look.top_sh), "u": shade(t, 1.12), "a": a}


def stamp(cv, x, y, rows, p):
    for j, row in enumerate(rows):
        for i, ch in enumerate(row):
            if ch != ".":
                cv.put(x + i, y + j, p[ch])


def monitor(cv, x, y, screen_bg, lines):
    # screen faces down-right: a parallelogram whose top edge rises 1 px per 2 px.
    w, h = 14, 11
    case = (84, 90, 112)
    hi, base, sh, deep = ramp(case)
    face = [(x, y + 7), (x + w, y), (x + w, y + h), (x, y + 7 + h)]
    side = [(x - 3, y + 6 + 0), (x, y + 7), (x, y + 7 + h), (x - 3, y + 6 + h)]
    poly(cv, side, sh)
    poly(cv, face, base)
    inner = [(x + 2, y + 7), (x + w - 2, y + 2), (x + w - 2, y + h - 2), (x + 2, y + 5 + h)]
    poly(cv, inner, screen_bg)
    for k, col in enumerate(lines):
        line(cv, (x + 3, y + 9 + 2 * k - 0), (x + 3 + 4 + (k * 3) % 5, y + 7 + 2 * k - (4 + (k * 3) % 5) // 2), col)
    line(cv, (x + 3, y + 6), (x + w - 3, y + 1 + 1), shade(screen_bg, 1.6))
    for a, b in ((face[0], face[1]), (face[1], face[2]), (face[2], face[3]), (side[0], face[0]), (side[0], side[3]), (side[3], face[3])):
        line(cv, a, b, OUT)
    base_y = y + 7 + h + 1
    poly(cv, [(x + 6, base_y - 3), (x + 9, base_y - 4), (x + 9, base_y), (x + 6, base_y + 1)], deep)
    c = iso_box(cv, x + 9, base_y, 2, 2, 1, hi, sh, deep)
    outline_box(cv, c, 1)


def station(cv, x, y, look, wood, chair_col):
    floor_shadow(cv, x + 6, y + 27, 26, 8)
    chair(cv, x + 17, y + 2, chair_col)
    p = pal(look)
    stamp(cv, x + 7, y - 18, HEAD, p)
    stamp(cv, x + 7, y - 1, BODY, p)
    desk(cv, x, y, wood)
    monitor(cv, x - 9, y - 9, (32, 36, 60), [(120, 220, 160), (250, 200, 110), (140, 190, 255), (235, 130, 160)])
    # keyboard and hands
    kb = iso_box(cv, x + 6, y + 9, 5, 2, 1, (226, 230, 240), (150, 156, 176), (120, 126, 146))
    outline_box(cv, kb, 1)
    cv.put(x + 8, y + 9, p["s"]); cv.put(x + 9, y + 9, p["S"]); cv.put(x + 15, y + 11, p["s"]); cv.put(x + 16, y + 11, p["S"])
    mug = iso_box(cv, x + 22, y + 11, 2, 2, 4, (250, 250, 250), (220, 90, 90), (170, 60, 60))
    outline_box(cv, mug, 4)


if __name__ == "__main__":
    from office.props import tile_color, ROOM_TILE_PERIOD
    from office.sprites import LOOKS
    from PIL import Image

    W, H = 200, 70
    cv = Canvas(W, H)
    light, dark, grout = (236, 222, 196), (226, 210, 180), (210, 194, 164)
    for yy in range(H):
        for xx in range(W):
            cv.rows[yy][xx] = tile_color(xx, yy, light, dark, grout, ROOM_TILE_PERIOD)
    woods = [(232, 190, 140), (168, 108, 70), (62, 66, 84), (244, 240, 232)]
    chairs = [(98, 112, 160), (150, 74, 60), (232, 70, 110), (120, 200, 190)]
    for i in range(4):
        station(cv, 30 + i * 46, 30, LOOKS[i % len(LOOKS)], woods[i], chairs[i])
    img = Image.new("RGB", (W, H))
    img.putdata([c for row in cv.rows for c in row])
    img.resize((W * 8, H * 8), Image.NEAREST).save(sys.argv[1])
