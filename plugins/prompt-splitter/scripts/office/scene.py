"""The office scene: pages of workstations, one actor per split, drawn to a terminal frame."""
from . import props, sprites
from .actors import SLOTS, Actor, resolve_target
from .bubble import CREAM, INK, draw_bubble
from .model import Worker
from .term import Frame

MIN_COLS, MIN_ROWS = 36, 28
PITCH_MIN, PITCH_MAX = 46, 60
STATION_ROWS, BUBBLE_MIN, BUBBLE_MAX = 22, 6, 14
RAINBOW = [(255, 95, 95), (255, 135, 0), (255, 215, 0), (135, 255, 0), (0, 215, 135), (0, 175, 255), (95, 135, 255), (175, 95, 255), (255, 95, 215)]
FOOTER_FG, FOOTER_BG = (225, 228, 240), (38, 34, 54)
NOTICE_TICKS = 24


class Scene:
    def __init__(self, cols: int, rows: int):
        self.tick = 0
        self.workers: list[Worker] = []
        self.actors: dict[str, Actor] = {}
        self.selected_id: str | None = None
        self.seen = 0
        self.notice, self.notice_until = "", 0
        self.resize(cols, rows)

    def resize(self, cols: int, rows: int) -> None:
        self.cols, self.rows = cols, rows
        self.room = sprites.Canvas(cols, max(0, rows - 1) * 2)
        props.draw_room(self.room)
        self.n_cols = max(1, cols // PITCH_MIN)
        self.n_rows = max(1, (rows - 1) // MIN_ROWS)
        self.per_page = self.n_cols * self.n_rows
        self.page_of_actors = -1

    def set_workers(self, workers: list[Worker]) -> None:
        for worker in sorted(workers, key=lambda w: w.started_ms):
            if worker.id not in self.actors:
                self.actors[worker.id] = Actor(worker, sprites.LOOKS[self.seen % len(sprites.LOOKS)])
                self.seen += 1
            self.actors[worker.id].worker = worker
        self.workers = workers
        if self.selected_id not in {w.id for w in workers}:
            self.selected_id = workers[0].id if workers else None

    def select(self, delta: int) -> None:
        if self.workers:
            ids = [w.id for w in self.workers]
            self.selected_id = ids[max(0, min(len(ids) - 1, ids.index(self.selected_id) + delta))]

    def selected(self) -> Worker | None:
        return next((w for w in self.workers if w.id == self.selected_id), None)

    def page(self) -> int:
        ids = [w.id for w in self.workers]
        return ids.index(self.selected_id) // self.per_page if self.selected_id in ids else 0

    def visible(self) -> list[Worker]:
        start = self.page() * self.per_page
        return self.workers[start:start + self.per_page]

    def worker_at(self, col: int, row: int) -> Worker | None:
        """The worker whose visible bubble covers this cell, if any."""
        if self.cols < MIN_COLS or self.rows < MIN_ROWS or row >= self.rows - 1:
            return None
        visible = self.visible()
        for worker, (left, top, width, height) in zip(visible, self._cells(len(visible))):
            if left <= col < left + width and top <= row < top + height:
                return worker
        return None

    def notify(self, text: str) -> None:
        """Shows a short message in the footer for a few seconds."""
        self.notice, self.notice_until = text, self.tick + NOTICE_TICKS

    def _cells(self, count: int) -> list[tuple[int, int, int, int]]:
        """Per visible worker: bubble col, bubble row, bubble width, bubble height."""
        used = min(self.n_cols, max(1, count))
        pitch = min(PITCH_MAX, self.cols // used)
        margin = (self.cols - pitch * used) // 2
        lines = max(1, (count + used - 1) // used)
        cell_rows = (self.rows - 1) // max(1, min(lines, self.n_rows))
        height = max(BUBBLE_MIN, min(BUBBLE_MAX, cell_rows - STATION_ROWS))
        spare = max(0, cell_rows - height - STATION_ROWS)
        out = []
        for i in range(count):
            col, line = i % used, i // used
            drop = 2 if col % 2 and spare >= 2 else 0
            top = line * cell_rows + (spare - (2 if spare >= 2 else 0)) // 2 + drop
            width = min(pitch - 2, 56)
            out.append((margin + col * pitch + (pitch - width) // 2, top, width, height))
        return out

    def _sync(self) -> tuple[list[Actor], list[tuple[int, int, int, int]]]:
        """Seats the visible actors at this page's desks and picks where each waiter goes."""
        visible = self.visible()
        cells = self._cells(len(visible))
        actors = [self.actors[w.id] for w in visible]
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
                actor.goal, actor.target = (max(9, min(self.cols - 9, host.desk[0] + dx)), host.desk[1] + dy), host
                host.visitors += 1
        for actor in fresh:
            actor.settle()
        return actors, cells

    def step(self) -> None:
        self.tick += 1
        actors, _ = self._sync()
        for actor in actors:
            actor.step()

    def render(self) -> Frame:
        if self.cols < MIN_COLS or self.rows < MIN_ROWS:
            frame = Frame(self.cols, self.rows)
            text = "Aumente o terminal (minimo 36x28)"
            frame.text(max(0, (self.cols - len(text)) // 2), self.rows // 2, text, (225, 228, 240), None)
            return frame
        actors, cells = self._sync()
        canvas = self.room.copy()
        items = [(a.desk[1] + 20, 0, i, a) for i, a in enumerate(actors)] + [(a.foot[1], 1, i, a) for i, a in enumerate(actors) if not a.seated]
        for _, kind, _, actor in sorted(items, key=lambda item: item[:3]):
            (actor.draw_body if kind else actor.draw_station)(canvas, self.tick)
        for actor in actors:
            actor.draw_icons(canvas, self.tick)
        frame = Frame.from_canvas(canvas, self.cols, self.rows)
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
        pages = max(1, (len(self.workers) + self.per_page - 1) // self.per_page)
        text = (f" {count('working', 'thinking')} rodando  {count('waiting', 'ask', 'blocked')} aguardando  "
                f"{count('done')} concluidas  {count('failed')} falhas  |  Tab/setas/roda selecionam  Enter/clique abre  q sai  "
                f"pagina {self.page() + 1}/{pages}")
        if self.tick < self.notice_until:
            text = f" {self.notice}"
        frame.text(0, self.rows - 1, text.ljust(self.cols)[:self.cols], FOOTER_FG, FOOTER_BG)
