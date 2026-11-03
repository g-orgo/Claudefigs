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

from . import life
from .bubble import INK, clean
from .composer import COMPOSER_ROWS, MIN_ROWS, Composer, draw_composer
from .data import full_session_id
from .hall import BACK, WAREHOUSE, Hall, doors_of
from .model import Worker
from .scene import FOOTER_BG, FOOTER_FG, Scene
from .term import Frame

SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DISPATCH = os.path.join(SCRIPTS, "dispatch.py")
ROOM_BUSY = ("working", "thinking")
COPY_WORDING = re.compile(r"(?i)\b(copy|c[oó]pia|started a copy)\b")
BACK_LABEL, BACK_FILL = " < Voltar ", (232, 178, 92)  # the bubble look: wood gold, ink text


class Office:
    def __init__(self, cols: int, rows: int, sender=None, demo: bool = False):
        """`sender(argv, cwd)` runs one command and returns (returncode, output); the viewer injects it."""
        self.tick = 0
        self.cols, self.rows = cols, rows
        self.sender = sender
        self.demo = demo
        self.composer = Composer()
        self.results: queue.Queue = queue.Queue()
        self.inflight = False
        view_rows = self._view_rows(rows)
        self.scene = Scene(cols, view_rows)
        self.place = os.path.basename(os.getcwd().rstrip("/")) or "/"
        self.hall = Hall(cols, view_rows, False, self.place)
        self.warehouse = Hall(cols, view_rows, True, self.place)
        self.mode = "hall"
        self.door_key: str | None = None
        self.came_from = "hall"
        self.workers: list[Worker] = []
        self.set_workers([])

    @staticmethod
    def _view_rows(rows: int) -> int:
        """Rows left for the scene and the halls: the composer takes its own strip at the bottom."""
        return rows - COMPOSER_ROWS if rows >= MIN_ROWS else rows

    def composer_shown(self) -> bool:
        return self.rows >= MIN_ROWS

    def in_composer(self, row: int) -> bool:
        return self.composer_shown() and row >= self.rows - COMPOSER_ROWS

    def resize(self, cols: int, rows: int) -> None:
        self.cols, self.rows = cols, rows
        view_rows = self._view_rows(rows)
        self.scene.resize(cols, view_rows)
        self.hall.resize(cols, view_rows)
        self.warehouse.resize(cols, view_rows)

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

    def _room_ids(self) -> dict:
        if self.mode != "room":
            return {}
        return {w.id: room.group for room in self.scene._rooms() for w in room.workers}

    def step(self) -> None:
        self.tick += 1
        self.drain()
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
        view = self.view().render()
        if self.composer_shown():
            frame = Frame(self.cols, self.rows)
            frame.cells[:view.nrows] = view.cells
            for row in range(self.rows - COMPOSER_ROWS, self.rows):
                frame.text(0, row, " " * self.cols, FOOTER_FG, FOOTER_BG)
            hint = "Enter envia  Esc sai" if self.composer.focused else "Tab escreve"
            draw_composer(frame, self.rows - COMPOSER_ROWS, self.composer, self._destination(), hint, self.tick)
        else:
            frame = view
        button = self.back_button()
        if button is not None:
            col, row, _ = button
            frame.text(col, row, BACK_LABEL, INK, BACK_FILL, True)
        return frame

    def back_button(self) -> tuple[int, int, int] | None:
        """Where the Voltar button sits as (col, row, width): room at the left, warehouse centered; None in the hall."""
        width = len(BACK_LABEL)
        if self.mode == "room":
            return (1, 0, width)
        if self.mode == "warehouse":
            return (max(0, (self.cols - width) // 2), 0, width)
        return None

    def hits_back(self, col: int, row: int) -> bool:
        button = self.back_button()
        return button is not None and row == button[1] and button[0] <= col < button[0] + button[2]

    def arrows_scroll(self) -> bool:
        """In a room, Up and Down page the selected chat instead of selecting."""
        return self.mode == "room"

    def chat(self, rows: int) -> None:
        self.scene.chat(rows)

    def chat_step(self) -> int:
        return self.scene.chat_step()

    def _destination(self) -> str:
        if self.mode == "room":
            worker = self.scene.selected()
            return f"Para: {clean(worker.title)}" if worker else "Selecione um item"
        return f"Nova sessão em {self.place}"

    def paste(self, text: str) -> None:
        """A bracketed paste lands as one insert, and only while the field has focus."""
        if self.composer.focused:
            self.composer.insert(text)

    def submit(self) -> None:
        """Sends the draft: to the selected split inside a room, or as a new session in the hall and warehouse."""
        text = self.composer.text
        if not text.strip():
            return
        if self.inflight:
            self.notify("Aguarde o envio anterior")
            return
        prompt = " " + text if text.startswith("-") else text
        plan = None
        room: dict = {}
        if self.mode == "room":
            worker = self.scene.selected()
            if worker is None:
                self.notify("Selecione um item primeiro")
                return
            if worker.state in ROOM_BUSY:
                self.notify("Esta sessao esta rodando: espere terminar para enviar")
                return
            if worker.state == "waiting":
                self.notify("Este item ainda nao comecou")
                return
            session_id = full_session_id(worker.session_id)
            if not session_id:
                self.notify("Esta sessao ainda nao pode receber texto")
                return
            kind, title = "room", clean(worker.title)
            argv, cwd = ["claude", "--bg", "--resume", session_id, prompt], worker.cwd or None
            room = {"worker_id": worker.id, "attachable": worker.attachable}
        else:
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
        job = {"kind": kind, "text": text, "title": title, "plan": plan, **room}
        threading.Thread(target=self._run, args=(job, argv, cwd), daemon=True).start()

    def _write_plan(self, title: str, prompt: str) -> str:
        plan = {"cwd": os.getcwd(), "groups": [{"name": f"escritorio-{int(time.time())}", "title": title, "prompt": prompt}]}
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
            if not ok:
                self.notify("Nao foi possivel enviar")
                if not self.composer.text:
                    self.composer.text = job["text"]
                continue
            self.composer.clear()
            if job["kind"] == "hall":
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
        if key == WAREHOUSE:
            self.mode = "warehouse"
        elif key == BACK:
            self.mode = "hall"
        else:
            self.came_from, self.door_key, self.mode = self.mode, key, "room"
            self.scene.set_workers([w for w in self.workers if w.room_key == key])

    def click(self, col: int, row: int) -> Worker | None:
        """Enters what was clicked; returns a worker only when a bubble was clicked inside a room."""
        if self.mode == "room":
            return self.scene.click(col, row)
        key = self.view().key_at(col, row)
        if key is not None:
            self.view().selected_key = key
            self._go(key)
        return None

    def scroll(self, delta: int) -> None:
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
        if self.mode == "room":
            self.mode, self.door_key = self.came_from, None
        elif self.mode == "warehouse":
            self.mode = "hall"

    def toggle_warehouse(self) -> None:
        self.mode = "hall" if self.mode == "warehouse" else "warehouse"
