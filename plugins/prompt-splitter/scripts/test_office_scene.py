"""Tests for the office terminal viewer: cell frames, ANSI diffs and scene layout and actors."""
import io
import os
import pty
import termios
import unittest
from unittest import mock

from claude_office import PARTIAL, handle_key, keys_of, open_session, parse_mouse, session_command
from office import props
from office.model import Line, Worker
from office.actors import SLOTS, resolve_target
from office.bubble import body_rows, chat_geometry
from office import rooms
from office.composer import BACK_H, BACK_W, INK_BROWN
from office.office import BACK_GAP, COPY_WORDING, Office
from office.scene import MIN_COLS, MIN_ROWS, Scene
from office.sprites import Canvas
from office.term import MOUSE_OFF, MOUSE_ON, Frame, Screen, char_width, diff


def make_worker(i: int, state: str = "working", activity: str = "code", lines=None) -> Worker:
    return Worker(
        id=f"w{i}",
        session_id=f"s{i}",
        name=f"Worker {i}",
        title=f"Task {i}",
        item_label=f"item {i}",
        group="g",
        index=i,
        cwd="/tmp",
        started_ms=float(i),
        state=state,
        activity=activity,
        lines=lines or [],
    )


def row_text(frame: Frame, row: int) -> str:
    return "".join(cell[0] for cell in frame.cells[row])


class CharWidthTests(unittest.TestCase):
    def test_widths(self):
        self.assertEqual(char_width("a"), 1)
        self.assertEqual(char_width("中"), 2)
        self.assertEqual(char_width("́"), 0)


class FrameTests(unittest.TestCase):
    def test_half_block_packs_two_pixels(self):
        canvas = Canvas(2, 2, fill=(0, 0, 0))
        canvas.put(0, 0, (255, 0, 0))
        frame = Frame.from_canvas(canvas, 2, 1)
        char, fg, bg, _ = frame.cells[0][0]
        self.assertEqual(char, "▀")
        self.assertEqual(fg, (255, 0, 0))
        self.assertEqual(bg, (0, 0, 0))
        self.assertEqual(frame.cells[0][1][0], " ")

    def test_wide_character_takes_two_cells_and_clips(self):
        frame = Frame(4, 1)
        frame.text(0, 0, "中文字", None, None)
        self.assertEqual(frame.cells[0][0][0], "中")
        self.assertEqual(frame.cells[0][1][0], "")
        self.assertEqual(frame.cells[0][2][0], "文")
        self.assertEqual(frame.cells[0][3][0], "")

    def test_text_outside_grid_is_clipped(self):
        frame = Frame(3, 1)
        frame.text(2, 0, "abc", None, None)
        self.assertEqual(row_text(frame, 0), "  a")
        frame.text(0, 5, "zzz", None, None)  # row out of range is ignored


class DiffTests(unittest.TestCase):
    def test_unchanged_frame_emits_nothing(self):
        frame = Frame(5, 2)
        frame.text(0, 0, "hello", None, None)
        prev = Frame(5, 2)
        prev.text(0, 0, "hello", None, None)
        self.assertEqual(diff(prev, frame), ("", 0))

    def test_full_redraw_is_wrapped_in_synchronized_output(self):
        frame = Frame(3, 2)
        text, changed = diff(None, frame)
        self.assertTrue(text.startswith("\x1b[?2026h"))
        self.assertTrue(text.endswith("\x1b[?2026l"))
        self.assertEqual(changed, 6)

    def test_only_changed_cells_are_written(self):
        prev = Frame(10, 1)
        frame = Frame(10, 1)
        frame.text(4, 0, "x", None, None)
        text, changed = diff(prev, frame)
        self.assertEqual(changed, 1)
        self.assertIn("\x1b[1;5H", text)

