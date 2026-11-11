#!/usr/bin/env python3
"""Animated office of the prompt-splitter sessions: one character per split, a click opens its session."""
import argparse
import codecs
import os
import re
import select
import shutil
import signal
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from office import clipboard  # noqa: E402
from office.data import Poller, full_session_id  # noqa: E402
from office.demo import DemoSource  # noqa: E402
from office.office import Office  # noqa: E402
from office.term import Frame, Screen, diff  # noqa: E402

FRAME_S = 1 / 8
ESC_S = 0.05  # a lone Esc this old is the key, not the start of a sequence.
DRAW_S = 1 / 30  # input redraws sooner than the next tick, but a mouse flood does not draw per report.
REFRESH_TICKS = 4
FONT = "/usr/share/fonts/google-noto/NotoSansMono-Regular.ttf"
NEXT = {"\x1b[C", "\x1b[B"}
PREVIOUS = {"\x1b[D", "\x1b[A"}
ESCAPE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]?|O[A-Z]?)?")  # CSI, or SS3 (arrows in application cursor mode).
PARTIAL = re.compile(r"\x1b(?:\[[0-?]*[ -/]*|O)?")
FOCUS_IN, FOCUS_OUT = "\x1b[I", "\x1b[O"  # focus reporting (mode 1004); ESCAPE already reads each as one key.
SS3_KEYS = {f"\x1bO{c}": f"\x1b[{c}" for c in "ABCDHF"}  # application cursor mode sends ESC O x; read it as ESC [ x.
MOUSE = re.compile(r"\x1b\[<(\d+);(\d+);(\d+)([Mm])")
LEFT_BUTTON, WHEEL_UP, WHEEL_DOWN = 0, 64, 65
MOTION = 32
PASTE_START, PASTE_END = "\x1b[200~", "\x1b[201~"
LEFT_KEYS = {"\x1b[D"}
RIGHT_KEYS = {"\x1b[C"}
HOME_KEYS = {"\x1b[H", "\x1b[1~", "\x1bOH"}
END_KEYS = {"\x1b[F", "\x1b[4~", "\x1bOF"}
WORD_LEFT_KEYS = {"\x1b[1;5D"}
WORD_RIGHT_KEYS = {"\x1b[1;5C"}
SHIFT_LEFT_KEYS = {"\x1b[1;2D"}
SHIFT_RIGHT_KEYS = {"\x1b[1;2C"}
SHIFT_HOME_KEYS = {"\x1b[1;2H"}
SHIFT_END_KEYS = {"\x1b[1;2F"}
SHIFT_WORD_LEFT_KEYS = {"\x1b[1;6D"}
SHIFT_WORD_RIGHT_KEYS = {"\x1b[1;6C"}
DELETE_KEYS = {"\x1b[3~"}


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
        key = data[i:i + size]
        out.append(SS3_KEYS.get(key, key))
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


def launch(argv: list[str], cwd: str | None) -> tuple[int, str]:
    """Runs one send to completion; the office calls it from a worker thread. Returns (exit code, output)."""
    result = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=120)
    return result.returncode, result.stdout + result.stderr


def write_clipboard(text: str) -> bool:
    """Puts text on the desktop clipboard through the office clipboard module."""
    return clipboard.write_clipboard(text)


def copy_selection(composer) -> None:
    """Puts a finished non-empty selection on the desktop clipboard."""
    text = composer.selected_text()
    if text:
        write_clipboard(text)


