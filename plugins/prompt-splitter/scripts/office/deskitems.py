"""Small objects on top of an office desk: keyboard, mouse and the decor of each furniture kit."""
from .props import OUTLINE, Kit, fill_poly
from .sprites import Canvas, Color, _Layer

PALETTE: dict[str, Color] = {
    "o": OUTLINE, "w": (255, 255, 255), "W": (226, 230, 240), "g": (170, 175, 195), "G": (112, 118, 140),
    "r": (232, 84, 84), "R": (164, 44, 58), "b": (84, 140, 232), "B": (48, 82, 164), "y": (252, 214, 96), "Y": (208, 154, 56),
    "n": (104, 200, 110), "N": (48, 134, 84), "t": (214, 124, 84), "T": (156, 80, 58), "c": (108, 66, 44),
    "p": (246, 150, 190), "P": (204, 90, 140), "m": (120, 232, 240), "M": (60, 150, 170), "k": (60, 62, 80), "K": (34, 36, 50),
    "s": (96, 186, 240), "l": (70, 150, 110), "L": (40, 96, 72), "a": (232, 192, 96), "A": (160, 118, 52),
}

# Rows of each object; the last row sits on the anchor point of its slot.
ITEMS = {
    "mug": ["..w.w...", ".w.w....", ".ooooo..", "occcccoo", "owrrrRo.o", "orrrrRoo.", "orrrrRo..", ".ooooo..."],
    "papers": ["...oooo.", ".ooWWWWo", "oWWwwwwo", "oWggwwwo", "owwwggo.", ".oowwo..", "...oo..."],
    "plant": ["..n..n..", ".nnonNn.", "onNnNnno", ".nnNnNo.", "onNnnNno", ".ooNnoo.", ".ottttTo", ".oytttTo", "..ottTo.", "...ooo.."],
    "note_yellow": [".ooo.", "oyyyo", "oYyyo", ".ooo."],
    "note_pink": [".ooo.", "opppo", "oPppo", ".ooo."],
    "floppies": ["...ooooo", ".oobbbbo", "obbbwwBo", "obbwwBoo", "orrrrRo.", "orwwRoo.", ".oooo..."],
    "banker": ["...oooo..", "..olllLo.", ".olllllLo", "ollllLLLo", "oooyyyooo", "....oAo..", "....oAo..", "...oaaAo.", "...ooooo."],
    "soda": ["..ooo.", ".oggGo", ".orrRo", ".owrRo", ".orwRo", ".orrRo", ".oggGo", "..ooo."],
    "headset": ["..oooo..", ".okkkKo.", "okoooKKo", "omo.oKmo", "omo.oKmo", "ooo.oooo", "...oGo..", "..oGGGo.", "..ooooo."],
    "pencils": [".y..r.b.", ".Yo.Ro.B", ".oyoRoBo", "oppppppo", "opwpppPo", "opppppPo", "oppppPPo", ".oooooo."],
    "sketch": ["...oooo.", ".oowwwwo", "owwwbbwo", "owbbwwpo", "owwwppo.", ".oowwo..", "...oo..."],
    "cactus": ["..oo...", ".onno.o", "oonNoono", "onnNonNo", "onnNnNo.", ".onNoo..", ".onNo...", "ottttTo.", "oyttTTo.", ".oooo..."],
    "books": [".oooooo.", "orrrrrRo", "oooooooo", "obwbbbBo", "oooooooo", "onnnnnNo", ".oooooo."],
    "inkwell": ["..w...", "..wo..", "..oo..", ".oBBo.", "obbbBo", "obbBBo", ".oooo."],
    "globe": ["..ooo..", ".obnbbo", "onnbbbo", "obnnbBo", "obbbnBo", ".oBBBo.", "..oao..", ".oaaAo.", ".ooooo."],
}
NEAR_SLOT = (13, 13)  # bottom-left anchor of the object beside the keyboard, relative to the desk corner.
FAR_SLOT = (33, 15)  # the far corner, on the character's right.
NOTE_SLOT = (22, 17)  # flat note in front of the keyboard.
RAINBOW = [(255, 90, 110), (255, 170, 70), (250, 230, 90), (110, 230, 120), (90, 200, 250), (170, 120, 250)]


def draw_item(canvas: Canvas, x: int, y: int, name: str) -> None:
    rows = ITEMS[name]
    layer = _Layer()  # same top-left light as the characters, so the decor gets volume too.
    for j, row in enumerate(rows):
        for i, ch in enumerate(row):
            if ch != ".":
                layer.put(x + i, y - len(rows) + 1 + j, PALETTE[ch])
    layer.flush(canvas)


def draw_keyboard(canvas: Canvas, x: int, y: int, kit: Kit, tick: int) -> None:
    """Keyboard along the desk's axis: thick body, two rows of keys and, on the gaming kit, cycling lights."""
    a, b, c, d = (x + 26, y + 9), (x + 35, y + 13), (x + 29, y + 16), (x + 20, y + 12)
    if kit.mat:
        fill_poly(canvas, [(a[0], a[1] - 2), (b[0] + 2, b[1] - 1), (c[0], c[1] + 2), (d[0] - 2, d[1])], kit.mat)
    gap = tuple(int(v * 0.72) for v in kit.key_gap)  # dark enough that light keyboards never read as a sheet.
    fill_poly(canvas, [d, c, (c[0], c[1] + 1), (d[0], d[1] + 1)], gap)  # front face.
    fill_poly(canvas, [a, b, c, d], tuple(int(v * 0.85) for v in gap))  # dark body, so the light keys stand out.
    for lane in (0, 1, 2):
        for t in range(1, 9):
            px, py = a[0] + t - 2 * lane - 1, a[1] + t // 2 + lane + 1
            # Keys two pixels wide with a dark gap between them; the front lane's middle is the space bar.
            is_key = (t + lane) % 3 != 0 or (lane == 2 and 3 <= t <= 6)
            color = kit.key_cap if is_key else gap
            if kit.rgb and is_key:
                color = RAINBOW[(t + lane + tick // 3) % len(RAINBOW)]
            canvas.put(px, py, color)


def draw_items(canvas: Canvas, x: int, y: int, kit: Kit, seed: int, tick: int) -> None:
    """Keyboard and the two decor objects on the desk top (the monitor is drawn apart)."""
    near, far, _note = kit.items  # the flat note is not drawn: no free spot on the top, and over the keyboard
    # it read as a stray sheet of paper.
    draw_keyboard(canvas, x, y, kit, tick)
    for name, (dx, dy) in ((near[seed % len(near)], NEAR_SLOT), (far, FAR_SLOT)):
        _contact_shadow(canvas, x + dx, y + dy, name, kit)
        draw_item(canvas, x + dx, y + dy, name)


def _contact_shadow(canvas: Canvas, x: int, y: int, name: str, kit: Kit) -> None:
    """1 px of the desk top's dark tone under an object's base, so it rests on the desk instead of floating."""
    base = ITEMS[name][-1]
    shadow = tuple(int(v * 0.62) for v in kit.top)
    for i, ch in enumerate(base):
        if ch != ".":
            canvas.put(x + i, y + 1, shadow)