class SceneTests(unittest.TestCase):
    def workers(self):
        make = lambda index, state, after=(): Worker(id=f"w{index}", session_id="s", name="n", title=f"T{index}", item_label=str(index),
                                                     group="g", index=index, cwd="", started_ms=index, state=state, activity="code", after=list(after))
        return [make(1, "working"), make(2, "waiting", [1]), make(3, "waiting", [2]), make(4, "done")]

    def test_per_page(self):
        self.assertEqual(Scene(120, 40).per_page, 2)
        self.assertEqual(Scene(200, 60).per_page, 8)

    def test_chain_reaches_the_worker_actually_working(self):
        workers = self.workers()
        self.assertEqual(resolve_target(workers[2], workers).id, "w1")
        workers[0].state = "done"
        self.assertIsNone(resolve_target(workers[1], workers))

    def test_waiter_walks_to_a_slot_and_goes_back_when_released(self):
        scene = Scene(200, 60)
        workers = self.workers()
        scene.set_workers(workers)
        scene.step()
        waiter, host = scene.actors["w2"], scene.actors["w1"]
        for _ in range(200):
            scene.step()
        self.assertFalse(waiter.seated)
        self.assertEqual(waiter.foot, waiter.goal)
        self.assertLess(abs(waiter.foot[0] - host.desk[0]), 60)
        self.assertEqual(host.visitors, 2)
        workers[1].state = "working"
        for _ in range(200):
            scene.step()
        self.assertTrue(waiter.seated)

    def test_bubble_keeps_the_tail_and_the_state_row(self):
        worker = self.workers()[0]
        worker.lines = [Line("tool", f"passo {i}") for i in range(20)]
        rows = body_rows(worker, [worker], 30, 4)
        self.assertEqual(len(rows), 4)
        self.assertIn("passo 19", rows[-2][0])
        self.assertEqual(rows[-1][0], "Estou trabalhando")

    def test_long_tool_line_wraps_and_state_stays_visible(self):
        worker = self.workers()[0]
        long_line = "Estou procurando \"ContadorDeItensDaFilaDeProcessamento\" no código do módulo de cobrança"
        worker.lines = [Line("tool", long_line), Line("tool", "Estou lendo o arquivo api.md")]
        rows = body_rows(worker, [worker], 20, 12)
        texts = [row[0] for row in rows]
        self.assertLessEqual(len(rows), 12)
        self.assertGreater(len(rows), 3)
        self.assertEqual(texts[-1], "Estou trabalhando")
        self.assertIn("Estou lendo o arquivo", " ".join(texts))
        self.assertTrue(all(len(text) <= 20 for text in texts))
        self.assertIn("código", " ".join(texts))

    def test_selection_stops_at_the_top_and_the_bottom(self):
        scene = Scene(200, 60)
        scene.set_workers(self.workers())
        scene.select(-3)
        self.assertEqual(scene.selected().id, "w1")
        scene.select(99)
        scene.select(1)
        self.assertEqual(scene.selected().id, "w4")

    def test_renders_at_every_size(self):
        for size in ((80, 30), (120, 40), (200, 60), (30, 10)):
            scene = Scene(*size)
            scene.set_workers(self.workers())
            for _ in range(60):
                scene.step()
            frame = scene.render()
            self.assertEqual((frame.cols, frame.nrows), size)


class KeysOfTests(unittest.TestCase):
    def test_splits_plain_keys_and_arrows(self):
        self.assertEqual(keys_of("q\t\x1b[A\x1b[Z"), ["q", "\t", "\x1b[A", "\x1b[Z"])

    def test_keeps_mouse_reports_of_any_length_whole(self):
        data = "\x1b[<0;5;9M\x1b[<0;120;45mq\x1b[<64;1;1M"
        self.assertEqual(keys_of(data), ["\x1b[<0;5;9M", "\x1b[<0;120;45m", "q", "\x1b[<64;1;1M"])

    def test_cut_report_stays_a_single_partial_key(self):
        keys = keys_of("a\x1b[<0;12")
        self.assertEqual(keys, ["a", "\x1b[<0;12"])
        self.assertTrue(PARTIAL.fullmatch(keys[-1]))
        self.assertEqual(keys_of(keys[-1] + ";7M"), ["\x1b[<0;12;7M"])

    def test_lone_escape_does_not_swallow_the_next_key(self):
        self.assertEqual(keys_of("\x1bq"), ["\x1b", "q"])


class ParseMouseTests(unittest.TestCase):
    def test_press_and_release_with_zero_based_cells(self):
        self.assertEqual(parse_mouse("\x1b[<0;5;9M"), (0, 4, 8, True))
        self.assertEqual(parse_mouse("\x1b[<0;120;45m"), (0, 119, 44, False))

    def test_wheel_buttons(self):
        self.assertEqual(parse_mouse("\x1b[<64;1;1M")[0], 64)
        self.assertEqual(parse_mouse("\x1b[<65;1;1M")[0], 65)

    def test_other_keys_are_not_mouse_reports(self):
        for key in ("q", "\x1b[A", "\x1b[<0;12"):
            self.assertIsNone(parse_mouse(key))


