"""Navigation of the viewer: the hall of the working directory, the warehouse and the room behind a door."""
import json
import os
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time

from . import hallart, life, props, sprites
from .bubble import clean
from .clipboard import UNAVAILABLE, read_clipboard
from .composer import (BACK_H, BACK_W, MIN_ROWS, PANEL_ROWS_SHORT, PLATE_ROWS, POPUP_ROWS, TEXT_TOP_ROWS, Composer, draw_back_button,
                       draw_composer, draw_popup, field_geometry, panel_rows)
from .data import full_session_id
from .hall import BACK, WAREHOUSE, Hall, doors_of
from .hallart import BAY_W
from .hallplan import WIDE_COLS, WIDE_ROWS
from .model import Worker
from .notice import Notice, draw as draw_notice, limit_content, place as place_notice, resume_content
from .question import Asking
from .scene import FOOTER_BG, FOOTER_FG, Scene
from .term import Frame

SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DISPATCH = os.path.join(SCRIPTS, "dispatch.py")
FLOOR_GAP = 2  # rows of floor kept between the box and the footer in the wide hall.
EXTRA_FLOOR_MARGIN = 1  # rows of floor above and below the box where the floor is extended for it.
ROOM_BUSY = ("working", "thinking")
LIMIT_WINDOW_MS = 24 * 3600 * 1000  # a usage-limit stop older than this is not resumed.
WEEKLY_WINDOW_MS = 8 * 24 * 3600 * 1000  # weekly limits wait longer for their reset.
UNKNOWN_RESET_MS = 15 * 60 * 1000  # without a known reset time, resume after this long.
RESUME_PROMPT = "Continue de onde parou: o limite de uso foi liberado."
COPY_WORDING = re.compile(r"(?i)\b(copy|c[oó]pia|started a copy)\b")
BACK_GAP = 1  # cells between the back button and the box.
BOX_TOP_ROWS = 2  # rows of name plate above the box's body; the button centers on the body.
MIN_BOX_WIDTH = 24  # draw_composer draws nothing narrower than this.
ASK_HINTS = ("Setas escolhem  Espaco marca  Enter confirma  Tab troca  Ctrl+X adia",
             "Setas escolhem  Enter confirma  Ctrl+X adia", "Enter confirma  Ctrl+X adia", "Enter confirma")


