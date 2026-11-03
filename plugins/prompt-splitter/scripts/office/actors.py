"""Behaviour of the office characters: where each one goes and how it animates, per split state."""
import zlib

from . import props, sprites
from .life import Life, work_glance
from .model import Worker

BEAT = 16  # the waiter/target interaction has three beats of this many ticks.
STAND = (36, 6)  # foot point beside the own desk, relative to its corner.
SLOTS = [(46, 26), (16, 30), (-8, 26), (46, 6)]  # foot points around the desk of the awaited worker.
POSE = {"code": "type", "term": "type", "web": "type", "doc": "read", "delegate": "phone"}
SCREEN = {"code": "code", "term": "term", "web": "web", "doc": "doc", "delegate": "term"}
CHAIR = (90, 96, 130)
BODY_H = 23


def resolve_target(worker: Worker, workers: list[Worker]) -> Worker | None:
    """The worker actually holding this one up: follows chains of waiters until one that is not waiting."""
    group = {w.index: w for w in workers if w.group == worker.group}
    seen = {worker.id}
    current = worker
    while True:
        pending = [group[i] for i in current.after if i in group and group[i].state != "done"]
        if not pending or pending[0].id in seen:
            return None
        if pending[0].state != "waiting":
            return pending[0]
        current = pending[0]
        seen.add(current.id)


