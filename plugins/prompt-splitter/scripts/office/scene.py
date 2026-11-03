"""The office scene: one walled room per split group, paged by whole rooms, drawn to a terminal frame."""
from . import props, rooms, sprites
from .actors import SLOTS, Actor, resolve_target
from .bubble import CREAM, INK, draw_bubble
from .model import Worker
from .term import Frame

MIN_COLS, MIN_ROWS = 36, 28
RAINBOW = [(255, 95, 95), (255, 135, 0), (255, 215, 0), (135, 255, 0), (0, 215, 135), (0, 175, 255), (95, 135, 255), (175, 95, 255), (255, 95, 215)]
FOOTER_FG, FOOTER_BG = (225, 228, 240), (38, 34, 54)
NOTICE_TICKS = 24
BACKGROUND_CACHE = 32


class Scene:
    def __init__(self, cols: int, rows: int):
        self.tick = 0
        self.workers: list[Worker] = []
        self.pages: list[list[rooms.Room]] = []
        self.actors: dict[str, Actor] = {}
        self.selected_id: str | None = None
        self.seen = 0
        self.notice, self.notice_until = "", 0
        self._backgrounds: dict[tuple, sprites.Canvas] = {}
        self.resize(cols, rows)

    def resize(self, cols: int, rows: int) -> None:
        self.cols, self.rows = cols, rows
        self.corridor = sprites.Canvas(cols, max(0, rows - 1) * 2)
        props.draw_corridor(self.corridor)
        self.n_cols = max(1, (cols - 2 * rooms.SIDE_MARGIN) // rooms.PITCH_MIN)
        self.n_rows = max(1, (rows - 2) // rooms.LINE_MIN)
        self.per_page = self.n_cols * self.n_rows
        self._backgrounds.clear()
        self.pages = rooms.paginate(self.workers, cols, rows) if cols >= MIN_COLS and rows >= MIN_ROWS else []

    def set_workers(self, workers: list[Worker]) -> None:
        for worker in sorted(workers, key=lambda w: w.started_ms):
            if worker.id not in self.actors:
                self.actors[worker.id] = Actor(worker, sprites.LOOKS[self.seen % len(sprites.LOOKS)])
                self.seen += 1
            self.actors[worker.id].worker = worker
        self.workers = [w for group in rooms.group_workers(workers) for w in group]
        self.pages = rooms.paginate(self.workers, self.cols, self.rows) if self.cols >= MIN_COLS and self.rows >= MIN_ROWS else []
        if self.selected_id not in {w.id for w in self.workers}:
            self.selected_id = self.workers[0].id if self.workers else None

    def select(self, delta: int) -> None:
        if self.workers:
            ids = [w.id for w in self.workers]
            self.selected_id = ids[max(0, min(len(ids) - 1, ids.index(self.selected_id) + delta))]

    def selected(self) -> Worker | None:
        return next((w for w in self.workers if w.id == self.selected_id), None)

    def page(self) -> int:
        """Index of the page holding the selected worker."""
        for index, page in enumerate(self.pages):
            if any(w.id == self.selected_id for room in page for w in room.workers):
                return index
        return 0

    def _rooms(self) -> list[rooms.Room]:
        return self.pages[self.page()] if self.pages else []

    def visible(self) -> list[Worker]:
        return [w for room in self._rooms() for w in room.workers]

    def worker_at(self, col: int, row: int) -> Worker | None:
        """The worker whose visible bubble covers this cell, if any."""
        if self.cols < MIN_COLS or self.rows < MIN_ROWS or row >= self.rows - 1:
            return None
        for worker, (left, top, width, height) in zip(self.visible(), self._cells()):
            if left <= col < left + width and top <= row < top + height:
                return worker
        return None

    def notify(self, text: str) -> None:
        """Shows a short message in the footer for a few seconds."""
        self.notice, self.notice_until = text, self.tick + NOTICE_TICKS

    def _cells(self) -> list[tuple[int, int, int, int]]:
        """Per visible worker, in visible order: bubble col, bubble row, bubble width, bubble height."""
        return [cell for room in self._rooms() for cell in room.cells]

    def _sync(self) -> tuple[list[Actor], list[tuple[int, int, int, int]]]:
        """Seats the visible actors at their room desks and picks where each waiter goes."""
        page_rooms = self._rooms()
        cells = self._cells()
        visible = self.visible()
        actors = [self.actors[w.id] for w in visible]
        room_of = {w.id: room for room in page_rooms for w in room.workers}
        fresh = []
        for actor, (col, top, width, height) in zip(actors, cells):
            desk = (col + width // 2 - props.DESK_W // 2, (top + height) * 2 + 12)
            if actor.desk != desk:
                actor.place(desk)
                fresh.append(actor)
            actor.visitors, actor.target = 0, None
        by_id = {a.worker.id: a for a in actors}
        for actor in actors:
            actor.goal = actor.stand_point
            if actor.worker.state != "waiting":
                continue
            target = resolve_target(actor.worker, self.workers)
            host = by_id.get(target.id) if target else None
            if host is not None and host.visitors < len(SLOTS):
                dx, dy = SLOTS[host.visitors]
                actor.goal = room_of[host.worker.id].clamp_foot(host.desk[0] + dx, host.desk[1] + dy)
                actor.target = host
                host.visitors += 1
        for actor in fresh:
            actor.settle()
        return actors, cells

    def step(self) -> None:
        self.tick += 1
        actors, _ = self._sync()
        for actor in actors:
            actor.step()

    def _background(self, page_rooms: list[rooms.Room]) -> sprites.Canvas:
        """Corridor with every room shell of this page drawn once and cached by room layout."""
        key = tuple((r.group, r.x, r.row, r.width, r.height, r.bubble, r.palette, r.sign, r.sign_col) for r in page_rooms)
        if key not in self._backgrounds:
            if len(self._backgrounds) >= BACKGROUND_CACHE:
                self._backgrounds.clear()
            canvas = self.corridor.copy()
            for room in page_rooms:
                props.draw_room_shell(canvas, room, rooms.display_width(room.sign))
            self._backgrounds[key] = canvas
        return self._backgrounds[key]

    def render(self) -> Frame:
        if self.cols < MIN_COLS or self.rows < MIN_ROWS:
            frame = Frame(self.cols, self.rows)
            text = "Aumente o terminal (minimo 36x28)"
            frame.text(max(0, (self.cols - len(text)) // 2), self.rows // 2, text, (225, 228, 240), None)
            return frame
        actors, cells = self._sync()
        page_rooms = self._rooms()
        canvas = self._background(page_rooms).copy()
        items = [(a.desk[1] + 20, 0, i, a) for i, a in enumerate(actors)] + [(a.foot[1], 1, i, a) for i, a in enumerate(actors) if not a.seated]
        for _, kind, _, actor in sorted(items, key=lambda item: item[:3]):
            (actor.draw_body if kind else actor.draw_station)(canvas, self.tick)
        for actor in actors:
            actor.draw_icons(canvas, self.tick)
        frame = Frame.from_canvas(canvas, self.cols, self.rows)
        for room in page_rooms:
            frame.text(room.sign_col, room.row, room.sign, INK, CREAM, True)
        positions = {w.id: i for i, w in enumerate(self.workers)}
        for actor, (col, top, width, height) in zip(actors, cells):
            worker = actor.worker
            color = RAINBOW[positions[worker.id] % len(RAINBOW)]
            tail = actor.desk[0] + props.SEAT_DX + 8
            draw_bubble(frame, col, top, width, height, worker, self.workers, color, worker.id == self.selected_id, tail)
            if not actor.seated:
                hx, hy = actor.head()
                frame.text(hx + 5, hy // 2 - 1, f" {worker.item_label} ", (28, 24, 40), color, True)
        if not self.workers:
            text = " Nenhum split recente "
            frame.text((self.cols - len(text)) // 2, self.rows // 2, text, INK, CREAM, True)
        self._footer(frame)
        return frame

    def _footer(self, frame: Frame) -> None:
        count = lambda *states: sum(w.state in states for w in self.workers)
        pages = max(1, len(self.pages))
        text = (f" {count('working', 'thinking')} rodando  {count('waiting', 'ask', 'blocked')} aguardando  "
                f"{count('done')} concluidas  {count('failed')} falhas  |  Tab/setas/roda selecionam  Enter/clique abre  q sai  "
                f"pagina {self.page() + 1}/{pages}")
        if self.tick < self.notice_until:
            text = f" {self.notice}"
        frame.text(0, self.rows - 1, text.ljust(self.cols)[:self.cols], FOOTER_FG, FOOTER_BG)