class HitTestTests(unittest.TestCase):
    def scene(self, count: int = 3) -> Scene:
        scene = Scene(200, 60)
        scene.set_workers([make_worker(i) for i in range(count)])
        return scene

    def test_every_corner_of_each_bubble_hits_its_worker(self):
        scene = self.scene()
        visible = scene.visible()
        for worker, (col, top, width, height) in zip(visible, scene._cells()):
            for c, r in ((col, top), (col + width - 1, top + height - 1)):
                self.assertEqual(scene.worker_at(c, r).id, worker.id)

    def test_just_outside_a_bubble_misses(self):
        scene = self.scene(1)
        col, top, width, height = scene._cells()[0]
        for c, r in ((col - 1, top), (col + width, top), (col, top - 1), (col, top + height)):
            self.assertIsNone(scene.worker_at(c, r))

    def test_footer_and_small_terminal_miss(self):
        scene = self.scene()
        self.assertIsNone(scene.worker_at(5, scene.rows - 1))
        small = Scene(MIN_COLS - 1, MIN_ROWS)
        small.set_workers([make_worker(0)])
        self.assertIsNone(small.worker_at(5, 5))

    def test_only_the_current_page_is_hit(self):
        scene = Scene(100, 30)
        scene.set_workers([make_worker(i) for i in range(scene.per_page + 1)])
        scene.selected_id = scene.workers[-1].id
        scene.reveal()
        col, top, _, _ = scene._cells()[0]
        self.assertEqual(scene.worker_at(col, top).id, scene.workers[-1].id)


class HandleKeyTests(unittest.TestCase):
    def scene(self) -> Scene:
        scene = Scene(200, 60)
        scene.set_workers([make_worker(i) for i in range(3)])
        return scene

    def test_wheel_scrolls_the_selected_chat_and_keeps_page_and_selection(self):
        scene = Scene(200, 60)
        scene.set_workers([make_worker(0, lines=[Line("claude", f"linha {n}") for n in range(60)])])
        page = scene.page()
        handle_key(scene, "\x1b[<64;1;1M")
        self.assertGreater(scene.chat_scroll.get("w0", 0), 0)
        self.assertEqual(scene.page(), page)
        self.assertEqual(scene.selected_id, "w0")
        handle_key(scene, "\x1b[<65;1;1M")
        handle_key(scene, "\x1b[<65;1;1M")
        self.assertEqual(scene.chat_scroll.get("w0", 0), 0)
        self.assertEqual(scene.selected_id, "w0")

    def test_tab_no_longer_moves_selection(self):
        scene = self.scene()
        handle_key(scene, "\t")
        handle_key(scene, "\x1b[Z")
        self.assertEqual(scene.selected_id, "w0")

    def test_left_press_on_a_bubble_selects_and_opens_it(self):
        scene = self.scene()
        col, top, _, _ = scene._cells()[2]
        with mock.patch("claude_office.open_session") as opened:
            handle_key(scene, f"\x1b[<0;{col + 2};{top + 2}M")
        self.assertEqual(scene.selected_id, "w2")
        opened.assert_called_once_with(scene, scene.workers[2])

    def test_release_other_buttons_and_empty_cells_do_nothing(self):
        scene = self.scene()
        col, top, _, _ = scene._cells()[2]
        with mock.patch("claude_office.open_session") as opened:
            handle_key(scene, f"\x1b[<0;{col + 2};{top + 2}m")
            handle_key(scene, f"\x1b[<2;{col + 2};{top + 2}M")
            handle_key(scene, f"\x1b[<0;{col + 2};{scene.rows}M")
        self.assertEqual(scene.selected_id, "w0")
        opened.assert_not_called()

    def test_enter_shares_the_click_opener(self):
        scene = self.scene()
        with mock.patch("claude_office.open_session") as opened:
            handle_key(scene, "\r")
        opened.assert_called_once_with(scene, scene.workers[0])


class ScrollSceneTests(unittest.TestCase):
    def scene(self, count: int = 1) -> Scene:
        scene = Scene(200, 60)
        workers = [make_worker(0, lines=[Line("claude", f"linha {n}") for n in range(60)])]
        workers += [make_worker(i) for i in range(1, count)]
        scene.set_workers(workers)
        return scene

    def test_scroll_up_moves_chat_older_and_stops_at_the_top(self):
        scene = self.scene()
        for _ in range(60):
            scene.scroll(-1)
        worker = scene.workers[0]
        total, keep = chat_geometry(worker, scene._cell_of(worker)[0] - 4, scene._cell_of(worker)[1])
        self.assertEqual(scene.chat_scroll["w0"], total - keep)
        scene.scroll(-1)
        self.assertEqual(scene.chat_scroll["w0"], total - keep)

    def test_scroll_down_returns_to_newest_and_stops_at_zero(self):
        scene = self.scene()
        scene.scroll(-1)
        scene.scroll(1)
        scene.scroll(1)
        self.assertEqual(scene.chat_scroll.get("w0", 0), 0)

    def test_short_chat_stays_at_zero(self):
        scene = self.scene(count=2)
        scene.scroll(-1)
        self.assertEqual(scene.chat_scroll.get("w1", 0), 0)

    def test_chat_offset_is_kept_per_worker_and_dropped_when_removed(self):
        scene = self.scene(count=2)
        scene.select(1)
        scene.chat(-3)
        scene.chat(3)
        self.assertNotIn("w1", scene.chat_scroll)
        scene.select(-1)
        scene.chat(3)
        self.assertIn("w0", scene.chat_scroll)
        scene.set_workers([make_worker(1)])
        self.assertNotIn("w0", scene.chat_scroll)

    def test_selection_and_page_do_not_change_on_chat_scroll(self):
        scene = self.scene(count=60)
        selected, page = scene.selected_id, scene.page()
        scene.chat(3)
        self.assertEqual(scene.selected_id, selected)
        self.assertEqual(scene.page(), page)

