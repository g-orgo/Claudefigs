#!/usr/bin/env python3
"""Animated office of the prompt-splitter sessions: one character per split, a click opens its session."""
import argparse
import os
import re
import select
import shutil
import signal
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from office.data import Poller, full_session_id  # noqa: E402
from office.demo import DemoSource  # noqa: E402
from office.office import Office  # noqa: E402
from office.term import Frame, Screen, diff  # noqa: E402

FRAME_S = 1 / 8
REFRESH_TICKS = 4
FONT = "/usr/share/fonts/google-noto/NotoSansMono-Regular.ttf"
NEXT = {"\t", "\x1b[C", "\x1b[B"}
PREVIOUS = {"\x1b[Z", "\x1b[D", "\x1b[A"}
ESCAPE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]?)?")
PARTIAL = re.compile(r"\x1b(?:\[[0-?]*[ -/]*)?")
MOUSE = re.compile(r"\x1b\[<(\d+);(\d+);(\d+)([Mm])")
LEFT_BUTTON, WHEEL_UP, WHEEL_DOWN = 0, 64, 65


def parse_size(value: str) -> tuple[int, int]:
    cols, rows = value.lower().split("x")
    return int(cols), int(rows)


def keys_of(data: str) -> list[str]:
    """Splits raw input into single keys, keeping escape sequences of any length whole.

    A sequence cut by the end of the data comes back as the last key and matches PARTIAL.
    """
    out, i = [], 0
    while i < len(data):
        match = ESCAPE.match(data, i)
        size = match.end() - i if match else 1
        out.append(data[i:i + size])
        i += size
    return out


def parse_mouse(key: str) -> tuple[int, int, int, bool] | None:
    """An SGR mouse report as (button, col, row, pressed), with 0-based cells; None for any other key."""
    match = MOUSE.fullmatch(key)
    if match is None:
        return None
    return int(match[1]), int(match[2]) - 1, int(match[3]) - 1, match[4] == "M"


def session_command(worker) -> list[str] | None:
    """The command that gives this split a composer, or None when there is no session to open.

    `claude attach` works for every session the registry knows, waking an ended one, and fails for any other.
    Those only reopen with `claude --resume`, which takes the full session id and not the short one.
    """
    if worker.state == "waiting":
        return None
    if worker.attachable:
        return ["claude", "attach", worker.id]
    session_id = full_session_id(worker.session_id)
    return ["claude", "--resume", session_id] if session_id else None


