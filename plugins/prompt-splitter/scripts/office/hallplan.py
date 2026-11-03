"""Floor plan of the hall: offices on diagonal walls beside a central table, or a plain list when narrow."""
from dataclasses import dataclass

from .hallart import BAY_H, BAY_W, CAP, DEPTH
from .paths import Grid

WIDE_COLS, WIDE_ROWS = 188, 46
SLOPE = 3  # the side walls fall one pixel every this many columns.
DROP = BAY_W // SLOPE
BACK_Y = 36  # floor line of the back wall.
WALL_GAP = 6  # flat floor kept between the table and the start of the diagonal walls.
LANE = 8  # walkable gap below a wall or a free-standing office.
TABLE_W, TABLE_H = 60, 36
TABLE_TOP = BACK_Y - 18
CELL_W, CELL_H, TOP_PX = 64, 48, 10
SIDE_LIST_COLS = 122  # from here one door and the table fit side by side.


@dataclass(frozen=True)
class Panel:
    """Where one office front goes. mirror swaps door and window; slope makes it follow an angled wall."""
    x: int
    y: int
    mirror: bool = False
    slope: int = 0  # 0 flat, 1 falls to the right, -1 falls to the left.
    free: bool = False  # a free-standing lower office, with a roof strip above it.

    def shift(self, col: int) -> int:
        if self.slope > 0:
            return col // SLOPE
        return (BAY_W - 1 - col) // SLOPE if self.slope < 0 else 0

    @property
    def door(self) -> tuple[int, int]:
        """The floor point in front of this office's door."""
        if self.slope:
            col = BAY_W - 10 if self.slope < 0 else 9
            return self.x + col, self.y + self.shift(col) + BAY_H + 4
        return self.x + 10, self.y + BAY_H + 2


class Plan:
    def __init__(self, cols: int, rows: int, with_table: bool):
        self.cols, self.height = cols, max(0, rows - 1) * 2
        self.wide = with_table and cols >= WIDE_COLS and rows >= WIDE_ROWS
        self.table: tuple[int, int] | None = None
        if self.wide:
            self._wide()
        else:
            self._list(with_table)

    def wall_start(self) -> int:
        """Column where the flat back wall ends and the diagonal walls begin."""
        return (self.cols - TABLE_W) // 2 - WALL_GAP

    def _wide(self) -> None:
        self.table = ((self.cols - TABLE_W) // 2, TABLE_TOP)
        wall_start = self.wall_start()
        self.panels = []
        for i in range(max(1, wall_start // BAY_W)):
            x = wall_start - (i + 1) * BAY_W
            if x < 0:
                continue
            y = self.floor_edge(x + BAY_W - 1) - BAY_H
            self.panels += [Panel(x, y, True, -1), Panel(self.cols - x - BAY_W, y, False, 1)]
        y = self.floor_edge(2 + BAY_W - 1) + LANE + CAP
        while y + DROP + BAY_H <= self.height - 2:
            self.panels += [Panel(2, y, True, -1, True), Panel(self.cols - 2 - BAY_W, y, False, 1, True)]
            y += BAY_H + LANE + CAP

    def _list(self, with_table: bool) -> None:
        n_cols = max(1, self.cols // CELL_W)
        n_rows = max(1, self.height // CELL_H)
        side = with_table and n_cols * n_rows == 1 and self.cols >= SIDE_LIST_COLS
        left = 2 if side else (self.cols - n_cols * CELL_W) // 2 + 2
        top = (self.height - n_rows * CELL_H) // 2
        cells = [(left + (i % n_cols) * CELL_W, top + (i // n_cols) * CELL_H + TOP_PX) for i in range(n_cols * n_rows)]
        if side:
            self.table = (self.cols - TABLE_W - 2, cells[0][1])
        elif with_table and len(cells) >= 2:
            self.table = cells.pop()
        self.panels = [Panel(x, y) for x, y in cells]

    def floor_edge(self, x: int) -> int:
        """First floor row of the wide plan at column x: flat behind the table, falling diagonally to both view edges."""
        wall_start = self.wall_start()
        distance = min(x, self.cols - 1 - x)
        if distance >= wall_start:
            return BACK_Y
        return BACK_Y + (wall_start - distance) // SLOPE

    def spots(self) -> list[tuple[int, int]]:
        """Foot points around the table where people stop for coffee, water or a chat."""
        tx, ty = self.table
        return [(tx + 20, ty + TABLE_H + 3), (tx + 53, ty + TABLE_H + 3), (tx + 8, ty + TABLE_H + 9), (tx + 36, ty + TABLE_H + 9)]

    def blocks(self, x: int, y: int) -> bool:
        if self.table is not None:
            tx, ty = self.table
            if tx - 4 <= x <= tx + TABLE_W + 3 and ty - 2 <= y <= ty + TABLE_H:
                return True
        if self.wide:
            if y < self.floor_edge(x) + 2:
                return True
            for panel in self.panels:
                if not panel.free:
                    continue
                col = min(BAY_W - 1, max(0, x - panel.x))
                if panel.x - 2 <= x <= panel.x + BAY_W + 1 and panel.y + panel.shift(col) - CAP <= y <= panel.y + panel.shift(col) + BAY_H + 1:
                    return True
            return False
        for panel in self.panels:
            if panel.x - 4 <= x <= panel.x + BAY_W + DEPTH + 3 and panel.y - DEPTH <= y <= panel.y + BAY_H:
                return True
        return False

    def grid(self) -> Grid:
        return Grid(self.cols, self.height, self.blocks)
