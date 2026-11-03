"""Floor plan of the hall: rooms along both side walls with the central table on top, or a plain list when narrow."""
from dataclasses import dataclass

from .hallart import BAY_H, BAY_W, DEPTH
from .paths import Grid

WIDE_COLS, WIDE_ROWS = 170, 46
SLOPE = 4  # the side walls fall one pixel every this many columns.
DROP = BAY_W // SLOPE
PITCH = BAY_H + DROP + 4
WIDE_TOP = 6
TABLE_W, TABLE_H, TABLE_TOP = 60, 36, 8
CELL_W, CELL_H, TOP_PX = 64, 48, 10
SIDE_LIST_COLS = 122  # from here one door and the table fit side by side.


@dataclass(frozen=True)
class Panel:
    """Where one office front goes. mirror swaps door and window; slope makes it follow an angled wall."""
    x: int
    y: int
    mirror: bool = False
    slope: int = 0  # 0 flat, 1 falls to the right, -1 falls to the left.

    def shift(self, col: int) -> int:
        if self.slope > 0:
            return col // SLOPE
        return (BAY_W - 1 - col) // SLOPE if self.slope < 0 else 0

    @property
    def door(self) -> tuple[int, int]:
        """The floor point in front of this office's door."""
        if self.slope > 0:  # right wall: the door is on its inner, left end.
            return self.x - 6, self.y + BAY_H - 2
        if self.slope < 0:  # left wall: the door is on its inner, right end.
            return self.x + BAY_W + 5, self.y + BAY_H - 2
        return self.x + 10, self.y + BAY_H + 2


class Plan:
    def __init__(self, cols: int, rows: int, with_table: bool):
        self.cols, self.height = cols, max(0, rows - 1) * 2
        self.wide = with_table and cols >= WIDE_COLS and rows >= WIDE_ROWS
        self.table: tuple[int, int] | None = None
        self.side_wall = 0
        if self.wide:
            self._wide()
        else:
            self._list(with_table)

    def _wide(self) -> None:
        per_side = max(1, (self.height - WIDE_TOP - BAY_H - DROP) // PITCH + 1)
        self.panels = []
        for row in range(per_side):
            y = WIDE_TOP + row * PITCH
            self.panels += [Panel(2, y, True, -1), Panel(self.cols - 2 - BAY_W, y, False, 1)]
        self.table = ((self.cols - TABLE_W) // 2, TABLE_TOP)
        self.side_wall = BAY_W + 4

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
        """First floor row of the wide plan at column x: the back wall with chamfers down to the side walls."""
        inner, center = self.side_wall, (self.cols - TABLE_W) // 2 - 6
        distance = min(x, self.cols - 1 - x)
        if distance <= inner:
            return self.height
        return 10 + max(0, (center - distance) // 2)

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
            return y < self.floor_edge(x) + 2
        for panel in self.panels:
            if panel.x - 4 <= x <= panel.x + BAY_W + DEPTH + 3 and panel.y - DEPTH <= y <= panel.y + BAY_H:
                return True
        return False

    def grid(self) -> Grid:
        return Grid(self.cols, self.height, self.blocks)
