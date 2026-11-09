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

# Rows of each object; the last row sits on the base of its slot.
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

# The desk top is a 2:1 parallelogram. A point (u, v) in 0..1 on it sits at
# (x + 28u + 12v, y + 6 + 14u - 6v) from the desk origin: u runs along the long front edge,
# v runs across the desk, (0, 0) is the front corner and (1, 1) the rear one.
KEYBOARD_UV = (0.52, 0.84, 0.30, 0.82)  # u0, u1, v0, v1 of the keyboard body, inside the top
NEAR_UV = (0.36, 0.25)  # base centre of the object beside the keyboard, left of it
FAR_UV = (0.92, 0.80)  # base centre of the far corner, on the character's right
NOTE_UV = (0.68, 0.14)  # base centre of the flat note in front of the keyboard
RAINBOW = [(255, 90, 110), (255, 170, 70), (250, 230, 90), (110, 230, 120), (90, 200, 250), (170, 120, 250)]


def desk_px(x: int, y: int, u: float, v: float) -> tuple[int, int]:
    """Pixel of a point of the desk top, given in its 2:1 (u, v) coordinates."""
    return x + round(28 * u + 12 * v), y + round(6 + 14 * u - 6 * v)


NEAR_SLOT = desk_px(0, 0, *NEAR_UV)  # kept as pixel anchors for callers that place items by hand
FAR_SLOT = desk_px(0, 0, *FAR_UV)
NOTE_SLOT = desk_px(0, 0, *NOTE_UV)


def _dark(color: Color, factor: float) -> Color:
    return tuple(int(c * factor) for c in color)


def draw_item(canvas: Canvas, x: int, y: int, name: str) -> None:
    """Draws an object whose bottom-left pixel is (x, y); its last row is the base."""
    rows = ITEMS[name]
    layer = _Layer()  # same top-left light as the characters, so the decor gets volume too.
    for j, row in enumerate(rows):
        for i, ch in enumerate(row):
            if ch != ".":
                layer.put(x + i, y - len(rows) + 1 + j, PALETTE[ch])
    layer.flush(canvas)


def _place_item(canvas: Canvas, x: int, y: int, kit: Kit, name: str, uv: tuple[float, float]) -> None:
    """Puts an object so its base centre sits on uv, with a 1 px contact shadow under the base."""
    rows = ITEMS[name]
    cols = [i for i, ch in enumerate(rows[-1]) if ch != "."]
    px, py = desk_px(x, y, *uv)
    left = px - round(sum(cols) / len(cols))
    shadow = _dark(kit.top, 0.62)  # dark tone of the desk top, under the base only.
    for i in cols:
        canvas.put(left + i, py + 1, shadow)
    draw_item(canvas, left, py, name)


def draw_keyboard(canvas: Canvas, x: int, y: int, kit: Kit, tick: int) -> None:
    """Keyboard lying on the desk top: an iso block with a front face, three rows of keys and a space bar."""
    u0, u1, v0, v1 = KEYBOARD_UV
    corners = [desk_px(x, y, u, v) for u, v in ((u0, v0), (u1, v0), (u1, v1), (u0, v1))]
    if kit.mat:
        mat = [desk_px(x, y, u, v) for u, v in ((u0 - 0.06, v0 - 0.12), (u1 + 0.06, v0 - 0.12), (u1 + 0.06, v1 + 0.06), (u0 - 0.06, v1 + 0.06))]
        fill_poly(canvas, mat, kit.mat)
    fill_poly(canvas, [(px, py + 1) for px, py in corners], _dark(kit.top, 0.62), None)  # contact shadow.
    (fx0, fy0), (fx1, fy1) = corners[0], corners[1]
    fill_poly(canvas, [(fx0, fy0), (fx1, fy1), (fx1, fy1 + 1), (fx0, fy0 + 1)], _dark(kit.keys, 0.7), None)  # darker front face.
    fill_poly(canvas, corners, kit.keys)  # body, with the 1 px dark outline.
    steps = round(28 * (u1 - u0))
    for row, f in enumerate((0.22, 0.5, 0.78)):  # row 0 is the front one, nearest the camera.
        vr = v0 + (v1 - v0) * f
        for t in range(steps + 1):
            px, py = desk_px(x, y, u0 + (u1 - u0) * t / steps, vr)
            if row == 0 and steps * 0.3 <= t <= steps * 0.7:
                color = kit.key_cap  # space bar: one wide run of key pixels.
            else:
                color = kit.key_cap if t % 2 == 0 else kit.key_gap
            if kit.rgb and color == kit.key_cap:
                color = RAINBOW[(t + row + tick // 3) % len(RAINBOW)]
            canvas.put(px, py, color)


def draw_items(canvas: Canvas, x: int, y: int, kit: Kit, seed: int, tick: int) -> None:
    """Everything on the desk's top but the monitor, drawn from the back of the desk to the front."""
    near, far, note = kit.items
    _place_item(canvas, x, y, kit, far, FAR_UV)
    draw_keyboard(canvas, x, y, kit, tick)
    _place_item(canvas, x, y, kit, near[seed % len(near)], NEAR_UV)
    if note:
        _place_item(canvas, x, y, kit, note, NOTE_UV)