def open_session(scene, worker) -> None:
    """Opens the split in a new Konsole, in its directory, ready to continue; failures only show a notice."""
    command = session_command(worker)
    if command is None:
        scene.notify("Esta sessao ainda nao pode ser aberta")
        return
    workdir = ["--workdir", worker.cwd] if worker.cwd else []
    try:
        subprocess.Popen(["setsid", "-f", "konsole", *workdir, "-e", *command],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        scene.notify("Nao foi possivel abrir o Konsole")


def handle_key(scene, key: str) -> None:
    """Applies one key or mouse report to the scene."""
    mouse = parse_mouse(key)
    if mouse is not None:
        button, col, row, pressed = mouse
        if not pressed:
            return
        if button == WHEEL_UP:
            scene.select(-1)
        elif button == WHEEL_DOWN:
            scene.select(1)
        elif button == LEFT_BUTTON:
            worker = scene.click(col, row)
            if worker is not None:
                open_session(scene, worker)
    elif key in NEXT:
        scene.select(1)
    elif key in PREVIOUS:
        scene.select(-1)
    elif key in ("\r", "\n"):
        worker = scene.press()
        if worker is not None:
            open_session(scene, worker)
    elif key in ("\x1b", "\x7f", "b"):
        scene.back()
    elif key in ("w", "W"):
        scene.toggle_warehouse()


def write_png(frame: Frame, path: str) -> None:
    from PIL import Image, ImageDraw, ImageFont

    cell_w, cell_h = 8, 16
    image = Image.new("RGB", (frame.cols * cell_w, frame.nrows * cell_h))
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(FONT, 13) if os.path.exists(FONT) else ImageFont.load_default()
    for r, line in enumerate(frame.cells):
        for c, (ch, fg, bg, _bold) in enumerate(line):
            box = (c * cell_w, r * cell_h, (c + 1) * cell_w - 1, (r + 1) * cell_h - 1)
            draw.rectangle(box, fill=bg or (0, 0, 0))
            if ch == "▀":
                draw.rectangle((box[0], box[1], box[2], box[1] + cell_h // 2 - 1), fill=fg)
            elif ch.strip():
                draw.text((box[0], box[1]), ch, fill=fg or (255, 255, 255), font=font)
    image.save(path)


def offline(args: argparse.Namespace, source) -> int:
    cols, rows = parse_size(args.size)
    scene = Office(cols, rows)
    scene.set_workers(source.snapshot())
    if args.view == "warehouse":
        scene.toggle_warehouse()
    elif args.view == "room":
        scene.press()
    if args.snapshot:
        for _ in range(args.tick):
            scene.step()
        write_png(scene.render(), args.snapshot)
        return 0
    previous, started = None, time.perf_counter()
    for _ in range(args.bench):
        scene.step()
        frame = scene.render()
        diff(previous, frame)
        previous = frame
    print(f"{(time.perf_counter() - started) * 1000 / args.bench:.1f} ms/frame")
    return 0


def run(source) -> int:
    if not sys.stdout.isatty() or not sys.stdin.isatty():
        print("claude split precisa de um terminal.", file=sys.stderr)
        return 1
    resized = [False]
    signal.signal(signal.SIGWINCH, lambda *_: resized.__setitem__(0, True))
    for signum in (signal.SIGTERM, signal.SIGHUP, signal.SIGQUIT):
        signal.signal(signum, lambda *_: sys.exit(0))
    screen = Screen()
    scene = Office(*shutil.get_terminal_size())
    source.start()
    pending = ""
    try:
        screen.enter()
        while True:
            started = time.monotonic()
            if resized[0]:
                resized[0] = False
                scene.resize(*shutil.get_terminal_size())
            if scene.tick % REFRESH_TICKS == 0:
                scene.set_workers(source.snapshot())
            scene.step()
            screen.present(scene.render())
            wait = max(0, FRAME_S - (time.monotonic() - started))
            ready = select.select([sys.stdin], [], [], wait)[0]
            if not ready and pending == "\x1b":
                pending = ""  # nothing followed it, so it was the Esc key and not the start of a sequence.
                handle_key(scene, "\x1b")
            if ready:
                keys = keys_of(pending + os.read(sys.stdin.fileno(), 1024).decode(errors="ignore"))
                pending = keys.pop() if keys and PARTIAL.fullmatch(keys[-1]) else ""
                for key in keys:
                    if key in ("q", "Q", "\x03"):
                        return 0
                    handle_key(scene, key)
    except KeyboardInterrupt:
        return 0
    finally:
        screen.exit()


def main() -> int:
    parser = argparse.ArgumentParser(description="Escritorio animado dos splits: entre por uma porta e clique em um balao para abrir a sessao.")
    parser.add_argument("--demo", action="store_true", help="mostra splits de exemplo")
    parser.add_argument("--snapshot", help="grava um quadro em PNG e sai")
    parser.add_argument("--bench", type=int, default=0, help="mede o tempo de N quadros e sai")
    parser.add_argument("--size", default="200x60", help="tamanho CxL para --snapshot e --bench")
    parser.add_argument("--view", default="hall", choices=("hall", "warehouse", "room"), help="tela inicial de --snapshot e --bench")
    parser.add_argument("--tick", type=int, default=80, help="quadros simulados antes do --snapshot")
    args = parser.parse_args()
    source = DemoSource() if args.demo else Poller()
    if args.snapshot or args.bench:
        return offline(args, source)
    return run(source)


if __name__ == "__main__":
    raise SystemExit(main())