def handle_key(scene, key: str) -> None:
    """Applies one key or mouse report to the scene; a plain Scene has no composer and keeps the old keys."""
    composer = getattr(scene, "composer", None)
    mouse = parse_mouse(key)
    if mouse is not None:
        button, col, row, pressed = mouse
        hover = getattr(scene, "hover", None)
        if button & MOTION:  # bit 32: the pointer moved, with or without a button.
            if composer is not None and composer.dragging and button == MOTION:
                index = composer.index_at(col, row)
                if index is not None:
                    composer.drag_to(index)
                return
            if hover is not None:
                hover(col, row)
            return
        if not pressed:
            if composer is not None and composer.dragging:
                text = composer.end_drag()
                if text:
                    write_clipboard(text)
            return
        if button == LEFT_BUTTON and getattr(scene, "notice_click", lambda c, r: False)(col, row):
            return  # the usage-limit pop-up closes on a click and the click goes no further.
        if button == LEFT_BUTTON and composer is not None and composer.focused:
            index = scene.popup_row_at(col, row)
            if index is not None:
                scene.popup_accept(index)  # a click on a suggestion row takes it, without leaving the field.
                return
        if button == LEFT_BUTTON and composer is not None:
            if scene.in_composer(col, row):
                if getattr(scene, "question_click", lambda c, r: False)(col, row):
                    return  # a question or one of its options, not the answer line.
                composer.focus()
                index = composer.index_at(col, row)
                if index is not None:
                    composer.begin_drag(index)
                return
            composer.blur()
        hits_back = getattr(scene, "hits_back", None)
        if button == LEFT_BUTTON and hits_back is not None and hits_back(col, row):
            scene.back()  # the Voltar button wins over whatever is drawn under it.
            return
        if button in (WHEEL_UP, WHEEL_DOWN):
            if hover is not None:
                hover(col, row)  # terminals without motion reports still scroll what is under the pointer.
            scene.scroll(-1 if button == WHEEL_UP else 1)
        elif button == LEFT_BUTTON:
            worker = scene.click(col, row)
            if worker is not None:
                open_session(scene, worker)
    elif getattr(scene, "answer_key", lambda k: False)(key):
        return  # a shown question took the key: option arrows, Space, Tab, Ctrl+X.
    elif key == "\x1b" and not (composer is not None and composer.focused) and getattr(scene, "notice_dismiss", lambda: False)():
        return  # Esc closes the usage-limit pop-up only when the field is not focused.
    elif composer is not None and composer.focused:
        if key in ("\r", "\n"):
            if not scene.popup_accept():  # with a suggestion open, Enter takes it instead of sending.
                scene.submit()
        elif key == "\t":
            scene.popup_accept()
        elif key in ("\x1b[A", "\x1b[B"):
            if scene.popup_items():
                scene.popup_move(-1 if key == "\x1b[A" else 1)  # the popup takes the arrows; the chat never scrolls here.
            elif key == "\x1b[A":
                composer.move_up()
            else:
                composer.move_down()
        elif key in LEFT_KEYS:
            composer.move_left()
        elif key in RIGHT_KEYS:
            composer.move_right()
        elif key in HOME_KEYS:
            composer.move_home()
        elif key in END_KEYS:
            composer.move_end()
        elif key in WORD_LEFT_KEYS:
            composer.move_word_left()
        elif key in WORD_RIGHT_KEYS:
            composer.move_word_right()
        elif key in SHIFT_LEFT_KEYS:
            composer.shift_left()
            copy_selection(composer)
        elif key in SHIFT_RIGHT_KEYS:
            composer.shift_right()
            copy_selection(composer)
        elif key in SHIFT_HOME_KEYS:
            composer.move_home(True)
            copy_selection(composer)
        elif key in SHIFT_END_KEYS:
            composer.move_end(True)
            copy_selection(composer)
        elif key in SHIFT_WORD_LEFT_KEYS:
            composer.move_word_left(True)
            copy_selection(composer)
        elif key in SHIFT_WORD_RIGHT_KEYS:
            composer.move_word_right(True)
            copy_selection(composer)
        elif key in DELETE_KEYS:
            composer.delete()
        elif key == "\x1b":
            if not scene.popup_dismiss():  # Esc closes the popup first, then leaves the field; the draft stays.
                composer.blur()
        elif key in ("\x7f", "\b"):
            composer.backspace()
        elif key == "\x15":
            composer.clear()
        elif key == "\x16":
            scene.paste_clipboard()
        elif len(key) == 1 and key.isprintable():
            composer.insert(key)
    elif key == "\t" and composer is not None and scene.composer_shown():
        composer.focus()
    elif key in ("\x1b[A", "\x1b[B") and getattr(scene, "arrows_scroll", lambda: False)():
        step = scene.chat_step()
        scene.chat(step if key == "\x1b[A" else -step)  # Up is older, Down is newer.
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


