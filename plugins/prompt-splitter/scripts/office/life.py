"""What idle characters decide to do: stay at the desk or leave the room for good during that idle period."""
import random
import zlib

IDLE_STATES = ("done", "blocked")
DESK_POSES = ("coffee", "nap", "read", "phone", "look")
# Each entry: kind, weight, shortest and longest duration in ticks.
CHOICES = (("desk", 40, 70, 240), ("out", 30, 170, 420))
WORK_BEAT = 48
FIRST_DELAY = 120


class Life:
    """The current plan of one character. Plans only apply while its split is idle."""

    def __init__(self, seed: int):
        self.seed = seed
        self.kind = "work"
        self.pose = DESK_POSES[seed % len(DESK_POSES)]
        self.until = 0
        self.decided = False  # whether the one idle decision of this idle period was already made

    def decide(self, tick: int) -> None:
        """Picks the single idle plan with a generator seeded per character and tick, so runs vary but stay testable."""
        rng = random.Random(self.seed ^ tick)
        kind, _, low, high = rng.choices(CHOICES, weights=[c[1] for c in CHOICES])[0]
        self.kind, self.until, self.decided = kind, tick + rng.randint(low, high), True
        if kind == "desk":
            self.pose = rng.choice(DESK_POSES)


def advance(actors: list, tick: int, room_of: dict) -> None:
    """Moves every character's plan forward; room_of maps the actors of the visible rooms to their room id."""
    for actor in actors:
        life = actor.life
        if actor.worker.state not in IDLE_STATES:
            life.kind, life.decided = "work", False
            continue
        if life.kind == "work":
            # Just became idle: it sits for a moment before deciding once, and the crowd never moves at once.
            life.kind, life.until, life.decided = "desk", tick + FIRST_DELAY + life.seed % 90, False
        elif tick >= life.until:
            if not life.decided:
                life.decide(tick)
            elif life.kind == "desk":
                # It stays at the desk for the whole idle period; only the pose changes.
                rng = random.Random(life.seed ^ tick)
                life.pose, life.until = rng.choice(DESK_POSES), tick + rng.randint(70, 240)


def work_glance(seed: int, tick: int) -> str:
    """A busy character sometimes looks up or takes a sip: returns the pose of that moment, or an empty string."""
    beat = zlib.crc32(f"{seed}:{tick // WORK_BEAT}".encode()) % 9
    return {0: "look", 1: "coffee"}.get(beat, "")
