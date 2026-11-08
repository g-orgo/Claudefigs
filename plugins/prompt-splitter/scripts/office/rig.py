"""Hotel-style avatars built from parts, facing down-left (toward the monitor) in a 3/4 isometric view.

The avatar lives in a CELL_W wide cell; (0, 0) is the cell's top-left and the head top. Each part is painted into a
letter grid in draw order with its own 1 px outline, so a later part's outline separates it from the parts behind;
soften_lines later turns those inner outlines into dark tones and only the silhouette keeps the dark line.
"""
import math

CELL_W = 34
HEAD_H = 26  # head top to chin.
STAND_H = 80  # head top to the soles.


class Grid:
    def __init__(self):
        self.px: dict[tuple[int, int], str] = {}

    def paint(self, cells: set, fill, edge: str = "o") -> None:
        """Paints a part: its cells get fill(x, y) (a letter), and the ring just outside gets the outline letter."""
        for x, y in cells:
            for p in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if p not in cells:
                    self.px[p] = edge
        for x, y in cells:
            self.px[(x, y)] = fill(x, y)


def ellipse(cx: float, cy: float, rx: float, ry: float) -> set:
    return {(x, y) for y in range(int(cy - ry) - 1, int(cy + ry) + 2) for x in range(int(cx - rx) - 1, int(cx + rx) + 2)
            if ((x + 0.5 - cx) / rx) ** 2 + ((y + 0.5 - cy) / ry) ** 2 <= 1}


def polygon(points: list) -> set:
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    out = set()
    for y in range(int(min(ys)), int(max(ys)) + 1):
        for x in range(int(min(xs)), int(max(xs)) + 1):
            inside, j = False, len(points) - 1
            for i in range(len(points)):
                (xi, yi), (xj, yj) = points[i], points[j]
                if (yi > y + 0.5) != (yj > y + 0.5) and x + 0.5 < (xj - xi) * (y + 0.5 - yi) / (yj - yi) + xi:
                    inside = not inside
                j = i
            if inside:
                out.add((x, y))
    return out


def limb(a: tuple, b: tuple, width: float) -> set:
    """A capsule from a to b: arms and legs."""
    (ax, ay), (bx, by) = a, b
    length = max(1e-6, math.hypot(bx - ax, by - ay))
    r = width / 2
    out = set()
    for y in range(int(min(ay, by) - r) - 1, int(max(ay, by) + r) + 2):
        for x in range(int(min(ax, bx) - r) - 1, int(max(ax, bx) + r) + 2):
            px, py = x + 0.5, y + 0.5
            t = max(0.0, min(1.0, ((px - ax) * (bx - ax) + (py - ay) * (by - ay)) / length ** 2))
            if math.hypot(px - (ax + t * (bx - ax)), py - (ay + t * (by - ay))) <= r:
                out.add((x, y))
    return out


def lit(base: str, shade: str, split):
    """Two-tone fill with light from the top-left: cells past split(x, y) > 0 take the shade letter."""
    return lambda x, y: shade if split(x, y) > 0 else base