class FrameClock:
    """Paces the viewer: ticks at a fixed rate whatever the input does, redraws after input at most every DRAW_S."""

    def __init__(self, now: float):
        self.next_tick = now
        self.last_draw = now - DRAW_S
        self.dirty = True

    def tick_due(self, now: float) -> bool:
        if now < self.next_tick:
            return False
        self.next_tick = now + FRAME_S
        self.dirty = True
        return True

    def draw_due(self, now: float) -> bool:
        if not self.dirty or now - self.last_draw < DRAW_S:
            return False
        self.dirty, self.last_draw = False, now
        return True

    def wait(self, now: float) -> float:
        """Seconds until the next tick, or the pending redraw if that comes first."""
        until = self.next_tick - now
        if self.dirty:
            until = min(until, self.last_draw + DRAW_S - now)
        return max(0, until)


def run(source, demo: bool = False) -> int:
    if not sys.stdout.isatty() or not sys.stdin.isatty():
        print("claude split precisa de um terminal.", file=sys.stderr)
        return 1
    resized = [False]
    signal.signal(signal.SIGWINCH, lambda *_: resized.__setitem__(0, True))
    for signum in (signal.SIGTERM, signal.SIGHUP, signal.SIGQUIT):
        signal.signal(signum, lambda *_: sys.exit(0))
    screen = Screen()
    scene = Office(*shutil.get_terminal_size(), sender=launch, demo=demo)
    source.start()
    pending, pending_at = "", 0.0
    paste = None  # keys of a bracketed paste in progress, or None
    decoder = codecs.getincrementaldecoder("utf-8")(errors="ignore")
    try:
        screen.enter()
        sys.stdout.write("\x1b[?2004h")
        sys.stdout.write("\x1b[?1004h")
        sys.stdout.flush()
        clock = FrameClock(time.monotonic())
        while True:
            now = time.monotonic()
            if resized[0]:
                resized[0] = False
                scene.resize(*shutil.get_terminal_size())
                clock.dirty = True
            if clock.tick_due(now):
                if scene.tick % REFRESH_TICKS == 0:
                    scene.set_workers(source.snapshot())
                scene.step()
            if clock.draw_due(now):
                screen.present(scene.render())
            ready = select.select([sys.stdin], [], [], clock.wait(time.monotonic()))[0]
            if not ready and pending == "\x1b" and time.monotonic() - pending_at >= ESC_S:
                pending = ""  # nothing followed it, so it was the Esc key and not the start of a sequence.
                handle_key(scene, "\x1b")
            if ready:
                clock.dirty = True
                keys = keys_of(pending + decoder.decode(os.read(sys.stdin.fileno(), 1024)))
                pending = keys.pop() if keys and PARTIAL.fullmatch(keys[-1]) else ""
                pending_at = time.monotonic()
                scene.user_active()  # any input is activity: resume the sessions whose limit reset.
                for key in keys:
                    if key == FOCUS_IN:
                        continue
                    if key == FOCUS_OUT:
                        continue
                    if paste is not None:
                        if key == PASTE_END:
                            scene.paste("".join(paste))
                            paste = None
                        else:
                            paste.append(key)
                        continue
                    if key == PASTE_START:
                        paste = []
                    elif key == "\x03" or (key in ("q", "Q") and not getattr(getattr(scene, "composer", None), "focused", False)):
                        return 0
                    else:
                        handle_key(scene, key)
    except KeyboardInterrupt:
        return 0
    finally:
        sys.stdout.write("\x1b[?2004l")
        sys.stdout.write("\x1b[?1004l")
        sys.stdout.flush()
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
    return run(source, args.demo)


if __name__ == "__main__":
    raise SystemExit(main())
