"""The first screen: office doors with glass, one per session, plus the warehouse door and the break corner."""
from dataclasses import dataclass, field

from . import hallart, sprites
from .bubble import CREAM, INK, clean, clip, width_of
from .life import IDLE_STATES
from .model import Worker
from .term import Frame

CELL_W, CELL_H = 64, 48
TOP_PX = 10  # label rows and roof edge above the front wall.
WAREHOUSE, BACK = "@warehouse", "@back"
FOOTER_FG, FOOTER_BG = (225, 228, 240), (38, 34, 54)
MARK = (255, 214, 90)
MIN_COLS, MIN_ROWS = 36, 28
SPOTS = ((12, 38), (43, 38), (26, 44), (56, 42))  # foot points around the break corner.


@dataclass
class Door:
    key: str
    title: str
    workers: list[Worker] = field(default_factory=list)


def doors_of(workers: list[Worker]) -> list[Door]:
    """One door per session, in the order of its newest split."""
    doors: dict[str, Door] = {}
    for worker in workers:
        door = doors.setdefault(worker.room_key, Door(worker.room_key, worker.room_title or worker.title))
        door.workers.append(worker)
    return list(doors.values())


def status_of(door: Door) -> str:
    states = {w.state for w in door.workers}
    if states & {"working", "thinking"}:
        return "run"
    if states & {"ask", "blocked", "waiting"}:
        return "wait"
    return "fail" if "failed" in states else "idle"


def summary_of(door: Door) -> str:
    states = [w.state for w in door.workers]
    running = sum(s in ("working", "thinking") for s in states)
    waiting = sum(s in ("waiting", "ask", "blocked") for s in states)
    parts = [f"{running} rodando"] * bool(running) + [f"{waiting} aguardando"] * bool(waiting)
    return ", ".join(parts) or f"{len(states)} {'item' if len(states) == 1 else 'itens'} concluidos"


