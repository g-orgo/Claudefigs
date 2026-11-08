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
    fill_poly(canvas, [d, c, (c[0], c[1] + 1), (d[0], d[1] + 1)], kit.key_gap)
    fill_poly(canvas, [a, b, c, d], kit.keys)
    for lane in (0, 1, 2):
        for t in range(1, 9):
            px, py = a[0] + t - 2 * lane - 1, a[1] + t // 2 + lane + 1
            color = kit.key_cap if (t + lane) % 2 else kit.key_gap
            if kit.rgb and (t + lane) % 2:
                color = RAINBOW[(t + lane + tick // 3) % len(RAINBOW)]
            canvas.put(px, py, color)


def draw_items(canvas: Canvas, x: int, y: int, kit: Kit, seed: int, tick: int) -> None:
    """Everything on the desk's top but the monitor."""
    near, far, note = kit.items
    draw_keyboard(canvas, x, y, kit, tick)
    draw_item(canvas, x + NEAR_SLOT[0], y + NEAR_SLOT[1], near[seed % len(near)])
    draw_item(canvas, x + FAR_SLOT[0], y + FAR_SLOT[1], far)
    if note:
        draw_item(canvas, x + NOTE_SLOT[0], y + NOTE_SLOT[1], note)
