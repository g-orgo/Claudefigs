"""Slim, profile-facing avatars of the office (facing left, toward the monitor), drawn as pixel rows.

Every row set here is written in avatar coordinates: column 0 is 3 columns right of the character's 16-wide cell
(`pad` adds that margin), row 0 is the head top. The body starts at row BODY_TOP.
"""
BODY_TOP = 11


def pad(rows: list[str], left: int = 3) -> list[str]:
    return ["." * left + row for row in rows]


# Head with short hair: face in front (left), nose one pixel out of the outline, mouth at the front edge,
# nape and ear behind. Eyes and mouth are overlays (EYES, MOUTH) so poses can change them.
BASE = [
    "...oooooo..",
    "..ohhhhhHo.",
    ".ohHhhhhhdo",
    ".ohhhhhhhdo",
    ".ohsshhhhdo",
    ".osssshhhdo",
    ".osssSShhdo",
    "osssSSShhdo",
    ".osssSShddo",
    ".ossssSdddo",
    "..ossSoooo.",
]


def _style(base: list[str], edits: dict[int, str], above: list[str] = (), width: int = 15) -> list[str]:
    """Head rows of one hair style: the base with whole rows replaced, plus rows stacked above the head.
    Rows are left-padded by 2 so hair can stick out in front; `above` rows sit over row 0."""
    rows = [(".." + edits.get(i, row)).ljust(width, ".") for i, row in enumerate(base)]
    return [(".." + r).ljust(width, ".") for r in above] + rows


STYLES = {  # (rows, how many rows sit above the head top)
    "neat": (_style(BASE, {}), 0),
    "bob": (_style(BASE, {3: "ohhhhhhhhhdo", 4: "ohhhhhhhhhdo", 5: "ohsshhhhhhdo", 8: ".osssSShhddo", 9: ".ossssShdddo",
                          10: "..ossSohddo."}), 0),
    "spiky": (_style(BASE, {0: "..ooooooo..", 1: ".ohhhHhhHo."}, ["...o.o.o...", "..oHoHoHo.."]), 2),
    "ponytail": (_style(BASE, {4: ".ohsshhhhdoo", 5: ".osssshhhdHdo", 6: ".osssSShhdohdo", 7: "osssSSShhdohdo",
                               8: ".osssSShddo.odo", 9: ".ossssSdddo..o"}), 0),
    "bun": (_style(BASE, {}, ["....oooo...", "...oHhhdo..", "...ohhddo.."]), 3),
    "curly": (_style(BASE, {0: "..oooooooo.", 1: ".ohHhHhhHho", 2: "ohHhhHhhhdo", 3: "ohhHhhhHhdo", 4: "ohssHhhhHdo",
                            8: ".osssSShHdo", 9: ".ossssShdHo"}, ["...oo.oo...", "..oHhohHo.."]), 2),
    "long": (_style(BASE, {8: ".osssSShhddo", 9: ".ossssShhddo", 10: "..ossSohhddo"}), 0),
    "cap": (_style(BASE, {0: "...oooooo..", 1: "..oRRRRRRo.", 2: ".oRRRRRRRRo", 3: "oKKKKKoRRdo", 4: ".ohsshhhhdo"}), 0),
}
LONG_TAIL = ["......ohhdo", "......ohhdo", "......oddo.", ".......oo.."]  # long hair falling behind the shoulders.

# Eye, as (row, column, rows) overlays in avatar coordinates.
EYES = {
    "open": [(5, 3, ["e", "e"])],
    "blink": [(6, 3, ["e"])],
    "happy": [(5, 2, [".e.", "e.e"])],
    "down": [(6, 3, ["e", "e"])],
    "right": [(5, 4, ["e", "e"])],
}
MOUTH = (9, 2, ["m"])
CHEEK = (7, 4, ["b"])
GLASSES = (4, 1, ["gggg", "g..g", "gggg"])

# Seated body behind the desk: slim torso, lap and thigh pointing toward the desk.
SIT = [
    "...oSSo....",
    "..otkTTo...",
    ".ottkTTTo..",
    ".ottktTTo..",
    ".otTtkTTo..",
    ".otTttTTo..",
    ".oppppPPo..",
    "oppppppPo..",
]
STAND = SIT[:6] + [
    ".osoTtTTo..",
    "..oppPPPo..",
    "..oppoPPo..",
    "..oppoPPo..",
    "..oppoPPo..",
    "..oppoPPo..",
    ".offoFffo..",
    "offfoffffo.",
    "oooooooooo.",
]
STEP_A = STAND[:12] + ["..oppooPPo.", ".offo.oFfo.", "offfo.offfo", "ooooo.ooooo"]
STEP_B = STAND[:12] + [".oppo.oPPo.", "offfoooffo.", "oooooffffo.", "....oooooo."]
ARM_HANG = (2, 1, ["oTo", "oTo", "oTo", "oTo", "oso", ".o."])  # near arm along the body, standing.

# Seated arm overlays (row, column, rows), drawn over the desk so the hand rests on it.
ARM_DESK = (2, -3, ["....oTo", "....oTo", "....oTo", ".ooooTo", "osssTTo", ".oooooo"])
ARM_TAP = (2, -3, ["....oTo", "....oTo", "....oTo", "....oTo", ".ooooTo", "osssTTo", ".oooooo"])
SHEET = (1, -6, ["ooooooo", "oWWWWWo", "oWggWWo", "oWWWWWo", "oWgggWo", "oWWWWWo", "ooooooo"])
FAR_HAND_CHIN = (-3, 3, ["oSo", "oTo", "oTo", "oTo"])
PHONE = (-6, 4, ["ooo", "ono", "ono", "oSo", "oTo"])
CUP_UP = (-3, -2, ["oooo", "occo", "occo", "oooo", ".oso"])
CUP_LOW = (4, -5, ["oooo", "occo", "occo", "oooo"])
FOLDED = (5, -4, [".ooooooooooo", "oTTTTTTTTTso", "ottttttttTso", ".ooooooooooo"])
HAND_UP = (0, -2, ["oso", "oTo", "oTo", "oTo"])  # waving while chatting.
