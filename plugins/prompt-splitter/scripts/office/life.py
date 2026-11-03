"""What idle characters decide to do: stay at the desk, walk around, visit a colleague or leave the room."""
import random
import zlib

IDLE_STATES = ("done", "blocked")
DESK_POSES = ("coffee", "nap", "read", "phone", "look")
# Each entry: kind, weight, shortest and longest duration in ticks.
CHOICES = (("desk", 40, 70, 240), ("out", 30, 170, 420), ("roam", 15, 45, 110), ("visit", 15, 90, 190))
WORK_BEAT = 48
FIRST_DELAY = 120


class Life:
    """The current plan of one character. Plans only apply while its split is idle."""

    def __init__(self, seed: int):
        self.seed = seed
        self.kind = "work"
        self.pose = DESK_POSES[seed % len(DESK_POSES)]
        self.until = 0
        self.spot = (0.0, 0.0)  # fractions of the room, used by roam.
        self.mate = None  # the actor being visited.

    def decide(self, tick: int, mates: list) -> None:
        """Picks the next plan with a generator seeded per character and tick, so runs vary but stay testable."""
        rng = random.Random(self.seed ^ tick)
        choices = [c for c in CHOICES if c[0] != "visit" or mates]
        kind, _, low, high = rng.choices(choices, weights=[c[1] for c in choices])[0]
        self.kind, self.until, self.mate = kind, tick + rng.randint(low, high), None
        if kind == "desk":
            self.pose = rng.choice(DESK_POSES)
        elif kind == "roam":
            self.spot = (rng.random(), rng.random())
        elif kind == "visit":
            self.mate = rng.choice(mates)


def advance(actors: list, tick: int, room_of: dict) -> None:
    """Moves every character's plan forward; room_of maps the actors of the visible rooms to their room id."""
    for actor in actors:
        life = actor.life
        if actor.worker.state not in IDLE_STATES:
            life.kind, life.mate = "work", None
            continue
        if life.kind == "work":
            # Just became idle: it sits for a moment before doing anything else, and the crowd never moves at once.
            life.kind, life.until = "desk", tick + FIRST_DELAY + life.seed % 90
        elif tick >= life.until:
            here = room_of.get(actor.worker.id)
            mates = [other for other in actors if other is not actor and here is not None
                     and room_of.get(other.worker.id) == here and other.life.kind in ("desk", "work")]
            life.decide(tick, mates)
        if life.mate is not None and life.mate.worker.id not in room_of:
            life.mate = None
            life.kind = "desk"


def work_glance(seed: int, tick: int) -> str:
    """A busy character sometimes looks up or takes a sip: returns the pose of that moment, or an empty string."""
    beat = zlib.crc32(f"{seed}:{tick // WORK_BEAT}".encode()) % 9
    return {0: "look", 1: "coffee"}.get(beat, "")
