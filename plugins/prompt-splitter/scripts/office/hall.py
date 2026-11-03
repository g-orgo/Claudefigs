"""The first screen: office doors with glass, one per session, plus the warehouse door and the break corner."""
from dataclasses import dataclass, field

from . import hallart, sprites
from .bubble import CREAM, INK, clean, clip, width_of
from .hallplan import TABLE_W, TOP_PX, Plan
from .model import Worker
from .term import Frame

WAREHOUSE, BACK = "@warehouse", "@back"
WAREHOUSE_LABEL = "Todas as sessões"  # no padding: centered on the parcel, it ends right before the coffee machine.
PARCEL_CENTER = 7  # the table's parcel spans columns 2 to 11 from the table's left edge.
FOOTER_FG, FOOTER_BG = (225, 228, 240), (38, 34, 54)
MARK = (255, 214, 90)
MIN_COLS, MIN_ROWS = 36, 28


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
        self._page = 0
        self.covered_rows = 0  # rows above the footer hidden by something the office draws over this view.
        self.resize(cols, rows)

    def resize(self, cols: int, rows: int) -> None:
        self.cols, self.rows = cols, rows
        self.plan = Plan(cols, rows, not self.warehouse)
        self.page_size = max(1, len(self.plan.panels))
        self.grid = self.plan.grid() if rows >= MIN_ROWS and cols >= MIN_COLS else None
        self._floor = None
        for actor in self.actors.values():
            actor.hall_foot, actor.hall_goal, actor.hall_path = None, None, []

    def set_doors(self, doors: list[Door]) -> None:
        first_doors = doors and not self.doors  # the list starts empty, so this is the first real selection.
        self.doors = doors
        if first_doors or self.selected_key not in self.entry_keys():
            self.selected_key = self.entry_keys()[0]

    def door_keys(self) -> list[str]:
        """What takes a place on the wall: sessions, plus the way back when inside the warehouse."""
        return [d.key for d in self.doors] + ([BACK] if self.warehouse else [])

    def entry_keys(self) -> list[str]:
        return self.door_keys() + ([] if self.warehouse else [WAREHOUSE])

    def select(self, delta: int) -> None:
        keys = self.entry_keys()
        new = keys[max(0, min(len(keys) - 1, keys.index(self.selected_key) + delta))]
        self.selected_key = new
        self.reveal()

    def scroll(self, delta: int) -> None:
        """Turns pages without moving the selection; no wrap."""
        self._page = max(0, min(self.pages() - 1, self.page() + delta))

    def reveal(self) -> None:
        """Brings the stored page to the page of the selected door; the table entries keep the page."""
        keys = self.door_keys()
        if self.selected_key in keys:
            self._page = keys.index(self.selected_key) // self.page_size

    def on_page(self, key: str | None) -> bool:
        return key not in self.door_keys() or key in self.visible_keys()

    def page(self) -> int:
        """The stored page, clamped to the pages that exist now."""
        self._page = min(self._page, max(0, self.pages() - 1))
        return self._page

    def pages(self) -> int:
        return max(1, (len(self.door_keys()) + self.page_size - 1) // self.page_size)

    def visible_keys(self) -> list[str]:
        start = self.page() * self.page_size
        return self.door_keys()[start:start + self.page_size]

    def cell_xy(self, index: int) -> tuple[int, int]:
        panel = self.plan.panels[index]
        return panel.x, panel.y

    def key_at(self, col: int, row: int) -> str | None:
        """The entry whose label or front wall covers this cell, or the warehouse parcel on the table."""
        if row >= self.rows - 1:
            return None
        if self.plan.table is not None:
            tx, ty = self.plan.table
            if tx <= col < tx + 14 and ty - 2 <= row * 2 < ty + 16:
                return WAREHOUSE
            label_x, label_y = self._warehouse_label_at()
            if row == label_y and label_x <= col < tx + 12:
                return WAREHOUSE
        for index, key in enumerate(self.visible_keys()):
            panel = self.plan.panels[index]
            shift = panel.shift(max(0, min(hallart.BAY_W - 1, col - panel.x)))
            if panel.x <= col < panel.x + hallart.BAY_W + hallart.DEPTH and panel.y - TOP_PX <= row * 2 < panel.y + shift + hallart.BAY_H:
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
        """Walks whoever left a room to the table along a route, and back to their door when the plan ends."""
        self.tick += 1
        if self.plan.table is None or self.grid is None:
            return
        spots = self.plan.spots()
        taken = 0
        for actor, index in sorted(self._out_of_room(), key=lambda item: item[0].seed):
            front = self.grid.nearest_free(self.plan.panels[index].door)
            if actor.hall_foot is None:
                actor.hall_foot = front
            leaving = actor.life.kind != "out"
            if leaving:
                goal = front
            elif taken < len(spots):
                goal, taken = self.grid.nearest_free(spots[taken]), taken + 1
            else:
                actor.away, actor.hall_foot = False, None  # the table is crowded, so it stays in its room.
                continue
            if actor.hall_goal != goal:
                actor.hall_path, actor.hall_goal = self.grid.route(actor.hall_foot, goal), goal
            actor.moving = bool(actor.hall_path)
            if actor.moving:
                fx, fy = actor.hall_foot
                dx, dy = actor.hall_path[0][0] - fx, actor.hall_path[0][1] - fy
                actor.hall_foot = (fx + max(-2, min(2, dx)), fy + max(-2, min(2, dy)))
                if dx:
                    actor.hall_flip = dx > 0
                if actor.hall_foot == actor.hall_path[0]:
                    actor.hall_path.pop(0)
            else:
                actor.hall_flip = self.plan.table[0] + TABLE_W // 2 > actor.hall_foot[0]
                if leaving:
                    actor.away, actor.hall_foot, actor.hall_goal = False, None, None

    def _draw_interior(self, canvas: sprites.Canvas, panel, door: Door) -> None:
        inside = hallart.new_interior()
        present = [self.actors[w.id] for w in door.workers if not self.actors[w.id].away][:2]
        for slot, actor in enumerate(present):
            sx = 1 + slot * 18
            hallart.rect(inside, sx + 1, 7 + hallart.PADDING, 14, 14, (90, 96, 130))
            pose, eyes, _, _ = actor.seat_look(self.tick)
            if actor.worker.state == "waiting":
                pose, eyes = "bob", ""
            sprites.draw(inside, sx, 2 + hallart.PADDING, actor.look, pose, self.tick, "all" if pose in ("bob", "wait") else "back", eyes=eyes)
        hallart.draw_desk_edge(inside)
        hallart.draw_glass(canvas, panel, inside, self.tick + panel.x)

    def _warehouse_label_at(self) -> tuple[int, int]:
        """Cell of the warehouse label: centered on the parcel, on the row just above its top."""
        tx, ty = self.plan.table
        return max(0, tx + PARCEL_CENTER - len(WAREHOUSE_LABEL) // 2), (ty + 7) // 2 - 1

    def _background(self) -> sprites.Canvas:
        """Floor, walls, table base and the flat parts of the offices of this page, drawn once."""
        keys = tuple(self.visible_keys())
        if self._floor is None or self._floor[0] != keys:
            floor = sprites.Canvas(self.cols, max(0, self.rows - 1) * 2)
            from .props import draw_corridor
            (hallart.draw_warehouse_floor if self.warehouse else draw_corridor)(floor)
            if self.plan.wide:
                hallart.draw_side_walls(floor, self.plan)
            for index, key in enumerate(keys):
                panel = self.plan.panels[index]
                if key == BACK:
                    hallart.draw_roller_front(floor, panel.x, panel.y, True)
                    continue
                wall = hallart.WALLS[sum(map(ord, key)) % len(hallart.WALLS)]
                if self.plan.wide and panel.free:
                    hallart.draw_partition(floor, panel, self.plan.panels[:index])
                if panel.free:
                    hallart.draw_free_office_frame(floor, panel, wall)
                if panel.slope == 0:
                    hallart.draw_office_front(floor, panel.x, panel.y, wall)
                else:
                    flat = sprites.Canvas(hallart.BAY_W, hallart.BAY_H)
                    hallart.draw_office_front(flat, 0, 0, wall, roof=False)
                    hallart.blit_panel(floor, flat, panel)
            if self.plan.wide:
                for index in range(len(keys), len(self.plan.panels)):
                    flat = sprites.Canvas(hallart.BAY_W, hallart.BAY_H)
                    hallart.draw_office_front(flat, 0, 0, (196, 200, 212), roof=False)
                    hallart.draw_dark_window(flat)
                    if self.plan.panels[index].free:
                        hallart.draw_partition(floor, self.plan.panels[index], self.plan.panels[:index])
                        hallart.draw_free_office_frame(floor, self.plan.panels[index], (196, 200, 212))
                    hallart.blit_panel(floor, flat, self.plan.panels[index])
            if self.warehouse:
                for index in range(len(keys), len(self.plan.panels)):
                    hallart.draw_crates(floor, self.plan.panels[index].x, self.plan.panels[index].y, index)
            self._floor = (keys, floor)
        return self._floor[1].copy()

    def _label(self, frame: Frame, index: int, title: str, summary: str, selected: bool) -> None:
        x, y = self.cell_xy(index)
        row = max(0, (y - (4 if self.plan.wide else TOP_PX)) // 2)
        width = hallart.BAY_W + (0 if self.plan.wide else hallart.DEPTH - 1)
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
        for index, key in enumerate(self.visible_keys()):
            panel = self.plan.panels[index]
            door = self._door_of(key)
            if door is None:
                labels.append((index, "Voltar ao escritorio", self.place, key))
                continue
            hallart.draw_lamp(canvas, panel, status_of(door), self.tick)
            self._draw_interior(canvas, panel, door)
            extra = len(door.workers) - 2
            where = clean(door.workers[0].cwd.rstrip("/").rsplit("/", 1)[-1]) + ": " if self.warehouse else ""
            labels.append((index, door.title, where + summary_of(door) + (f" (+{extra})" if extra > 0 else ""), key))
        if self.plan.table is not None:
            hallart.draw_table(canvas, *self.plan.table, self.tick, self.selected_key == WAREHOUSE)
            self._draw_visitors(canvas)
        frame = Frame.from_canvas(canvas, self.cols, self.rows)
        for index, title, summary, key in labels:
            self._label(frame, index, title, summary, key == self.selected_key)
        if self.plan.table is not None:
            tx, ty = self.plan.table
            selected = self.selected_key == WAREHOUSE
            label_x, label_y = self._warehouse_label_at()
            frame.text(label_x, max(0, label_y), WAREHOUSE_LABEL, (28, 24, 40) if selected else INK, MARK if selected else CREAM, selected)
        if not self.doors:
            text = " Nenhuma sessao neste diretorio: veja todas as sessões "
            frame.text((self.cols - len(text)) // 2, self.rows - 3 - self.covered_rows, text, INK, CREAM, True)
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
        where = "Todas as sessões" if self.warehouse else f"Escritorio: {self.place}"
        back = "Esc volta" if self.warehouse else "w todas as sessões"
        text = f" {where}  |  Setas selecionam  Roda rola  Enter/clique entra  {back}  q sai  pagina {self.page() + 1}/{self.pages()}"
        if self.tick < self.notice_until:
            text = f" {self.notice}"
        frame.text(0, self.rows - 1, text.ljust(self.cols)[:self.cols], FOOTER_FG, FOOTER_BG)
