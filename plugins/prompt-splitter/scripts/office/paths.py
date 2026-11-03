"""Walkable grid of a view: characters follow routes around furniture and walls instead of straight lines."""
from collections import deque

CELL = 4
EXIT_RADIUS = 3  # cells around a route's ends that stay walkable, since chairs and door fronts touch furniture.
STEPS = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1))


class Grid:
    def __init__(self, width: int, height: int, blocked) -> None:
        self.cols, self.rows = width // CELL + 1, height // CELL + 1
        self.blocked = [[blocked(c * CELL + CELL // 2, r * CELL + CELL // 2) for c in range(self.cols)] for r in range(self.rows)]

    def _cell(self, point: tuple[int, int]) -> tuple[int, int]:
        return max(0, min(self.cols - 1, point[0] // CELL)), max(0, min(self.rows - 1, point[1] // CELL))

    def is_free(self, point: tuple[int, int]) -> bool:
        c, r = self._cell(point)
        return not self.blocked[r][c]

    def nearest_free(self, point: tuple[int, int]) -> tuple[int, int]:
        """The point itself when walkable, else the center of the closest walkable cell."""
        if self.is_free(point):
            return point
        start = self._cell(point)
        seen, queue = {start}, deque([start])
        while queue:
            c, r = queue.popleft()
            if not self.blocked[r][c]:
                return c * CELL + CELL // 2, r * CELL + CELL // 2
            for dc, dr in STEPS[:4]:
                nxt = (c + dc, r + dr)
                if 0 <= nxt[0] < self.cols and 0 <= nxt[1] < self.rows and nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        return point

    def route(self, start: tuple[int, int], goal: tuple[int, int]) -> list[tuple[int, int]]:
        """Waypoints from start to goal, ending exactly at goal; just the goal when no way around exists."""
        begin, end = self._cell(start), self._cell(goal)

        def walkable(c: int, r: int) -> bool:
            near = max(abs(c - begin[0]), abs(r - begin[1])) <= EXIT_RADIUS or max(abs(c - end[0]), abs(r - end[1])) <= EXIT_RADIUS
            return near or not self.blocked[r][c]

        came = {begin: None}
        queue = deque([begin])
        while queue and end not in came:
            c, r = queue.popleft()
            for dc, dr in STEPS:
                nxt = (c + dc, r + dr)
                if not (0 <= nxt[0] < self.cols and 0 <= nxt[1] < self.rows) or nxt in came or not walkable(*nxt):
                    continue
                if dc and dr and not (walkable(c + dc, r) and walkable(c, r + dr)):
                    continue  # never cuts a corner of an obstacle.
                came[nxt] = (c, r)
                queue.append(nxt)
        if end not in came:
            return [goal]
        cells = []
        cur = end
        while cur is not None:
            cells.append(cur)
            cur = came[cur]
        cells.reverse()
        points = []
        for before, here, after in zip(cells, cells[1:], cells[2:]):
            if (here[0] - before[0], here[1] - before[1]) != (after[0] - here[0], after[1] - here[1]):
                points.append((here[0] * CELL + CELL // 2, here[1] * CELL + CELL // 2))
        return points + [goal]


def desk_blocks(desk: tuple[int, int], x: int, y: int) -> bool:
    """True for feet inside a desk's isometric top, under its thickness and legs, or on its chair."""
    px, py = x - desk[0], y - desk[1]
    if 18 <= px <= 38 and -5 <= py <= 12:
        return True
    return any(-16 <= px - 2 * rel <= 16 and 8 <= px + 2 * rel <= 72 for rel in (py, py - 10))