class Office:
    def __init__(self, cols: int, rows: int, sender=None, demo: bool = False):
        """`sender(argv, cwd)` runs one command and returns (returncode, output); the viewer injects it."""
        self.tick = 0
        self.cols, self.rows = cols, rows
        self.sender = sender
        self.demo = demo
        self.draft = Composer()  # the box's own draft; a pending question brings its own field.
        self.asking: Asking | None = None  # the session questions the box shows now
        self.postponed: set[tuple] = set()  # Asking keys put aside with Ctrl+X; entering their room brings them back.
        self.sent_asks: set[str] = set()  # asks already answered from here, hidden until the transcript catches up.
        self.told: set[tuple] = set()  # Asking keys already announced while the draft held the box.
        self._body = 0  # rows the question block adds to the box.
        self._floor = None
        self.results: queue.Queue = queue.Queue()
        self.inflight = False
        self.resumed: set[tuple] = set()  # (worker id, limit_at_ms) already resumed or being resumed.
        self.last_resume: tuple[int, int] | None = None  # (sent, failed) of the last resume batch.
        self.notice = Notice()  # the usage-limit pop-up.
        self.seen_limits: set[tuple] = set()  # (worker id, limit_at_ms) the pop-up already announced.
        self._armed = False  # the first non-empty set_workers counts as the viewer coming back.
        view_rows = self._view_rows()
        self.scene = Scene(cols, view_rows)
        self.place = os.path.basename(os.getcwd().rstrip("/")) or "/"
        self.hall = Hall(cols, self._hall_rows(), False, self.place)
        self.warehouse = Hall(cols, view_rows, True, self.place)
        self.mode = "hall"
        self.back_hovered = False
        self.pointer: tuple[int, int] | None = None  # last mouse cell, for the wheel over a bubble while typing.
        self.door_key: str | None = None
        self.came_from = "hall"
        self.workers: list[Worker] = []
        self.set_workers([])
        self._sync_covered()

    @property
    def composer(self) -> Composer:
        """The field keys go to: the pending question's answer when one is shown, else the draft."""
        return self.asking.composer if self.asking is not None else self.draft

    def _panel_rows(self) -> int:
        """Rows of the box: one line of answer under the question block, or the usual draft box."""
        return panel_rows(self.rows) if self.asking is None else PANEL_ROWS_SHORT + self._body

    def _view_rows(self) -> int:
        """Rows of a view with desks or doors all over it: the floor grows below it for the box, if the view still fits."""
        left = self.rows - self._panel_rows() - 2 * EXTRA_FLOOR_MARGIN
        return left if self.composer_shown() and left >= MIN_ROWS else self.rows

    def _hall_rows(self) -> int:
        """The wide hall has open floor for the box, so it keeps the whole height."""
        return self.rows if self._hall_is_wide() else self._view_rows()

    def _hall_is_wide(self) -> bool:
        return self.cols >= WIDE_COLS and self.rows >= WIDE_ROWS

    def _sync_covered(self) -> None:
        """Tells the views how many rows the box covers above their footer, for what they center down there."""
        for view in (self.hall, self.warehouse):
            view.covered_rows = self._panel_rows() + FLOOR_GAP if self.composer_shown() and view.rows == self.rows else 0

    def composer_shown(self) -> bool:
        return self.rows >= MIN_ROWS

    def field_rect(self) -> tuple[int, int, int, int]:
        """Where the box sits as (col, top, width, rows): on the open floor of the wide hall, else above the footer."""
        rows = self._panel_rows()
        view = self.view()
        room = None
        top = self.rows - 1 - rows
        if view.rows < self.rows:
            top -= EXTRA_FLOOR_MARGIN
        elif view is self.hall and self._hall_is_wide():
            top -= FLOOR_GAP
            free = [panel for panel in self.hall.plan.panels if panel.free]
            if free:
                left = max(panel.x + BAY_W for panel in free if panel.x < self.cols // 2)
                room = min(panel.x for panel in free if panel.x >= self.cols // 2) - left - 4
        width, col = field_geometry(self.cols, room)
        side = BACK_W + BACK_GAP + 1
        if self.mode != "hall" and col < side:  # no free floor at the left: the box gives way to the button.
            col, width = side, self.cols - side - 2
        return col, top, width, rows

    def in_composer(self, col: int, row: int) -> bool:
        if not self.composer_shown():
            return False
        left, top, width, rows = self.field_rect()
        return left <= col < left + width and top <= row < top + rows

    def resize(self, cols: int, rows: int) -> None:
        self.cols, self.rows = cols, rows
        view_rows = self._view_rows()
        self.scene.resize(cols, view_rows)
        self.hall.resize(cols, self._hall_rows())
        self.warehouse.resize(cols, view_rows)
        self._sync_covered()

    def view(self):
        return {"hall": self.hall, "warehouse": self.warehouse, "room": self.scene}[self.mode]

    def set_workers(self, workers: list[Worker]) -> None:
        self.workers = workers
        self.scene.register(workers)
        self.hall.actors = self.warehouse.actors = self.scene.actors
        self.hall.set_doors(doors_of([w for w in workers if w.in_cwd]))
        self.warehouse.set_doors(doors_of(workers))
        if self.mode == "room":
            inside = [w for w in workers if w.room_key == self.door_key]
            if inside:
                self.scene.set_workers(inside)
            else:
                self.back()
        self._refresh_asking()
        self._announce_limits()
        if workers and not self._armed:
            self._armed = True
            self.user_active()

    @staticmethod
    def _key_of(worker: Worker) -> tuple:
        return (worker.id, tuple(dict.fromkeys(q.ask for q in worker.questions)))

    def _asks(self, worker: Worker | None) -> bool:
        """The worker has questions not answered from here nor put aside."""
        return (worker is not None and bool(worker.questions) and not any(q.ask in self.sent_asks for q in worker.questions)
                and self._key_of(worker) not in self.postponed)

    def _askers(self) -> list[Worker]:
        """Every session waiting on a question, newest question first, wherever it sits."""
        found = [w for w in self.workers if self._asks(w)]
        return sorted(found, key=lambda w: -max(q.asked_ms for q in w.questions))

    def _refresh_asking(self) -> None:
        """Picks the question the box shows: the one being answered, the selected split's in a room, else the newest."""
        askers = self._askers()
        by_key = {self._key_of(w): w for w in askers}
        current = self.asking
        if current is not None and current.key in by_key:
            current.worker = by_key[current.key]
            selected = self.scene.selected() if self.mode == "room" else None
            if current.composer.focused or not self._asks(selected) or self._key_of(selected) == current.key:
                return self._fit()
            askers = [selected]
        elif current is not None:
            self.asking = None
        if not askers:
            return self._fit()
        selected = self.scene.selected() if self.mode == "room" else None
        worker = selected if self._asks(selected) else askers[0]
        key = self._key_of(worker)
        if self.draft.focused and self.draft.text and self.asking is None:
            if key not in self.told:  # never pull the box away from a draft being typed.
                self.told.add(key)
                self.notify(f"{clean(worker.title)} fez uma pergunta: Esc para ver")
            return self._fit()
        focused = self.draft.focused or (current is not None and current.composer.focused)
        self.draft.blur()
        self.asking = Asking(worker)
        if focused:
            self.asking.composer.focus()
        self._fit()

    def _fit(self) -> None:
        """Resizes the views when the question block changes the box's height."""
        body = 0
        if self.asking is not None:
            block = self.asking.block_rows(self.field_rect()[2])
            body = min(block, max(3, self.rows // 4)) + 1  # one spare row before the answer line.
        if body != self._body:
            self._body = body
            self.resize(self.cols, self.rows)

    def answer_key(self, key: str) -> bool:
        """Keys of a shown question; False lets the key reach the field as usual."""
        if self.asking is None:
            return False
        if key == "\x18":
            self.postpone()
            return True
        if not self.composer.focused or self.popup_items():
            return False
        if key in ("\x1b[A", "\x1b[B"):
            self.asking.move(-1 if key == "\x1b[A" else 1)
        elif key == "\t":
            self.asking.next()
        elif key == " " and not self.composer.text:
            self.asking.toggle()
        else:
            return False
        return True

    def postpone(self) -> None:
        """Ctrl+X: puts the shown question aside and shows the next one, or the draft."""
        if self.asking is None:
            return
        self.postponed.add(self.asking.key)
        self.asking = None
        self._refresh_asking()

    def question_click(self, col: int, row: int) -> bool:
        """A click on the question block: brings a question forward or takes an option."""
        hit = self.asking.row_at(col, row) if self.asking is not None and self.composer_shown() else None
        if hit is None:
            return False
        self.composer.focus()
        if self.asking.pick(*hit):
            self._send_answer()
        return True

    def _send_answer(self) -> None:
        """Sends every answer of the shown question to its session, like a room send."""
        asking = self.asking
        worker = asking.worker
        if self.inflight:
            self.notify("Aguarde o envio anterior")
            return
        if worker.state in ROOM_BUSY or worker.state == "waiting":
            self.notify("Esta sessao voltou a rodar")
            return
        session_id = "" if self.demo else full_session_id(worker.session_id)
        if not self.demo and not session_id:
            self.notify("Esta sessao ainda nao pode receber a resposta")
            return
        self.sent_asks.update(asking.asks)
        self.asking = None
        self._refresh_asking()
        if self.demo:
            self.notify("Demo: nada foi enviado")
            return
        self.inflight = True
        job = {"kind": "answer", "draft": None, "title": clean(worker.title), "plan": None, "worker_id": worker.id,
               "attachable": worker.attachable, "asking": asking}
        self.notify("Enviando...")
        argv = ["claude", "--bg", "--resume", session_id, asking.message()]
        threading.Thread(target=self._run, args=(job, argv, worker.cwd or None), daemon=True).start()

    def _room_ids(self) -> dict:
        if self.mode != "room":
            return {}
        return {w.id: room.group for room in self.scene._rooms() for w in room.workers}

    def step(self) -> None:
        self.tick += 1
        self.drain()
        self._refresh_asking()
        room_ids = self._room_ids()
        actors = [self.scene.actors[w.id] for w in self.workers]
        life.advance(actors, self.tick, room_ids)
        hall_keys = set(self.hall.visible_keys()) if self.mode == "hall" else set()
        for actor in actors:
            if actor.worker.id in room_ids:
                continue  # the room's own step walks it to the door and back.
            if actor.life.kind == "out":
                actor.away = True
            elif actor.away and actor.worker.room_key not in hall_keys:
                actor.away, actor.hall_foot = False, None
        if self.mode == "room":
            self.scene.tick = self.tick - 1
            self.scene.step()
        else:
            self.view().tick = self.tick - 1
            self.view().step()

    def render(self) -> Frame:
        self.view().show_selection = not (self.composer.focused or self.composer.hovered or self.back_hovered)
        frame = self.view().render()
        if self.composer_shown():
            if frame.nrows < self.rows:
                frame = self._with_strip(frame)
            col, top, width, rows = self.field_rect()
            if self.asking is not None:
                hints = ASK_HINTS if self.composer.focused else ("Tab responde",)
                draw_composer(frame, top, col, width, rows, self.composer, self._destination(), hints, self.tick,
                              self._body, "Aperte Tab para responder...", "ou escreva outra resposta")
                self.asking.draw(frame, col, top + PLATE_ROWS + TEXT_TOP_ROWS, width, self._body - 1)
            else:
                hints = (
                    ("@ arquivo  / comando  Ctrl+V imagem  Enter envia  Esc sai", "@ arquivo  / comando  Enter envia", "Enter envia  Esc sai", "Enter envia")
                    if self.composer.focused else ("Tab escreve",) if self.composer.text else ()
                )
                draw_composer(frame, top, col, width, rows, self.composer, self._destination(), hints, self.tick)
            items = self.popup_items()
            rect = self.popup_rect(len(items))
            if rect is not None:
                left, popup_top, popup_w, count = rect
                draw_popup(frame, left, popup_top, popup_w, items[:count], self.composer.highlight)
        button = self.back_button()
        if button is not None:
            col, row, _, _ = button
            draw_back_button(frame, col, row, self.back_hovered)
        placed = self.notice_place()
        if placed is not None:
            draw_notice(frame, placed, self.notice.plate)  # last, so the pop-up covers what is under it.
        return frame

    def _with_strip(self, view: Frame) -> Frame:
        """Grows the view's floor down to the footer, so the box floats on it and the footer stays on the last row."""
        frame = Frame(self.cols, self.rows)
        frame.cells[:view.nrows - 1] = view.cells[:-1]
        floor = self._floor_cells()
        frame.cells[view.nrows - 1:self.rows - 1] = [line[:] for line in floor[view.nrows - 1:self.rows - 1]]
        frame.cells[self.rows - 1] = view.cells[-1]
        return frame

    def _floor_cells(self) -> list:
        """The current view's floor tiles at full height; they depend only on x and y, so they meet the view's own."""
        key = (self.mode == "warehouse", self.cols, self.rows)
        if self._floor is None or self._floor[0] != key:
            # The warehouse lane marking sits at the canvas bottom: spare rows push it out of the frame.
            canvas = sprites.Canvas(self.cols, self.rows * 2 + 8)
            (hallart.draw_warehouse_floor if key[0] else props.draw_corridor)(canvas)
            self._floor = (key, Frame.from_canvas(canvas, self.cols, self.rows).cells)
        return self._floor[1]

    def back_button(self) -> tuple[int, int, int, int] | None:
        """Where the back button sits as (col, row, width, height): left of the box, vertically centered on its body; None in the hall.

        Without a box to sit beside it falls back to the top: room at the left, warehouse centered.
        The row is clipped so the whole button stays on screen."""
        if self.mode != "hall" and self.composer_shown():
            col, top, field, rows = self.field_rect()
            if field >= MIN_BOX_WIDTH:
                row = top + BOX_TOP_ROWS + (rows - BOX_TOP_ROWS - BACK_H) // 2
                return (max(0, col - BACK_W - BACK_GAP), max(0, min(row, self.rows - BACK_H)), BACK_W, BACK_H)
        if self.mode == "room":
            return (1, 0, BACK_W, BACK_H)
        if self.mode == "warehouse":
            return (max(0, (self.cols - BACK_W) // 2), 0, BACK_W, BACK_H)
        return None

    def hits_back(self, col: int, row: int) -> bool:
        button = self.back_button()
        return button is not None and button[0] <= col < button[0] + button[2] and button[1] <= row < button[1] + button[3]

    def arrows_scroll(self) -> bool:
        """In a room, Up and Down page the selected chat instead of selecting."""
        return self.mode == "room"

    def chat(self, rows: int) -> None:
        self.scene.chat(rows)

    def chat_step(self) -> int:
        return self.scene.chat_step()

    def _destination(self) -> str:
        if self.asking is not None:
            others = len(self._askers()) - 1
            return f"Pergunta de: {clean(self.asking.worker.title)}" + (f" (+{others})" if others > 0 else "")
        if self.mode == "room":
            return "Nova sessão nesta sala"
        return "Nova sessão"

    def _suggest_cwd(self) -> str:
        """Directory the suggestions come from: the selected worker's in a room, the viewer's otherwise."""
        worker = self.scene.selected() if self.mode == "room" else None
        return worker.cwd if worker is not None and worker.cwd else os.getcwd()

    def popup_items(self) -> list[tuple[str, str, str]]:
        return self.composer.suggestions(self._suggest_cwd()) if self.composer.focused else []

    def popup_rect(self, count: int) -> tuple[int, int, int, int] | None:
        """(left, top border row, width, items) of the suggestion popup: the box's width, one gap row above the box,
        and two border rows around the items; never over the view's top edge."""
        if not count or not self.composer_shown():
            return None
        left, top, width, _ = self.field_rect()
        shown = min(POPUP_ROWS, count, top - 3)
        return (left, top - shown - 3, width, shown) if shown > 0 else None

    def popup_row_at(self, col: int, row: int) -> int | None:
        rect = self.popup_rect(len(self.popup_items()))
        if rect is None:
            return None
        left, top, width, items = rect
        inside = left <= col < left + width and top + 1 <= row <= top + items
        return row - top - 1 if inside else None

    def popup_move(self, delta: int) -> None:
        self.composer.move(delta, self._suggest_cwd())

    def popup_accept(self, index: int | None = None) -> bool:
        return self.composer.accept(self._suggest_cwd(), index)

    def popup_dismiss(self) -> bool:
        return self.composer.dismiss(self._suggest_cwd())

    def paste(self, text: str) -> None:
        """A bracketed paste lands as one insert, and only while the field has focus."""
        if self.composer.focused:
            self.composer.paste(text)

    def paste_clipboard(self) -> None:
        """Ctrl+V while the field has focus: attaches a clipboard image, or inserts clipboard text."""
        if not self.composer.focused:
            return
        kind, value = read_clipboard()
        if kind == "image":
            self.composer.attach(value)
        elif kind == "text":
            self.composer.paste(value)
        elif kind == UNAVAILABLE:
            self.notify("Area de transferencia indisponivel")

    def submit(self) -> None:
        """Sends the draft: to the selected split inside a room, or as a new session in the hall and warehouse."""
        if self.asking is not None:
            taken = self.asking.confirm()
            if taken is None:
                self.notify("Escolha uma opcao ou escreva a resposta")
            elif taken:
                self._send_answer()
            return
        text = self.composer.text
        if not text.strip():
            return
        if self.inflight:
            self.notify("Aguarde o envio anterior")
            return
        prompt = self.composer.prompt_text()
        prompt = " " + prompt if prompt.startswith("-") else prompt
        if self.mode == "room":
            self._submit_room(prompt)
            return
        plan = None
        kind, title = "hall", text.strip()[:60]
        argv, cwd = None, None
        if self.demo:
            self.composer.clear()
            self.notify("Demo: nada foi enviado")
            return
        if kind == "hall":
            plan = self._write_plan(title, prompt)
            argv = [sys.executable, DISPATCH, plan]
        self.inflight = True
        job = {"kind": kind, "draft": self.composer.state(), "title": title, "plan": plan}
        self.composer.clear()  # instant feedback: the draft leaves now and comes back only if the send fails.
        self.notify("Enviando...")
        threading.Thread(target=self._run, args=(job, argv, cwd), daemon=True).start()

    def _room_workers(self) -> list[Worker]:
        return [w for w in self.workers if w.room_key == self.door_key]

    def _submit_room(self, prompt: str) -> None:
        """Starts ONE new session for the draft in the room's project, under the room's parent so it shows in the room.

        A room message is a new request, never a broadcast: it must not be resumed into every item of the room.
        When the request has several independent items, the new session splits them itself through prompt-splitter.
        """
        room = self._room_workers()
        if not room:
            self.notify("Sala vazia: nada foi enviado")
            return
        if self.demo:
            self.composer.clear()
            self.notify("Demo: nada foi enviado")
            return
        cwd = room[0].cwd or os.getcwd()
        parent = next((w.parent for w in room if w.parent), "")
        title = self.composer.text.strip()[:60]
        plan = self._write_plan(title, prompt, cwd)
        argv = [sys.executable, DISPATCH, plan] + (["--parent", parent] if parent else [])
        job = {"kind": "hall", "draft": self.composer.state(), "title": title, "plan": plan}
        self.inflight = True
        self.composer.clear()  # instant feedback: the draft comes back only if the send fails.
        self.notify("Enviando...")
        threading.Thread(target=self._run, args=(job, argv, cwd), daemon=True).start()

    def _limit_recent(self, worker: Worker, now: float) -> bool:
        window = WEEKLY_WINDOW_MS if worker.limit == "weekly" else LIMIT_WINDOW_MS
        return bool(worker.limit) and now - worker.limit_at_ms <= window

    def limited_workers(self) -> list[Worker]:
        """Recent usage-limit stops not handled by auto-resume yet; the pop-up reads this."""
        now = time.time() * 1000
        return [w for w in self.workers if self._limit_recent(w, now) and (w.id, w.limit_at_ms) not in self.resumed]

    def _announce_limits(self) -> None:
        """Shows the pop-up when a limited session appears under a key not seen before; the first load counts."""
        limited = self.limited_workers()
        keys = {(w.id, w.limit_at_ms) for w in limited}
        fresh = keys - self.seen_limits
        self.seen_limits |= keys
        if fresh:
            self.notice.show(*limit_content(limited), self.tick)

    def notice_place(self):
        """Where the pop-up is drawn now, or None when it is hidden."""
        if not self.notice.visible(self.tick):
            return None
        return place_notice(self.cols, self.rows, self.notice.lines)

    def notice_click(self, col: int, row: int) -> bool:
        """A click inside the pop-up closes it; True means the click is consumed."""
        placed = self.notice_place()
        if placed is None or not (placed.col <= col < placed.col + placed.width and placed.top <= row < placed.top + placed.rows):
            return False
        self.notice.close()
        return True

    def notice_dismiss(self) -> bool:
        """Esc closes the pop-up; True means the key is consumed."""
        if self.notice_place() is None:
            return False
        self.notice.close()
        return True

    def _resume_due(self, now: float) -> list[Worker]:
        due = []
        for worker in self.workers:
            if not self._limit_recent(worker, now) or (worker.id, worker.limit_at_ms) in self.resumed:
                continue
            if worker.state in ROOM_BUSY or worker.state == "waiting" or not full_session_id(worker.session_id):
                continue
            if worker.limit_reset_ms > 0:
                resettled = now >= worker.limit_reset_ms
            else:
                resettled = now - worker.limit_at_ms >= UNKNOWN_RESET_MS
            if resettled:
                due.append(worker)
        return due

    def user_active(self) -> None:
        """Resumes in one batch the sessions whose usage limit has reset; called on screen changes and input."""
        if self.demo or self.inflight:
            return
        due = self._resume_due(time.time() * 1000)
        if not due:
            return
        targets = []
        for worker in due:
            key = (worker.id, worker.limit_at_ms)
            self.resumed.add(key)
            targets.append({"worker_id": worker.id, "session_id": full_session_id(worker.session_id), "cwd": worker.cwd,
                            "attachable": worker.attachable, "title": clean(worker.title), "key": key})
        job = {"kind": "resume", "batch": True, "draft": None, "prompt": RESUME_PROMPT, "targets": targets,
               "total": len(targets), "counts": {"busy": 0, "waiting": 0, "no_session": 0}}
        self.inflight = True
        threading.Thread(target=self._run_batch, args=(job,), daemon=True).start()

    def _run_batch(self, job: dict) -> None:
        """Sends the batch one target after another, rechecking each target right before its own send."""
        outcomes = []
        for target in job["targets"]:
            outcome = {"worker_id": target["worker_id"], "ok": False, "copied": False, "skipped": False}
            try:
                if self._busy(target["worker_id"]):
                    outcome["skipped"] = True  # started or ended in the meantime: never stopped or resumed.
                else:
                    if target["attachable"]:
                        try:  # an idle or done session must be stopped before a resume continues it under the same id.
                            subprocess.run(["claude", "stop", target["worker_id"]], capture_output=True, text=True, timeout=30)
                        except Exception:  # already exited or failed: the resume still runs.
                            pass
                    code, output = self.sender(["claude", "--bg", "--resume", target["session_id"], job["prompt"]], target["cwd"] or None)
                    outcome["ok"] = code == 0
                    outcome["copied"] = bool(COPY_WORDING.search(output or ""))
            except Exception:  # a launch failure, timeout included, only means this target did not get the text.
                outcome["ok"] = False
            outcomes.append(outcome)
        job["outcomes"] = outcomes
        self.results.put((job, any(o["ok"] for o in outcomes), ""))

    def _finish_batch(self, job: dict) -> None:
        outcomes = job["outcomes"]
        sent = sum(o["ok"] for o in outcomes)
        copied = sum(o["copied"] for o in outcomes)
        failed = sum(1 for o in outcomes if not o["ok"] and not o["skipped"])
        skipped = sum(o["skipped"] for o in outcomes)
        if job["kind"] == "resume":
            keys = {t["worker_id"]: t["key"] for t in job["targets"]}
            for outcome in outcomes:
                if not outcome["ok"]:
                    self.resumed.discard(keys.get(outcome["worker_id"]))  # retried on the next activity.
            self.last_resume = (sent, failed)
            content = resume_content(sent, failed)
            if content is not None:
                self.notice.show(*content, self.tick)
            return
        if sent == 0:
            self.notify("Nenhum item da sala pode receber agora" if skipped and not failed else "Nao foi possivel enviar")
            if not self.composer.text:
                self.composer.restore(job["draft"])  # nothing went out: the draft comes back.
            return
        total, counts = job["total"], job["counts"]
        if sent == total:
            message = "Enviado para o item da sala" if total == 1 else f"Enviado para os {total} itens da sala"
        else:
            parts = [f"{counts['busy'] + skipped} rodando", f"{counts['waiting']} aguardando", f"{counts['no_session']} sem sessao"]
            detail = ", ".join(part for part in parts if not part.startswith("0 "))
            message = f"Enviado para {sent} de {total} itens" + (f" ({detail})" if detail else "")
        if failed:
            message += f"; {failed} falharam"
        if copied:
            message += f"; {copied} continuaram em copia"
        self.notify(message)

    def _write_plan(self, title: str, prompt: str, cwd: str | None = None) -> str:
        plan = {"cwd": cwd or os.getcwd(), "groups": [{"name": f"escritorio-{int(time.time())}", "title": title, "prompt": prompt}]}
        fd, path = tempfile.mkstemp(suffix=".json", prefix="office-plan-")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(plan, handle, ensure_ascii=False)
        return path

    def _busy(self, worker_id: str) -> bool:
        """Rechecked right before a room send: a session that is running or not started is never stopped or resumed."""
        worker = next((w for w in self.workers if w.id == worker_id), None)
        return worker is None or worker.state in ROOM_BUSY or worker.state == "waiting"

    def _run(self, job: dict, argv: list, cwd) -> None:
        ok, output = False, ""
        try:
            if job.get("worker_id") is not None:
                if self._busy(job["worker_id"]):
                    raise RuntimeError("session is busy")
                if job.get("attachable"):
                    try:  # an idle or done session must be stopped before a resume continues it under the same id.
                        subprocess.run(["claude", "stop", job["worker_id"]], capture_output=True, text=True, timeout=30)
                    except Exception:  # already exited or failed: the resume still runs.
                        pass
            code, output = self.sender(argv, cwd)
            ok = code == 0
        except Exception:  # any launch failure, timeout included, only means the send did not happen.
            ok = False
        finally:
            if job["plan"] and os.path.exists(job["plan"]):
                os.remove(job["plan"])
        self.results.put((job, ok, output))

    def drain(self) -> None:
        """Applies the outcome of finished sends; runs on the UI thread."""
        while True:
            try:
                job, ok, output = self.results.get_nowait()
            except queue.Empty:
                return
            self.inflight = False
            if job.get("batch"):
                self._finish_batch(job)
                continue
            if not ok:
                self.notify("Nao foi possivel enviar")
                if job["kind"] == "answer":
                    asking = job["asking"]
                    self.sent_asks.difference_update(asking.asks)
                    if self.asking is None:
                        self.asking = asking  # the answers come back, ready to send again.
                        self._fit()
                elif not self.composer.text:
                    self.composer.restore(job["draft"])
                continue
            if job["kind"] == "answer":
                self.notify(f"Resposta enviada para {job['title']}")
            elif job["kind"] == "hall":
                self.notify("Nova sessao iniciada")
            elif COPY_WORDING.search(output or ""):
                self.notify("A sessao estava ativa: continuou em uma copia")
            else:
                self.notify(f"Enviado para {job['title']}")

    def select(self, delta: int) -> None:
        self.view().select(delta)

    def selected(self) -> Worker | None:
        return self.scene.selected() if self.mode == "room" else None

    def notify(self, text: str) -> None:
        self.view().notify(text)

    def _go(self, key: str) -> None:
        self.user_active()
        if key == WAREHOUSE:
            self.mode = "warehouse"
        elif key == BACK:
            self.mode = "hall"
        else:
            self.came_from, self.door_key, self.mode = self.mode, key, "room"
            inside = [w for w in self.workers if w.room_key == key]
            self.scene.set_workers(inside)
            self.postponed -= {self._key_of(w) for w in inside}  # questions put aside come back in their room.

    def click(self, col: int, row: int) -> Worker | None:
        """Enters what was clicked; returns a worker only when a bubble was clicked inside a room."""
        if self.mode == "room":
            return self.scene.click(col, row)
        key = self.view().key_at(col, row)
        if key is not None:
            self.view().selected_key = key
            self._go(key)
        return None

    def hover(self, col: int, row: int) -> None:
        """Mouse motion: moves the selection to what is under the pointer, unless a draft or the Voltar button holds it."""
        self.pointer = (col, row)
        self.composer.hovered = self.in_composer(col, row)
        self.back_hovered = self.hits_back(col, row)
        if self.composer.focused or self.composer.hovered or self.back_hovered:
            return  # in a room the composer's destination is the selected worker, so a draft must not change it.
        self.view().hover(col, row)

    def scroll(self, delta: int) -> None:
        """Wheel in a room: scrolls the bubble under the pointer; anywhere else it turns the page."""
        if self.mode == "room" and self.pointer is not None:
            covered = self.in_composer(*self.pointer) or self.hits_back(*self.pointer)
            worker = None if covered else self.scene.worker_at(*self.pointer)
            if worker is not None:
                self.scene.scroll(delta, worker)  # never changes the selection, which a draft may be aimed at.
            else:
                self.scene.turn_page(delta)
            return
        self.view().scroll(delta)

    def press(self) -> Worker | None:
        """Enter: goes through the selected door, or returns the selected split inside a room."""
        if self.mode == "room":
            return self.scene.press()
        view = self.view()
        if not view.on_page(view.selected_key):
            view.reveal()  # off the displayed page: only bring the page back.
            return None
        self._go(view.selected_key)
        return None

    def back(self) -> None:
        self.user_active()
        if self.mode == "room":
            self.mode, self.door_key = self.came_from, None
        elif self.mode == "warehouse":
            self.mode = "hall"

    def toggle_warehouse(self) -> None:
        self.user_active()
        self.mode = "hall" if self.mode == "warehouse" else "warehouse"
