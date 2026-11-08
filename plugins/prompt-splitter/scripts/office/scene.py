"""The office scene: one walled room per split group, paged by whole rooms, drawn to a terminal frame."""
from . import props, rooms, sprites
from .actors import SLOTS, Actor, resolve_target
from .bubble import CREAM, INK, chat_geometry, draw_bubble, draw_selection
from .model import Worker
from .paths import Grid, desk_blocks
from .term import Frame

MIN_COLS, MIN_ROWS = 36, 28
RAINBOW = [(255, 95, 95), (255, 135, 0), (255, 215, 0), (135, 255, 0), (0, 215, 135), (0, 175, 255), (95, 135, 255), (175, 95, 255), (255, 95, 215)]
FOOTER_FG, FOOTER_BG = (225, 228, 240), (38, 34, 54)
NOTICE_TICKS = 24
BACKGROUND_CACHE = 32
WHEEL_ROWS = 3  # chat rows per wheel notch
CONTROLS = [
    "Mouse ou esquerda/direita selecionam, cima/baixo rolam o chat, roda rola o balão ou muda a página  Enter/clique abre  Esc volta  q sai",
    "Setas selecionam, roda rola o balão ou muda a página  Enter abre  Esc volta  q sai",
    "Setas e roda rolam  Enter abre  Esc volta  q sai",
]


