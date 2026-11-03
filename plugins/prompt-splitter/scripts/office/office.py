"""Navigation of the viewer: the hall of the working directory, the warehouse and the room behind a door."""
import os

from . import life
from .hall import BACK, WAREHOUSE, Hall, doors_of
from .model import Worker
from .scene import Scene
from .term import Frame


class Office:
    def __init__(self, cols: int, rows: int):
        self.tick = 0
        self.scene = Scene(cols, rows)
        place = os.path.basename(os.getcwd().rstrip("/")) or "/"
        self.hall = Hall(cols, rows, False, place)
        self.warehouse = Hall(cols, rows, True, place)
        self.mode = "hall"
        self.door_key: str | None = None
        self.came_from = "hall"
        self.workers: list[Worker] = []
        self.set_workers([])

    def resize(self, cols: int, rows: int) -> None:
        self.scene.resize(cols, rows)
        self.hall.resize(cols, rows)
        self.warehouse.resize(cols, rows)

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
        return self.view().render()

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

    def press(self) -> Worker | None:
        """Enter: goes through the selected door, or returns the selected split inside a room."""
        if self.mode == "room":
            return self.scene.press()
        self._go(self.view().selected_key)
        return None

    def back(self) -> None:
        if self.mode == "room":
            self.mode, self.door_key = self.came_from, None
        elif self.mode == "warehouse":
            self.mode = "hall"

    def toggle_warehouse(self) -> None:
        self.mode = "hall" if self.mode == "warehouse" else "warehouse"