class Actor:
    def __init__(self, worker: Worker, look: sprites.Look):
        self.worker, self.look = worker, look
        self.seed = zlib.crc32(worker.id.encode())
        self.desk = (0, 0)
        self.foot = (0, 0)
        self.goal = (0, 0)
        self.seated = True
        self.moving = False
        self.flip = False
        self.target: "Actor | None" = None
        self.visitors = 0
        self.life = Life(self.seed)
        self.away = False  # out of the room, so only the hall can draw it.
        self.router = None  # the view's route finder.
        self.path: list[tuple[int, int]] = []
        self.path_goal: tuple[int, int] | None = None
        self.hall_foot: tuple[int, int] | None = None
        self.hall_path: list[tuple[int, int]] = []
        self.hall_goal: tuple[int, int] | None = None
        self.hall_flip = False

    @property
    def stand_point(self) -> tuple[int, int]:
        return self.desk[0] + STAND[0], self.desk[1] + STAND[1]

    @property
    def wants_seat(self) -> bool:
        return self.worker.state != "waiting" and self.life.kind in ("work", "desk")

    def place(self, desk: tuple[int, int]) -> None:
        """Puts the actor at its destination with no walking: first sight or a new desk."""
        self.desk = desk
        self.seated = self.wants_seat
        self.foot = self.goal = self.stand_point
        self.moving = False
        self.path, self.path_goal = [], self.goal

    def settle(self) -> None:
        """Places a waiter directly at the goal chosen this step."""
        if not self.wants_seat:
            self.foot = self.goal
            self.path, self.path_goal = [], self.goal

    def step(self) -> None:
        if self.seated and self.wants_seat:
            self.moving = False
            return
        if self.seated:
            self.seated, self.foot = False, self.stand_point
            self.path_goal = None
        if self.goal != self.path_goal:
            self.path = self.router(self.foot, self.goal) if self.router else [self.goal]
            self.path_goal = self.goal
        self.moving = bool(self.path)
        if self.moving:
            dx, dy = self.path[0][0] - self.foot[0], self.path[0][1] - self.foot[1]
            self.foot = (self.foot[0] + max(-2, min(2, dx)), self.foot[1] + max(-2, min(2, dy)))
            if dx:
                self.flip = dx > 0
            if self.foot == self.path[0]:
                self.path.pop(0)
        elif self.target is not None:
            # The wait pose looks right unflipped, so it flips to look at someone on the left.
            self.flip = self.target.desk[0] + 28 < self.foot[0]
        else:
            self.flip = False
        if self.wants_seat and self.foot == self.stand_point:
            self.seated, self.moving = True, False

    def seat_look(self, tick: int) -> tuple[str, str, str, str]:
        """Pose, eyes, icon and monitor screen of the character sitting at its desk."""
        w = self.worker
        greet = self.visitors > 0 and (tick // BEAT) % 3 == 1
        eyes, heart = ("happy", "heart") if greet else ("", "")
        if w.state == "working":
            return work_glance(self.seed, tick) or POSE.get(w.activity, "type"), eyes, heart, SCREEN.get(w.activity, "code")
        if w.state == "thinking":
            return "think", eyes, heart or "dots", "code"
        if w.state == "ask":
            return "look", "", "ask", "idle"
        if w.state == "failed":
            return "slump", "", "fail", "idle"
        if w.state == "waiting":
            return "look", "", "dots", "idle"
        return self.life.pose, eyes, heart or ("alert" if w.state == "blocked" else "done"), "idle"

    def stand_look(self, tick: int) -> tuple[str, str, str, str]:
        """Pose, eyes, icon and monitor screen of the character away from its chair."""
        beat = (tick // BEAT) % 3
        if self.moving:
            return "walk", "", "", "idle"
        if self.life.kind == "visit" and self.target is not None:
            return "chat", "", ("dots", "", "heart")[beat], "idle"
        if self.life.kind == "roam":
            return "bob" if (self.seed + tick // 24) % 3 == 0 else "stand", "", "", "idle"
        if self.target is None:
            return "wait", "", "dots", "idle"
        if beat == 0:
            return "wait", "", "dots", "idle"
        return "wait", "happy" if beat == 2 else "", "heart" if beat == 2 else "", "idle"

    def appearance(self, tick: int) -> tuple[str, str, str, str]:
        return self.seat_look(tick) if self.seated else self.stand_look(tick)

    def head(self) -> tuple[int, int]:
        if self.seated:
            return self.desk[0] + props.SEAT_DX, self.desk[1] + props.SEAT_DY
        return self.foot[0] - 8, self.foot[1] - BODY_H + 1

    def draw_station(self, canvas: sprites.Canvas, tick: int) -> None:
        x, y = self.desk
        pose, eyes, _, screen = self.appearance(tick)
        hx, hy = self.head()
        props.draw_chair(canvas, x, y, CHAIR)
        if self.seated:
            sprites.draw(canvas, hx, hy, self.look, pose, tick, "back", eyes=eyes)
        props.draw_desk(canvas, x, y)
        props.draw_monitor(canvas, x, y, screen if self.seated else "idle", tick, glow=self.seated and screen != "idle")
        props.draw_keyboard(canvas, x, y)
        props.draw_props(canvas, x, y, self.seed)
        if self.seated:
            sprites.draw(canvas, hx, hy, self.look, pose, tick, "front", eyes=eyes)

    def note(self) -> str:
        """What the bubble says about a character that is not at its desk by its own plan."""
        return "foi tomar um cafe" if self.life.kind == "out" else ""

    def draw_body(self, canvas: sprites.Canvas, tick: int) -> None:
        pose, eyes, _, _ = self.appearance(tick)
        hx, hy = self.head()
        sprites.draw(canvas, hx, hy, self.look, pose, tick, flip=self.flip, eyes=eyes)

    def draw_icons(self, canvas: sprites.Canvas, tick: int) -> None:
        if self.away:
            return
        pose, _, icon, _ = self.appearance(tick)
        hx, hy = self.head()
        fx = sprites.frame_of(pose, tick)[4]
        if icon:
            props.draw_icon(canvas, hx + 16, hy - 3, icon)
        if fx == "zzz":
            props.draw_icon(canvas, hx + 16, hy + 8 - (tick // 8) % 3, "zzz")
        if fx == "steam":
            props.draw_icon(canvas, hx + (0 if self.flip and not self.seated else 15), hy + 6 - (tick // 4) % 2, "steam")
