"""Pure room layout for the office viewer: groups, pages, geometry and sign text. No drawing here."""
import math
import time
import zlib
from dataclasses import dataclass, field

from office.model import Worker
from office.term import char_width

STATION_ROWS = 22  # rows of one desk station below its bubble
BUBBLE_MIN, BUBBLE_MAX = 5, 14  # bubble rows
LINE_MIN = STATION_ROWS + BUBBLE_MIN  # rows of one desk line with the smallest bubble
PITCH_MIN, PITCH_MAX = 46, 60  # columns per item
SIDE_MARGIN = 8  # columns kept free on each side of a room
CORRIDOR = 4  # columns between rooms in a shelf
CHAMFER = 12  # pixels of the rear wall corner cut into the floor
PALETTES = 6  # number of room palettes
NO_TITLE = "Sessão sem título"
MIN_TITLE = 12  # title columns kept before the meta is dropped


@dataclass
class Room:
    group: str
    title: str
    workers: list[Worker]
    total: int  # items of the whole group
    part: int
    parts: int
    cols: int
    lines: int
    x: int
    row: int
    width: int  # cells
    height: int  # cells
    bubble: int  # bubble rows
    palette: int
    sign: str
    sign_col: int
    cells: list[tuple[int, int, int, int]] = field(default_factory=list)  # bubble col, row, width, height

    @property
    def left(self) -> int:
        return self.x

    @property
    def right(self) -> int:
        return self.x + self.width - 1

    @property
    def top(self) -> int:
        return self.row * 2

    @property
    def bottom(self) -> int:
        return (self.row + self.height) * 2 - 1

    @property
    def floor_y(self) -> int:
        return (self.row + 1 + self.bubble) * 2 + 6

    def floor_edge(self, x: int) -> int:
        """Return the first floor pixel row at column x, lifted near the rear corners by the chamfer."""
        return self.floor_y + max(0, CHAMFER - (x - self.left) // 2, CHAMFER - (self.right - x) // 2)

    def clamp_foot(self, x: int, y: int) -> tuple[int, int]:
        """Keep a standing foot point inside the walls and on the floor."""
        x = min(max(x, self.left + 9), self.right - 9)
        y = min(max(y, self.floor_edge(x) + 1), self.bottom - 2)
        return x, y


def group_workers(workers: list[Worker]) -> list[list[Worker]]:
    """Group workers by split group, keeping the first-seen order of groups and members."""
    order: list[str] = []
    members: dict[str, list[Worker]] = {}
    for worker in workers:
        if worker.group not in members:
            order.append(worker.group)
            members[worker.group] = []
        members[worker.group].append(worker)
    return [members[name] for name in order]


def display_width(text: str) -> int:
    """Terminal cells used by a string."""
    return sum(char_width(ch) for ch in text)


def truncate(text: str, width: int) -> str:
    """Cut text to width cells, ending with '...' when something was dropped."""
    if width <= 0:
        return ""
    if display_width(text) <= width:
        return text
    if width < 3:
        out = ""
        for ch in text:
            if display_width(out + ch) > width:
                break
            out += ch
        return out
    out = ""
    for ch in text:
        if display_width(out + ch) + 3 > width:
            break
        out += ch
    return out + "..."


def sign_text(title: str, started_ms: float, total: int, part: int, parts: int, width: int) -> str:
    """Build the room sign: title plus meta (date, item count, part), truncated to width cells."""
    title = title or NO_TITLE
    count = "1 item" if total == 1 else f"{total} itens"
    if started_ms > 0:
        date = time.strftime("%d/%m %H:%M", time.localtime(started_ms / 1000))
        meta = f"{date}, {count}"
    else:
        meta = count
    if parts > 1:
        meta += f", parte {part}/{parts}"
    full = f"{title}  {meta}"
    if display_width(full) <= width:
        return full
    avail = width - display_width(meta) - 2
    if avail >= MIN_TITLE:
        return f"{truncate(title, avail)}  {meta}"
    return truncate(title, width)


def shape(count: int, max_cols: int) -> tuple[int, int]:
    """Return (lines, columns) for count items given at most max_cols columns."""
    lines = math.ceil(count / max_cols)
    return lines, math.ceil(count / lines)


@dataclass
class _Unit:
    group: str
    members: list[Worker]  # this piece's workers
    group_members: list[Worker]  # all workers of the group
    part: int
    parts: int
    lines: int
    cols: int
    alone: bool  # a non-last piece fills its page by itself


def _units(workers: list[Worker], max_cols: int, max_lines: int) -> list[_Unit]:
    units: list[_Unit] = []
    for members in group_workers(workers):
        count = len(members)
        lines, cols = shape(count, max_cols)
        if lines <= max_lines:
            units.append(_Unit(members[0].group, members, members, 1, 1, lines, cols, False))
            continue
        per = cols * max_lines
        pieces = [members[i:i + per] for i in range(0, count, per)]
        for number, piece in enumerate(pieces, start=1):
            last = number == len(pieces)
            piece_lines, piece_cols = shape(len(piece), max_cols) if last else (max_lines, cols)
            units.append(_Unit(members[0].group, piece, members, number, len(pieces),
                               piece_lines, piece_cols, not last))
    return units


def _shelves_fit(shelves: list[list[_Unit]], usable: int) -> bool:
    used = sum(max(u.lines for u in shelf) * LINE_MIN + 1 for shelf in shelves)
    return used <= usable


def _pack(units: list[_Unit], cols: int, usable: int, margin: int) -> list[list[list[_Unit]]]:
    pages: list[list[list[_Unit]]] = []
    shelves: list[list[_Unit]] = []

    def close() -> None:
        nonlocal shelves
        if shelves:
            pages.append(shelves)
        shelves = []

    for unit in units:
        if unit.alone and shelves:
            close()
        if shelves and shelves[-1]:
            last = shelves[-1]
            width = sum(u.cols * PITCH_MIN + 2 * margin for u in last + [unit]) + CORRIDOR * len(last)
            if width <= cols:
                trial = shelves[:-1] + [last + [unit]]
            else:
                trial = shelves + [[unit]]
        else:
            trial = [[unit]]
        if shelves and not _shelves_fit(trial, usable):
            close()
            trial = [[unit]]
        shelves = trial
        if unit.alone:
            close()
    close()
    return pages


def _place(page: list[list[_Unit]], cols: int, usable: int, margin: int) -> list[Room]:
    lines_total = sum(max(u.lines for u in shelf) for shelf in page)
    shelf_count = len(page)
    line = min((usable - shelf_count) // max(1, lines_total), STATION_ROWS + BUBBLE_MAX)
    bubble = max(BUBBLE_MIN, line - STATION_ROWS)
    line = bubble + STATION_ROWS
    spare = max(0, usable - lines_total * line - shelf_count)
    row = spare // 2
    rooms: list[Room] = []
    for shelf in page:
        shelf_lines = max(u.lines for u in shelf)
        total_cols = sum(u.cols for u in shelf)
        gaps = len(shelf) - 1
        pitch = max(1, min(PITCH_MAX, (cols - gaps * CORRIDOR - 2 * margin * len(shelf)) // total_cols))
        widths = [u.cols * pitch + 2 * margin for u in shelf]
        shelf_width = sum(widths) + gaps * CORRIDOR
        x = (cols - shelf_width) // 2
        for unit, width in zip(shelf, widths):
            cells = []
            bubble_width = min(pitch - 2, 56)
            for i in range(len(unit.members)):
                col_i, line_i = i % unit.cols, i // unit.cols
                cells.append((
                    x + margin + col_i * pitch + (pitch - bubble_width) // 2,
                    row + 1 + line_i * line,
                    bubble_width,
                    bubble,
                ))
            rooms.append(Room(
                group=unit.group,
                title="",
                workers=list(unit.members),
                total=len(unit.group_members),
                part=unit.part,
                parts=unit.parts,
                cols=unit.cols,
                lines=math.ceil(len(unit.members) / unit.cols),
                x=x,
                row=row,
                width=width,
                height=1 + unit.lines * line,
                bubble=bubble,
                palette=0,
                sign="",
                sign_col=0,
                cells=cells,
            ))
            x += width + CORRIDOR
        row += shelf_lines * line + 1
    return rooms


def _finish(rooms: list[Room], units_of: dict[int, _Unit]) -> None:
    previous = None
    for room in rooms:
        unit = units_of[id(room)]
        title = next((w.room_title for w in unit.group_members if w.room_title), "")
        started = [w.started_ms for w in unit.group_members if w.started_ms > 0]
        started_ms = min(started) if started else 0.0
        sign_width = room.width - 2 * CHAMFER - 2
        if sign_width < 12:
            sign_width = room.width - 2
        room.title = title
        room.sign = sign_text(title, started_ms, room.total, room.part, room.parts, sign_width)
        room.sign_col = room.x + (room.width - display_width(room.sign)) // 2
        palette = zlib.crc32(room.group.encode()) % PALETTES
        if palette == previous:
            palette = (palette + 1) % PALETTES
        room.palette = palette
        previous = palette


def paginate(workers: list[Worker], cols: int, rows: int) -> list[list[Room]]:
    """Split workers into pages of rooms that fit a cols x rows terminal, keeping groups whole when they fit."""
    usable = rows - 1
    margin = max(0, min(SIDE_MARGIN, (cols - PITCH_MIN) // 2))
    max_cols = max(1, (cols - 2 * margin) // PITCH_MIN)
    max_lines = max(1, (usable - 1) // LINE_MIN)
    units = _units(workers, max_cols, max_lines)
    pages: list[list[Room]] = []
    for page in _pack(units, cols, usable, margin):
        rooms = _place(page, cols, usable, margin)
        # Map each room back to its unit in packing order.
        flat = [u for shelf in page for u in shelf]
        units_of = {id(room): unit for room, unit in zip(rooms, flat)}
        pages.append(rooms)
        _finish(rooms, units_of)
    return pages