class Hall:
    def __init__(self, cols: int, rows: int, warehouse: bool, place: str = ""):
        self.warehouse, self.place = warehouse, place
        self.doors: list[Door] = []
        self.selected_key: str | None = None
        self.actors: dict = {}
        self.notice, self.notice_until, self.tick = "", 0, 0
        self.resize(cols, rows)

    def resize(self, cols: int, rows: int) -> None:
        self.cols, self.rows = cols, rows
        self.n_cols = max(1, cols // CELL_W)
        self.n_rows = max(1, max(0, rows - 1) * 2 // CELL_H)
        self.per_page = self.n_cols * self.n_rows
        self.has_corner = not self.warehouse and self.per_page >= 3
        self.page_size = self.per_page - (1 if self.has_corner else 0)
        self.left = (cols - self.n_cols * CELL_W) // 2 + 2
        self.top = (max(0, rows - 1) * 2 - self.n_rows * CELL_H) // 2
        self._floor = None

    def set_doors(self, doors: list[Door]) -> None:
        first_doors = doors and not self.doors  # the list starts empty, so this is the first real selection.
        self.doors = doors
        if first_doors or self.selected_key not in self.entry_keys():
            self.selected_key = self.entry_keys()[0]

    def entry_keys(self) -> list[str]:
        return [d.key for d in self.doors] + [BACK if self.warehouse else WAREHOUSE]

    def select(self, delta: int) -> None:
        keys = self.entry_keys()
        self.selected_key = keys[max(0, min(len(keys) - 1, keys.index(self.selected_key) + delta))]

    def page(self) -> int:
        return self.entry_keys().index(self.selected_key) // self.page_size if self.selected_key in self.entry_keys() else 0

    def pages(self) -> int:
        return (len(self.entry_keys()) + self.page_size - 1) // self.page_size

    def visible_keys(self) -> list[str]:
        start = self.page() * self.page_size
        return self.entry_keys()[start:start + self.page_size]

    def cell_xy(self, index: int) -> tuple[int, int]:
        """Front wall corner of a grid cell; TOP_PX holds the labels above it."""
        return self.left + (index % self.n_cols) * CELL_W, self.top + (index // self.n_cols) * CELL_H + TOP_PX

    def corner_xy(self) -> tuple[int, int]:
        return self.cell_xy(self.per_page - 1)

    def key_at(self, col: int, row: int) -> str | None:
        """The entry whose label or front wall covers this cell."""
        if row >= self.rows - 1:
            return None
        for index, key in enumerate(self.visible_keys()):
            x, y = self.cell_xy(index)
            if x <= col < x + hallart.BAY_W + hallart.DEPTH and y - TOP_PX <= row * 2 < y + hallart.BAY_H:
                return key
        return None

    def notify(self, text: str) -> None:
        self.notice, self.notice_until = text, self.tick + 24

    def _door_of(self, key: str) -> Door | None:
        return next((d for d in self.doors if d.key == key), None)

    def _out_of_room(self) -> list:
        """Characters of this page's sessions that are outside their rooms, with where each one came from."""
        out = []
        for index, key in enumerate(self.visible_keys()):
            door = self._door_of(key)
            for worker in door.workers if door else []:
                actor = self.actors[worker.id]
                if actor.away:
                    out.append((actor, index))
        return out

    def step(self) -> None:
        """Walks everyone who left a room to the break corner, and back to their door when the plan ends."""
        self.tick += 1
        if not self.has_corner:
            return
        cx, cy = self.corner_xy()
        out = sorted(self._out_of_room(), key=lambda item: item[0].seed)
        taken = 0
        for actor, index in out:
            x, y = self.cell_xy(index)
            front = (x + hallart.DOOR[0] + 7, y + hallart.BAY_H + 1)
            if actor.hall_foot is None:
                actor.hall_foot = front
            leaving = actor.life.kind != "out"
            if leaving:
                goal = front
            elif taken < len(SPOTS):
                goal = (cx + SPOTS[taken][0], cy + SPOTS[taken][1])
                taken += 1
            else:
                actor.away, actor.hall_foot = False, None  # the corner is full, so it stays in its room.
                continue
            fx, fy = actor.hall_foot
            dx, dy = goal[0] - fx, goal[1] - fy
            actor.hall_foot = (fx + max(-2, min(2, dx)), fy + max(-2, min(2, dy)))
            actor.moving = (dx, dy) != (0, 0)
            actor.hall_flip = dx > 0 if dx else cx + 28 > fx
            if leaving and not actor.moving:
                actor.away, actor.hall_foot = False, None

    def _draw_interior(self, canvas: sprites.Canvas, x: int, y: int, door: Door) -> None:
        inside = hallart.new_interior()
        present = [self.actors[w.id] for w in door.workers if not self.actors[w.id].away][:2]
        for slot, actor in enumerate(present):
            sx = 1 + slot * 18
            hallart.rect(inside, sx + 1, 7, 14, 14, (90, 96, 130))
            pose, eyes, _, _ = actor.seat_look(self.tick)
            if actor.worker.state == "waiting":
                pose, eyes = "bob", ""
            sprites.draw(inside, sx, 2, actor.look, pose, self.tick, "all" if pose in ("bob", "wait") else "back", eyes=eyes)
        hallart.draw_desk_edge(inside)
        hallart.draw_glass(canvas, x, y, inside, self.tick + x)

    def _background(self) -> sprites.Canvas:
        if self._floor is None:
            self._floor = sprites.Canvas(self.cols, max(0, self.rows - 1) * 2)
            from .props import draw_corridor
            (hallart.draw_warehouse_floor if self.warehouse else draw_corridor)(self._floor)
        return self._floor.copy()

    def _label(self, frame: Frame, index: int, title: str, summary: str, selected: bool) -> None:
        x, y = self.cell_xy(index)
        row = max(0, (y - TOP_PX) // 2)
        width = hallart.BAY_W + hallart.DEPTH - 1
        fg, bg = ((28, 24, 40), MARK) if selected else (INK, CREAM)
        name = clip(clean(title), width - 2)
        frame.text(x, row, " " + name + " " * (width - 1 - width_of(name)), fg, bg, True)
        frame.text(x, row + 1, " " + clip(summary, width - 2).ljust(width - 1), (100, 96, 116) if not selected else fg, bg)

    def render(self) -> Frame:
        if self.cols < MIN_COLS or self.rows < MIN_ROWS:
            frame = Frame(self.cols, self.rows)
            frame.text(max(0, (self.cols - 33) // 2), self.rows // 2, "Aumente o terminal (minimo 36x28)", FOOTER_FG, None)
            return frame
        canvas = self._background()
        labels = []
        keys = self.visible_keys()
        for index, key in enumerate(keys):
            x, y = self.cell_xy(index)
            door = self._door_of(key)
            if door is None:
                back = key == BACK
                hallart.draw_roller_front(canvas, x, y, back)
                labels.append((index, "Voltar ao escritorio" if back else "Warehouse", self.place if back else "todas as sessoes, de qualquer pasta", key))
                continue
            hallart.draw_office_front(canvas, x, y, hallart.WALLS[sum(map(ord, key)) % len(hallart.WALLS)])
            hallart.draw_lamp(canvas, x, y, status_of(door), self.tick)
            self._draw_interior(canvas, x, y, door)
            extra = len(door.workers) - 2
            where = clean(door.workers[0].cwd.rstrip("/").rsplit("/", 1)[-1]) + ": " if self.warehouse else ""
            labels.append((index, door.title, where + summary_of(door) + (f" (+{extra})" if extra > 0 else ""), key))
        if self.warehouse:
            for index in range(len(keys), self.per_page):
                hallart.draw_crates(canvas, *self.cell_xy(index), index)
        if self.has_corner:
            hallart.draw_break_corner(canvas, *self.corner_xy(), self.tick)
            self._draw_visitors(canvas)
        frame = Frame.from_canvas(canvas, self.cols, self.rows)
        for index, title, summary, key in labels:
            self._label(frame, index, title, summary, key == self.selected_key)
        if not self.doors:
            text = " Nenhuma sessao neste diretorio: veja a warehouse "
            frame.text((self.cols - len(text)) // 2, self.rows - 3, text, INK, CREAM, True)
        self._footer(frame)
        return frame

    def _draw_visitors(self, canvas: sprites.Canvas) -> None:
        from . import props
        out = sorted((item[0] for item in self._out_of_room() if item[0].hall_foot), key=lambda a: a.hall_foot[1])
        chatting = sum(not a.moving for a in out) >= 2
        for slot, actor in enumerate(out):
            fx, fy = actor.hall_foot
            if actor.moving:
                pose, icon = "walk", ""
            elif chatting:
                pose = "chat"
                icon = ("dots", "", "heart")[((self.tick // 16) + slot) % 3]
            else:
                pose, icon = "wait", ""
            hx, hy = fx - 8, fy - 22
            sprites.draw(canvas, hx, hy, actor.look, pose, self.tick, flip=actor.hall_flip)
            if icon:
                props.draw_icon(canvas, hx + 16, hy - 3, icon)
            if sprites.frame_of(pose, self.tick)[4] == "steam":
                props.draw_icon(canvas, hx + (0 if actor.hall_flip else 15), hy + 6 - (self.tick // 4) % 2, "steam")

    def _footer(self, frame: Frame) -> None:
        where = "Warehouse: todas as sessoes" if self.warehouse else f"Escritorio: {self.place}"
        back = "Esc volta" if self.warehouse else "w warehouse"
        text = f" {where}  |  Tab/setas/roda selecionam  Enter/clique entra  {back}  q sai  pagina {self.page() + 1}/{self.pages()}"
        if self.tick < self.notice_until:
            text = f" {self.notice}"
        frame.text(0, self.rows - 1, text.ljust(self.cols)[:self.cols], FOOTER_FG, FOOTER_BG)