class Scene:
    def __init__(self, cols: int, rows: int):
        self.tick = 0
        self.workers: list[Worker] = []
        self.pages: list[list[rooms.Room]] = []
        self.actors: dict[str, Actor] = {}
        self.selected_id: str | None = None
        self.show_selection = True  # False while the composer or Voltar has the pointer or focus.
        self._page = 0  # stored page, clamped to pages() on read.
        self.chat_scroll: dict[str, int] = {}  # rows back from the newest, per worker id; absent means 0.
        self._chat_seen: dict[str, int] = {}  # chat row count last seen per worker id, to follow new lines.
        self.seen = 0
        self.notice, self.notice_until = "", 0
        self._backgrounds: dict[tuple, sprites.Canvas] = {}
        self._grids: dict[tuple, Grid] = {}
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

    def register(self, workers: list[Worker]) -> None:
        """Keeps one actor per worker, whichever view shows it; the look stays for the whole run."""
        for worker in sorted(workers, key=lambda w: w.started_ms):
            if worker.id not in self.actors:
                self.actors[worker.id] = Actor(worker, sprites.LOOKS[self.seen % len(sprites.LOOKS)])
                self.seen += 1
            self.actors[worker.id].worker = worker

    def set_workers(self, workers: list[Worker]) -> None:
        self.register(workers)
        self.workers = [w for group in rooms.group_workers(workers) for w in group]
        self.pages = rooms.paginate(self.workers, self.cols, self.rows) if self.cols >= MIN_COLS and self.rows >= MIN_ROWS else []
        if self.selected_id not in {w.id for w in self.workers}:
            self.selected_id = self.workers[0].id if self.workers else None
        live = {w.id for w in self.workers}
        for offsets in (self.chat_scroll, self._chat_seen):
            for key in [key for key in offsets if key not in live]:
                del offsets[key]

    def select(self, delta: int) -> None:
        if self.workers:
            ids = [w.id for w in self.workers]
            self.selected_id = ids[max(0, min(len(ids) - 1, ids.index(self.selected_id) + delta))]
            self.reveal()

    def scroll(self, delta: int, worker: Worker | None = None) -> None:
        """One wheel notch moves the given chat (default: the selected one) by WHEEL_ROWS; negative is older."""
        self.chat(-delta * WHEEL_ROWS, worker)

    def turn_page(self, delta: int) -> None:
        """Wheel away from any bubble: moves to the next or previous page, keeping the selection."""
        self._page = max(0, min(self.page() + delta, len(self.pages) - 1))

    def _cell_of(self, worker: Worker) -> tuple[int, int] | None:
        """The bubble width and height of a worker on the displayed page, if it is shown."""
        return next(((cell[2], cell[3]) for w, cell in zip(self.visible(), self._cells()) if w.id == worker.id), None)

    def chat(self, rows: int, worker: Worker | None = None) -> None:
        """Moves the chat of `worker` (default: the selected one) by `rows`: positive is older, negative is newer. Clamped at both ends."""
        worker = self.selected() if worker is None else worker
        size = self._cell_of(worker) if worker is not None else None
        if size is None:
            return
        total, keep = chat_geometry(worker, *size)
        value = max(0, min(max(0, total - keep), self.chat_scroll.get(worker.id, 0) + rows))
        self._store_chat(worker.id, value)
        self._chat_seen[worker.id] = total

    def chat_step(self) -> int:
        """Rows per Up/Down press: one less than the visible body of the selected bubble, at least 1."""
        worker = self.selected()
        size = self._cell_of(worker) if worker is not None else None
        keep = chat_geometry(worker, *size)[1] if size is not None else 3
        return max(1, keep - 1)

    def _store_chat(self, worker_id: str, value: int) -> None:
        if value:
            self.chat_scroll[worker_id] = value
        else:
            self.chat_scroll.pop(worker_id, None)

    def _chat_offset(self, worker: Worker, width: int, height: int) -> int:
        """The clamped offset of a bubble; when new lines arrive above a reader, the offset grows with them."""
        total, keep = chat_geometry(worker, width, height)
        seen = self._chat_seen.get(worker.id)
        value = self.chat_scroll.get(worker.id, 0)
        if value and seen is not None and total > seen:
            value += total - seen
        value = max(0, min(value, max(0, total - keep)))
        self._store_chat(worker.id, value)
        self._chat_seen[worker.id] = total
        return value

    def reveal(self) -> None:
        """Brings the stored page to the page holding the selected worker, if it has one."""
        index = self._selected_page()
        if index is not None:
            self._page = index

    def selected(self) -> Worker | None:
        return next((w for w in self.workers if w.id == self.selected_id), None)

    def _selected_page(self) -> int | None:
        for index, page in enumerate(self.pages):
            if any(w.id == self.selected_id for room in page for w in room.workers):
                return index
        return None

    def page(self) -> int:
        """The stored page, clamped to the pages that exist now."""
        self._page = max(0, min(self._page, len(self.pages) - 1))
        return self._page

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

    def click(self, col: int, row: int) -> Worker | None:
        """The worker to open for a click on this cell, now selected."""
        worker = self.worker_at(col, row)
        if worker is not None:
            self.selected_id = worker.id
        return worker

    def hover(self, col: int, row: int) -> None:
        """Mouse motion: a bubble under the pointer becomes the selected one; anything else keeps the selection."""
        worker = self.worker_at(col, row)
        if worker is not None:
            self.selected_id = worker.id

    def press(self) -> Worker | None:
        """Enter: when the selected worker is off the displayed page, only brings the page back."""
        index = self._selected_page()
        if index is not None and index != self.page():
            self._page = index
            return None
        return self.selected()

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
            desk = (col + width // 2 - props.DESK_W * props.SCALE // 2, (top + height) * 2 + 27)
            if actor.desk != desk:
                actor.place(desk)
                fresh.append(actor)
            actor.visitors, actor.target = 0, None
        by_id = {a.worker.id: a for a in actors}
        grids = {id(room): self._grid(room, [a for a in actors if room_of[a.worker.id] is room]) for room in page_rooms}
        for actor in actors:
            actor.goal = actor.stand_point
            room = room_of[actor.worker.id]
            grid = grids[id(room)]
            actor.router = grid.route
            door = room.clamp_foot(room.right - 12, 0)
            life = actor.life
            if life.kind == "out":
                actor.goal = door
                if actor not in fresh and not actor.seated and actor.foot == door:
                    actor.away = True
                elif actor in fresh:
                    actor.away = True
                continue
            if actor.away:
                actor.away, actor.seated, actor.foot = False, False, door
            if life.kind == "roam":
                actor.goal = grid.nearest_free(room.clamp_foot(room.left + int(life.spot[0] * (room.right - room.left)), room.floor_y + int(life.spot[1] * (room.bottom - room.floor_y))))
                continue
            if life.kind == "visit" and life.mate in actors and life.mate.visitors < len(SLOTS):
                dx, dy = SLOTS[life.mate.visitors]
                actor.goal = grid.nearest_free(room.clamp_foot(life.mate.desk[0] + dx, life.mate.desk[1] + dy))
                actor.target = life.mate
                life.mate.visitors += 1
                continue
            if actor.worker.state != "waiting":
                continue
            target = resolve_target(actor.worker, self.workers)
            host = by_id.get(target.id) if target else None
            if host is not None and host.visitors < len(SLOTS):
                dx, dy = SLOTS[host.visitors]
                actor.goal = grids[id(room_of[host.worker.id])].nearest_free(room_of[host.worker.id].clamp_foot(host.desk[0] + dx, host.desk[1] + dy))
                actor.target = host
                host.visitors += 1
        for actor in fresh:
            actor.settle()
        return actors, cells

    def _grid(self, room: rooms.Room, actors: list[Actor]) -> Grid:
        """Walkable floor of one room: inside its walls and around its desks. Cached by the room's layout."""
        desks = tuple(a.desk for a in actors)
        key = (room.x, room.row, room.width, room.height, room.bubble, desks)
        if key not in self._grids:
            if len(self._grids) >= BACKGROUND_CACHE:
                self._grids.clear()

            def blocked(x: int, y: int) -> bool:
                outside = not (room.left + 9 <= x <= room.right - 9 and room.floor_edge(x) < y <= room.bottom - 2)
                return outside or any(desk_blocks(desk, x, y) for desk in desks)

            self._grids[key] = Grid(self.cols, max(0, self.rows - 1) * 2, blocked)
        return self._grids[key]

    def step(self) -> None:
        self.tick += 1
        actors, _ = self._sync()
        for actor in actors:
            if not actor.away:
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
            text = "Aumente o terminal (mínimo 36x28)"
            frame.text(max(0, (self.cols - len(text)) // 2), self.rows // 2, text, (225, 228, 240), None)
            return frame
        actors, cells = self._sync()
        page_rooms = self._rooms()
        canvas = self._background(page_rooms).copy()
        items = [(a.desk[1] + 40, 0, i, a) for i, a in enumerate(actors)] + [(a.foot[1], 1, i, a) for i, a in enumerate(actors) if not a.seated and not a.away]
        for _, kind, _, actor in sorted(items, key=lambda item: item[:3]):
            (actor.draw_body if kind else actor.draw_station)(canvas, self.tick)
        for actor in actors:
            actor.draw_icons(canvas, self.tick)
        frame = Frame.from_canvas(canvas, self.cols, self.rows)
        for room in page_rooms:
            frame.text(room.sign_col, room.row, room.sign, INK, CREAM, True)
        positions = {w.id: i for i, w in enumerate(self.workers)}
        ring = None  # the selected bubble's ring, drawn after every bubble so nothing covers it.
        for actor, (col, top, width, height) in zip(actors, cells):
            worker = actor.worker
            color = RAINBOW[positions[worker.id] % len(RAINBOW)]
            tail = actor.desk[0] + props.SEAT_DX + 16
            offset = self._chat_offset(worker, width, height)
            draw_bubble(frame, col, top, width, height, worker, self.workers, color, tail, actor.note(), offset)
            if worker.id == self.selected_id:
                ring = (col, top, width, height, tail, color)
            if not actor.seated and not actor.away:
                hx, hy = actor.head()
                frame.text(hx + 5, hy // 2 - 1, f" {worker.item_label} ", (28, 24, 40), color, True)
        if ring is not None and self.show_selection:
            draw_selection(frame, *ring)
        if not self.workers:
            text = " Nenhum split recente "
            frame.text((self.cols - len(text)) // 2, self.rows // 2, text, INK, CREAM, True)
        self._footer(frame)
        return frame

    def _footer(self, frame: Frame) -> None:
        count = lambda *states: sum(w.state in states for w in self.workers)
        pages = max(1, len(self.pages))
        stats = f" {count('working', 'thinking')} rodando  {count('waiting', 'ask', 'blocked')} aguardando  {count('done')} concluidas  {count('failed')} falhas  |  "
        tail = f"  página {self.page() + 1}/{pages}"
        text = next((stats + option + tail for option in CONTROLS if len(stats + option + tail) <= self.cols), stats + CONTROLS[-1] + tail)
        if self.tick < self.notice_until:
            text = f" {self.notice}"
        frame.text(0, self.rows - 1, text.ljust(self.cols)[:self.cols], FOOTER_FG, FOOTER_BG)