class OfficeBackAndSendTests(unittest.TestCase):
    def office(self, state: str = "done", attachable: bool = True, sender=None):
        worker = make_worker(0, state=state, lines=[Line("claude", f"linha {n}") for n in range(60)])
        worker.attachable = attachable
        office = Office(200, 60, sender=sender or (lambda argv, cwd: (0, "")))
        office.set_workers([worker])
        return office

    def test_back_button_sits_left_of_the_box_in_room_and_warehouse_absent_in_hall(self):
        office = self.office()
        for mode in ("room", "warehouse"):
            office.mode = mode
            col, row, width, height = office.back_button()
            left, top, _, rows = office.field_rect()
            self.assertEqual((width, height), (BACK_W, BACK_H))
            self.assertEqual(col + width + BACK_GAP, left)
            self.assertTrue(top < row < top + rows)
            self.assertFalse(office.in_composer(col, row))
        office.mode = "hall"
        self.assertIsNone(office.back_button())

    def test_box_gives_way_to_the_back_button_on_a_narrow_terminal(self):
        office = Office(60, 40, sender=lambda argv, cwd: (0, ""))
        office.set_workers([])
        hall_left = office.field_rect()[0]
        office.mode = "warehouse"
        col, row, width, _ = office.back_button()
        left, _, field, _ = office.field_rect()
        self.assertGreaterEqual(col, 0)
        self.assertEqual(col + width + BACK_GAP, left)
        self.assertLessEqual(left + field, 60)
        self.assertLess(hall_left, left)

    def test_back_button_falls_back_to_the_top_without_a_box(self):
        office = Office(200, 20, sender=lambda argv, cwd: (0, ""))
        office.set_workers([])
        office.mode = "room"
        self.assertEqual(office.back_button()[0:2], (1, 0))
        office.mode = "warehouse"
        self.assertEqual(office.back_button()[0:2], ((200 - BACK_W) // 2, 0))

    def test_hits_back_covers_the_whole_button_rectangle(self):
        office = self.office()
        office.mode = "room"
        col, row, width, height = office.back_button()
        for c, r in ((col, row), (col + width - 1, row), (col, row + height - 1), (col + width - 1, row + height - 1)):
            self.assertTrue(office.hits_back(c, r))
        for c, r in ((col - 1, row), (col + width, row), (col, row - 1), (col, row + height)):
            self.assertFalse(office.hits_back(c, r))

    def test_fail_badge_has_the_done_badge_shape_and_a_coloured_rim(self):
        def outline(rows):
            return [[ch == "o" for ch in row] for row in rows]
        done, fail = props.ICONS["done"][1], props.ICONS["fail"][1]
        self.assertEqual(outline(done), outline(fail))
        self.assertEqual({"L", "D"} & set("".join(fail)), {"L", "D"})
        canvas = Canvas(9, 9)
        props.draw_icon(canvas, 0, 0, "fail")
        self.assertEqual(canvas.rows[1][4], props.BADGE_RIMS["fail"][0])
        self.assertEqual(canvas.rows[7][4], props.BADGE_RIMS["fail"][1])
        self.assertEqual(canvas.rows[4][4], (255, 255, 255))

    def test_click_on_back_button_returns_from_room_without_opening_a_bubble(self):
        office = self.office()
        office.mode = "room"
        col, row, _, _ = office.back_button()
        with mock.patch("claude_office.open_session") as opened:
            handle_key(office, f"\x1b[<0;{col + 1};{row + 1}M")
        opened.assert_not_called()
        self.assertEqual(office.mode, "hall")

    def test_click_on_back_button_wins_over_a_bubble_under_it(self):
        office = self.office()
        office.mode = "room"
        col, row, _, _ = office.back_button()
        with mock.patch("claude_office.open_session", side_effect=RuntimeError("must not open")) as opened:
            handle_key(office, f"\x1b[<0;{col + 1};{row + 1}M")
        opened.assert_not_called()

    def test_back_button_is_drawn_with_the_arrow_color(self):
        office = self.office()
        office.mode = "room"
        frame = office.render()
        col, row, width, height = office.back_button()
        cells = [frame.cells[r][c] for r in range(row, row + height // 2) for c in range(col, col + width)]
        self.assertTrue(any(INK_BROWN in (fg, bg) for _, fg, bg, _ in cells))

    def test_room_send_stops_attachable_done_worker_then_resumes(self):
        calls = []
        sent = []
        def sender(argv, cwd):
            sent.append(argv)
            return 0, ""
        office = self.office(sender=sender)
        job = {"worker_id": "w0", "attachable": True, "plan": None}
        with mock.patch("office.office.subprocess.run", side_effect=lambda *a, **k: calls.append(a[0])):
            office._run(job, ["claude", "--resume", "s0"], "/tmp")
        self.assertEqual(calls, [["claude", "stop", "w0"]])
        self.assertEqual(sent, [["claude", "--resume", "s0"]])

    def test_room_send_to_non_attachable_worker_only_resumes(self):
        calls, sent = [], []
        office = self.office(attachable=False, sender=lambda argv, cwd: (sent.append(argv), (0, ""))[1])
        job = {"worker_id": "w0", "attachable": False, "plan": None}
        with mock.patch("office.office.subprocess.run", side_effect=lambda *a, **k: calls.append(a[0])):
            office._run(job, ["claude", "--resume", "s0"], "/tmp")
        self.assertEqual(calls, [])
        self.assertEqual(sent, [["claude", "--resume", "s0"]])

    def test_room_send_still_resumes_when_stop_fails(self):
        sent = []
        office = self.office(sender=lambda argv, cwd: (sent.append(argv), (0, ""))[1])
        job = {"worker_id": "w0", "attachable": True, "plan": None}
        with mock.patch("office.office.subprocess.run", side_effect=OSError("no claude")):
            office._run(job, ["claude", "--resume", "s0"], "/tmp")
        self.assertEqual(sent, [["claude", "--resume", "s0"]])

    def test_working_worker_is_refused_and_stop_never_runs(self):
        calls, sent = [], []
        office = self.office(state="working", sender=lambda argv, cwd: (sent.append(argv), (0, ""))[1])
        job = {"worker_id": "w0", "attachable": True, "plan": None}
        with mock.patch("office.office.subprocess.run", side_effect=lambda *a, **k: calls.append(a[0])):
            office._run(job, ["claude", "--resume", "s0"], "/tmp")
        self.assertEqual(calls, [])
        self.assertEqual(sent, [])

    def test_copy_wording_matches_started_a_copy(self):
        from office.office import COPY_WORDING
        self.assertIsNotNone(COPY_WORDING.search("Started a copy of the session"))


class OpenSessionTests(unittest.TestCase):
    def test_registered_session_attaches(self):
        worker = make_worker(1, state="done")
        worker.attachable = True
        self.assertEqual(session_command(worker), ["claude", "attach", "w1"])

    def test_unregistered_session_resumes_by_full_id(self):
        worker = make_worker(1, state="done")
        with mock.patch("claude_office.full_session_id", return_value="s1-full"):
            self.assertEqual(session_command(worker), ["claude", "--resume", "s1-full"])

    def test_waiting_or_unknown_session_has_no_command(self):
        worker = make_worker(1, state="waiting")
        worker.attachable = True
        self.assertIsNone(session_command(worker))
        with mock.patch("claude_office.full_session_id", return_value=""):
            self.assertIsNone(session_command(make_worker(2, state="done")))

    def test_opens_in_the_worker_directory(self):
        worker = make_worker(1)
        worker.attachable = True
        with mock.patch("claude_office.subprocess.Popen") as popen:
            open_session(Scene(200, 60), worker)
        self.assertEqual(popen.call_args[0][0],
                         ["setsid", "-f", "konsole", "--workdir", "/tmp", "-e", "claude", "attach", "w1"])

    def test_nothing_to_open_shows_a_notice(self):
        scene = Scene(200, 60)
        with mock.patch("claude_office.subprocess.Popen") as popen:
            open_session(scene, make_worker(1, state="waiting"))
        popen.assert_not_called()
        self.assertIn("ainda nao pode", row_text(scene.render(), scene.rows - 1))


class ScreenMouseTests(unittest.TestCase):
    def test_enter_turns_reports_on_and_exit_restores_everything(self):
        master, slave = pty.openpty()
        self.addCleanup(os.close, master)
        self.addCleanup(os.close, slave)
        before = termios.tcgetattr(slave)
        output = io.StringIO()
        with os.fdopen(os.dup(slave)) as stdin, mock.patch("office.term.sys.stdin", stdin):
            screen = Screen(output)
            screen.enter()
            self.assertIn(MOUSE_ON, output.getvalue())
            self.assertFalse(termios.tcgetattr(slave)[3] & termios.ECHO)
            screen.exit()
        self.assertTrue(output.getvalue().endswith(MOUSE_OFF + "\x1b[0m\x1b[?25h\x1b[?1049l"))
        self.assertEqual(termios.tcgetattr(slave), before)


class FurnitureTests(unittest.TestCase):
    FLOOR = (1, 2, 3)

    def station(self, draw) -> Canvas:
        canvas = Canvas(80, 60, self.FLOOR)
        draw(canvas)
        return canvas

    def test_every_leg_touches_the_underside_of_the_desk(self):
        x, y = 10, 15
        canvas = self.station(lambda c: props.draw_desk(c, x, y))
        corners = ((x + 1, y + 6), (x + 27, y + 20), (x + 37, y + 14))
        for lx, ly in corners:
            floor_y = ly + props.LEG_DROP
            for col in range(lx, lx + 3):
                self.assertIn(canvas.rows[floor_y][col], (props.METAL, props.METAL_D))
                run = floor_y
                while canvas.rows[run][col] in (props.METAL, props.METAL_D):
                    run -= 1
                self.assertNotEqual(canvas.rows[run][col], self.FLOOR, f"gap above leg column {col}")

    def test_idle_monitor_shows_a_lit_screen_with_bezel_and_reflection(self):
        canvas = self.station(lambda c: props.draw_monitor(c, 10, 20, "idle", 0, glow=False))
        colors = {color for row in canvas.rows for color in row}
        for color in (props.SCREEN_BG["idle"], props.SCREEN_SHINE, props.BEZEL):
            self.assertIn(color, colors)

    def test_monitor_stays_left_of_the_seated_character(self):
        x, y = 10, 20
        canvas = self.station(lambda c: props.draw_monitor(c, x, y, "code", 7))
        drawn = [col for row in canvas.rows for col, color in enumerate(row) if color != self.FLOOR]
        self.assertLess(max(drawn), x + props.SEAT_DX)

    def test_monitor_stand_is_connected_and_rests_on_the_desk(self):
        x, y = 10, 20
        monitor = self.station(lambda c: props.draw_monitor(c, x, y, "idle", 0, glow=False))
        desk = self.station(lambda c: props.draw_desk(c, x, y))
        stand = x + 7
        column = [row[stand] for row in monitor.rows]
        top = next(i for i, color in enumerate(column) if color != self.FLOOR)
        bottom = max(i for i, color in enumerate(column) if color != self.FLOOR)
        self.assertNotIn(self.FLOOR, column[top:bottom + 1])
        for row in range(y + 5, bottom + 1):
            for col in range(x, x + 16):
                if monitor.rows[row][col] == props.METAL_D:
                    self.assertNotEqual(desk.rows[row][col], self.FLOOR)


class RoomLayoutTests(unittest.TestCase):
    def workers(self, group, count, title="Titulo", started=1_700_000_000_000.0):
        return [Worker(id=f"{group}-{i}", session_id="", name="n", title="t", item_label=str(i + 1),
                       group=group, index=i + 1, cwd="", started_ms=started, state="working",
                       room_title=title) for i in range(count)]

    def demo(self):
        return (self.workers("demo", 7, "Reorganizar o modulo de login")
                + self.workers("outra", 2, "Integrar pagamentos e permissoes")
                + self.workers("terceira", 2, "Limpar modulos antigos"))

    def test_group_workers_keeps_first_seen_order(self):
        workers = self.workers("b", 1) + self.workers("a", 2) + self.workers("b", 1)
        groups = rooms.group_workers(workers)
        self.assertEqual([g[0].group for g in groups], ["b", "a"])
        self.assertEqual([len(g) for g in groups], [2, 2])

    def test_shape_seven_on_four_columns_is_four_by_two(self):
        pages = rooms.paginate(self.workers("demo", 7), 200, 60)
        room = pages[0][0]
        self.assertEqual((room.cols, room.lines), (4, 2))

    def test_paginate_200x60_keeps_fitting_groups_whole(self):
        pages = rooms.paginate(self.demo(), 200, 60)
        seen = {}
        for number, page in enumerate(pages):
            for room in page:
                seen.setdefault(room.group, set()).add(number)
        self.assertTrue(all(len(pages_of) == 1 for pages_of in seen.values()))
        ids = [w.id for page in pages for room in page for w in room.workers]
        self.assertEqual(sorted(ids), sorted(w.id for w in self.demo()))

    def test_split_group_at_120x40_numbers_parts_and_starts_pages(self):
        pages = rooms.paginate(self.workers("big", 9), 120, 40)
        parts = [room for page in pages for room in page]
        self.assertEqual([r.part for r in parts], list(range(1, len(parts) + 1)))
        self.assertTrue(all(r.parts == len(parts) for r in parts))
        self.assertEqual((pages[0][0].part, pages[0][0].group), (1, "big"))
        self.assertEqual(sum(len(r.workers) for r in parts), 9)

    def test_sign_text_has_date_and_count(self):
        text = rooms.sign_text("Titulo", 1_700_000_000_000.0, 7, 1, 1, 200)
        self.assertIn("7 itens", text)
        self.assertTrue(text.startswith("Titulo  "))

    def test_sign_text_singular_and_part(self):
        self.assertIn("1 item", rooms.sign_text("T", 0, 1, 1, 1, 200))
        self.assertNotIn("1 itens", rooms.sign_text("T", 0, 1, 1, 1, 200))
        self.assertTrue(rooms.sign_text("T", 0, 9, 2, 4, 200).endswith("parte 2/4"))

    def test_sign_text_keeps_meta_when_title_truncates(self):
        text = rooms.sign_text("Um titulo bem longo para a sala", 0, 7, 1, 1, 30)
        self.assertTrue(text.endswith("7 itens"))
        self.assertIn("...", text)
        self.assertLessEqual(rooms.display_width(text), 30)

    def test_sign_text_drops_meta_when_narrow(self):
        text = rooms.sign_text("Um titulo bem longo", 0, 7, 1, 1, 14)
        self.assertNotIn("itens", text)
        self.assertLessEqual(rooms.display_width(text), 14)

    def test_room_cells_stay_inside_the_room(self):
        for page in rooms.paginate(self.demo(), 200, 60):
            for room in page:
                for col, row, width, height in room.cells:
                    self.assertGreaterEqual(col, room.left)
                    self.assertLessEqual(col + width - 1, room.right)
                    self.assertGreaterEqual(row, room.row)
                    self.assertLessEqual(row + height, room.row + room.height)

    def test_clamp_foot_stays_inside_walls_for_every_slot(self):
        scene = Scene(200, 60)
        scene.set_workers(self.demo())
        for room in scene._rooms():
            for worker in room.workers:
                desk_x, desk_y = scene.actors[worker.id].desk
                for dx, dy in SLOTS:
                    x, y = room.clamp_foot(desk_x + dx, desk_y + dy)
                    self.assertTrue(room.left + 9 <= x <= room.right - 9)
                    self.assertTrue(room.floor_edge(x) + 1 <= y <= room.bottom - 2)

    def test_desk_legs_clear_the_bottom_wall(self):
        # draw_room_shell paints the bottom wall from room.bottom - WALL_THICK up to room.bottom.
        wall_thick = 2
        for cols, rows in ((200, 60), (230, 60), (120, 40)):
            scene = Scene(cols, rows)
            scene.set_workers(self.demo())
            scene._sync()
            for room in scene._rooms():
                for worker in room.workers:
                    desk_x, desk_y = scene.actors[worker.id].desk
                    leg_end = desk_y + 20 + props.LEG_DROP
                    self.assertLessEqual(leg_end + 3, room.bottom - wall_thick, (cols, rows, worker.id))

    def test_seven_item_demo_group_is_one_page_with_two_desk_lines_at_200x60(self):
        pages = rooms.paginate(self.workers("demo", 7, "Reorganizar o modulo de login"), 200, 60)
        self.assertEqual(len(pages), 1)
        self.assertEqual(max(room.lines for room in pages[0]), 2)

    def test_smallest_bubble_keeps_state_line_and_two_body_rows(self):
        worker = self.workers("demo", 1, "Titulo")[0]
        worker.lines = [Line("claude", f"linha {n}") for n in range(30)]
        rows = body_rows(worker, [worker], 60, rooms.BUBBLE_MIN)
        self.assertGreaterEqual(len(rows), 3)


class Phase2SceneTests(unittest.TestCase):
    def workers(self, group, count, title):
        return [Worker(id=f"{group}-{i}", session_id="", name="n", title="t", item_label=str(i + 1),
                       group=group, index=i + 1, cwd="", started_ms=1_700_000_000_000.0, state="working",
                       room_title=title) for i in range(count)]

    def demo(self):
        return (self.workers("demo", 7, "Reorganizar o modulo de login")
                + self.workers("outra", 2, "Integrar pagamentos e permissoes")
                + self.workers("terceira", 2, "Limpar modulos antigos"))

    def test_selection_crosses_pages_and_stops_at_both_ends(self):
        scene = Scene(200, 60)
        scene.set_workers(self.demo())
        self.assertEqual(scene.page(), 0)
        scene.select(100)
        self.assertEqual(scene.selected_id, scene.workers[-1].id)
        self.assertEqual(scene.page(), 1)
        scene.select(100)
        self.assertEqual(scene.selected_id, scene.workers[-1].id)
        scene.select(-100)
        self.assertEqual(scene.selected_id, scene.workers[0].id)
        self.assertEqual(scene.page(), 0)

    def test_floor_pixel_inside_room_differs_from_corridor(self):
        scene = Scene(200, 60)
        scene.set_workers(self.demo())
        room = scene._rooms()[0]
        background = scene._background(scene._rooms())
        x, y = room.left + 20, room.bottom - 3
        self.assertNotEqual(background.rows[y][x], scene.corridor.rows[y][x])

    def test_adjacent_rooms_have_different_palettes(self):
        for page in rooms.paginate(self.demo(), 200, 60):
            for first, second in zip(page, page[1:]):
                self.assertNotEqual(first.palette, second.palette)

    def test_wall_column_is_drawn_above_the_floor(self):
        scene = Scene(200, 60)
        scene.set_workers(self.demo())
        room = scene._rooms()[0]
        background = scene._background(scene._rooms())
        x = room.left + 20
        top = room.floor_edge(x) - (room.floor_y - room.top - 2)
        self.assertEqual(background.rows[top - 1][x], props.OUTLINE)
        self.assertEqual(background.rows[top][x], props.ROOM_PALETTES[room.palette][6])

    def test_room_shell_writes_nothing_outside_the_room(self):
        page = rooms.paginate(self.demo(), 200, 60)[1]
        room = page[0]
        sentinel = (1, 2, 3)
        canvas = Canvas(200, 118, sentinel)
        props.draw_room_shell(canvas, room, rooms.display_width(room.sign))
        for y in range(canvas.height):
            for x in range(canvas.width):
                if x < room.left or x > room.right:
                    self.assertEqual(canvas.rows[y][x], sentinel)


if __name__ == "__main__":
    unittest.main()


class HoverSelectionTests(unittest.TestCase):
    WHITE = (255, 255, 255)

    def office(self) -> Office:
        workers = [make_worker(0, lines=[Line("claude", f"linha {n}") for n in range(60)]), make_worker(1, lines=[Line("claude", f"linha {n}") for n in range(60)])]
        office = Office(200, 60, sender=lambda argv, cwd: (0, ""))
        office.set_workers(workers)
        office.scene.set_workers(workers)
        return office

    def bubble_cell(self, scene: Scene, index: int) -> tuple[int, int]:
        scene.render()
        left, top, _, _ = scene._cells()[index]
        return left + 2, top + 2

    def test_motion_report_selects_a_bubble_and_a_door(self):
        office = self.office()
        office.mode = "room"
        office.render()
        col, row = self.bubble_cell(office.scene, 1)
        handle_key(office, f"\x1b[<35;{col + 1};{row + 1}M")
        self.assertEqual(office.scene.selected_id, office.scene.visible()[1].id)
        office.mode = "hall"
        hall = office.hall
        target = next((c, r) for r in range(hall.rows) for c in range(hall.cols)
                      if hall.key_at(c, r) not in (None, hall.selected_key))
        key = hall.key_at(*target)
        handle_key(office, f"\x1b[<35;{target[0] + 1};{target[1] + 1}M")
        self.assertEqual(hall.selected_key, key)

    def test_hover_over_the_composer_does_not_focus_it(self):
        office = self.office()
        office.mode = "room"
        left, top, _, _ = office.field_rect()
        handle_key(office, f"\x1b[<35;{left + 2};{top + 2}M")
        self.assertTrue(office.composer.hovered)
        self.assertFalse(office.composer.focused)

    def test_hover_while_typing_keeps_selection_and_wheel_scrolls_the_bubble_under_the_pointer(self):
        office = self.office()
        office.mode = "room"
        scene = office.scene
        scene.render()
        scene.selected_id = scene.visible()[0].id
        office.composer.focus()
        col, row = self.bubble_cell(scene, 1)
        handle_key(office, f"\x1b[<35;{col + 1};{row + 1}M")
        self.assertEqual(scene.selected_id, scene.visible()[0].id)
        handle_key(office, f"\x1b[<64;{col + 1};{row + 1}M")
        self.assertEqual(scene.selected_id, scene.visible()[0].id)
        self.assertIn(scene.visible()[1].id, scene.chat_scroll)

    def test_mouse_on_enables_motion_tracking(self):
        self.assertIn("1003", MOUSE_ON)
        self.assertIn("1003", MOUSE_OFF)

    def test_show_selection_off_draws_no_white_ring(self):
        def white_cells(show: bool) -> int:
            scene = Scene(200, 60)
            scene.set_workers([make_worker(0), make_worker(1)])
            scene.selected_id = scene.visible()[0].id
            scene.show_selection = show
            frame = scene.render()
            return sum(1 for line in frame.cells for cell in line if cell[2] == self.WHITE)
        self.assertGreater(white_cells(True), 0)
        self.assertLess(white_cells(False), white_cells(True))
