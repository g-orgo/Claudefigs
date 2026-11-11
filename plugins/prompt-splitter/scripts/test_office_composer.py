"""Tests for the writing field: draft model, drawing, keys, sending and the launch wrapper. No real claude or dispatch.py runs."""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

import claude_office
from office import composer as composer_mod
from office import pixelfont
from office.hallart import BAY_W
from office.composer import (GOLD_FOCUSED, INK_BROWN, MAX_TEXT, PAD_CELLS, PANEL_ROWS, PLATE_ROWS,
                             TEXT_TOP_ROWS, Composer, draw_composer, field_geometry)
from office.model import Worker
from office.office import Office
from office.office import DISPATCH

SCRATCH = "/tmp/claude-1000/-var-home-Orgo/d01f3965-6a05-45d6-bf5b-c6c0b5c18166/scratchpad"
FULL_ID = "full-session-id-0001"


def make_worker(state: str = "done", cwd: str = "/work/project") -> Worker:
    return Worker(
        id="w1", session_id="w1", name="n", title="Titulo do split", item_label="1", group="g",
        index=0, cwd=cwd, started_ms=0.0, state=state,
    )


def make_office(demo: bool = False, sender=None, rows: int = 50) -> Office:
    office = Office(200, rows, sender=sender or (lambda argv, cwd: (0, "")), demo=demo)
    return office


def wait_result(office: Office) -> None:
    """Blocks until the sender thread has reported, then puts the result back for drain()."""
    item = office.results.get(timeout=5)
    office.results.put(item)


class ComposerModelTests(unittest.TestCase):
    def test_insert_maps_line_breaks_and_tabs_to_space(self):
        draft = Composer()
        draft.insert("a\r\nb\tc")
        self.assertEqual(draft.text, "a  b c")

    def test_insert_drops_non_printable_characters(self):
        draft = Composer()
        draft.insert("ok\x00\x07\x1b!")
        self.assertEqual(draft.text, "ok!")

    def test_insert_caps_at_max_text(self):
        draft = Composer()
        draft.insert("x" * (MAX_TEXT + 50))
        self.assertEqual(len(draft.text), MAX_TEXT)

    def test_backspace_and_clear(self):
        draft = Composer()
        draft.insert("abc")
        draft.backspace()
        self.assertEqual(draft.text, "ab")
        draft.clear()
        self.assertEqual(draft.text, "")
        draft.backspace()
        self.assertEqual(draft.text, "")

    def test_focus_and_blur(self):
        draft = Composer()
        self.assertFalse(draft.focused)
        draft.focus()
        self.assertTrue(draft.focused)
        draft.blur()
        self.assertFalse(draft.focused)

    def test_field_geometry_is_capped_and_centered(self):
        self.assertEqual(field_geometry(200), (96, 52))
        self.assertEqual(field_geometry(60), (56, 2))


def field_snapshot(draft, tick=0, hints=()):
    """The box drawn on a uniform floor, so every changed cell belongs to it."""
    from office.term import Frame
    frame = Frame(80, PANEL_ROWS)
    for line in frame.cells:
        line[:] = [(" ", None, FLOOR, False)] * 80
    draw_composer(frame, 0, 0, 80, PANEL_ROWS, draft, "Para: x", hints, tick)
    return frame


FLOOR = (1, 2, 3)


class DrawTests(unittest.TestCase):
    def test_box_is_all_pixels_with_round_corners_over_the_floor(self):
        frame = field_snapshot(Composer())
        wide = [cell[0] for line in frame.cells for cell in line if len(cell[0]) != 1]
        self.assertEqual(wide, [])
        self.assertEqual(frame.cells[PANEL_ROWS - 1][0], (" ", None, FLOOR, False))
        self.assertNotEqual(frame.cells[PANEL_ROWS - 1][40][2], FLOOR)

    def test_caret_blinks_only_while_focused(self):
        draft = Composer()
        self.assertEqual(field_snapshot(draft, 0).cells, field_snapshot(draft, 4).cells)
        draft.focus()
        self.assertNotEqual(field_snapshot(draft, 0).cells, field_snapshot(draft, 4).cells)

    def test_typed_text_changes_the_box(self):
        draft = Composer()
        draft.focus()
        empty = field_snapshot(draft).cells
        draft.insert("ola")
        self.assertNotEqual(field_snapshot(draft).cells, empty)

    def test_hints_give_way_to_the_destination(self):
        from office.term import Frame
        frame = Frame(30, PANEL_ROWS)
        draw_composer(frame, 0, 0, 30, PANEL_ROWS, Composer(), "Para: x", ("Enter envia  Esc sai",), 0)
        plain = Frame(30, PANEL_ROWS)
        draw_composer(plain, 0, 0, 30, PANEL_ROWS, Composer(), "Para: x", (), 0)
        self.assertEqual(frame.cells, plain.cells)


class BackButtonTests(unittest.TestCase):
    def test_corners_are_transparent_and_selected_outer_rings_are_white(self):
        canvas = composer_mod._back_canvas(True)
        self.assertIsNone(canvas.rows[0][0])
        self.assertEqual(canvas.rows[8][0], composer_mod.WHITE)
        self.assertEqual(canvas.rows[2][1], composer_mod.WHITE)
        self.assertEqual(composer_mod._back_canvas(False).rows[8][0], composer_mod.OUTLINE)

    def test_arrow_is_drawn_in_ink_brown_at_the_center(self):
        canvas = composer_mod._back_canvas(False)
        self.assertEqual(canvas.rows[8][4], composer_mod.INK_BROWN)
        self.assertEqual(canvas.rows[8][11], composer_mod.INK_BROWN)

    def test_draw_back_button_leaves_frame_size_alone(self):
        from office.term import Frame
        frame = Frame(40, 20)
        composer_mod.draw_back_button(frame, 2, 3, True)
        self.assertEqual(len(frame.cells), 20)


class PixelFontTests(unittest.TestCase):
    def test_portuguese_letters_differ_from_their_base(self):
        for accented, base in zip("áàâãéêíóôõúçÁÉÃÇ", "aaaaeeiooouc" + "AEAC"):
            self.assertNotEqual(pixelfont.glyph(accented)[1], pixelfont.glyph(base)[1], accented)

    def test_every_ascii_character_has_its_own_glyph(self):
        for code in range(32, 127):
            self.assertIn(chr(code), pixelfont.GLYPHS)

    def test_glyph_rows_are_rectangular(self):
        for ch, pattern in pixelfont.GLYPHS.items():
            self.assertEqual(len({len(row) for row in pattern.split("|")}), 1, ch)

    def test_wrap_keeps_lines_inside_the_width_and_loses_no_text(self):
        text = "uma frase bem comprida com " + "x" * 60 + " no meio "
        lines = pixelfont.wrap(text, 60)
        self.assertTrue(all(pixelfont.text_width(line) <= 60 for line in lines))
        self.assertEqual("".join(lines).replace(" ", ""), text.replace(" ", ""))

    def test_clip_fits_and_marks_the_cut(self):
        clipped = pixelfont.clip("Nova sessao em um lugar comprido", 40)
        self.assertLessEqual(pixelfont.text_width(clipped), 40)
        self.assertTrue(clipped.endswith("…"))


class SextantTests(unittest.TestCase):
    def test_codes_skip_the_older_half_and_full_blocks(self):
        self.assertEqual(pixelfont._sextant(1), "\U0001FB00")
        self.assertEqual(pixelfont._sextant(20), "\U0001FB13")
        self.assertEqual(pixelfont._sextant(22), "\U0001FB14")
        self.assertEqual(pixelfont._sextant(41), "\U0001FB27")
        self.assertEqual(pixelfont._sextant(43), "\U0001FB28")
        self.assertEqual(pixelfont._sextant(62), "\U0001FB3B")
        self.assertEqual([pixelfont._sextant(v) for v in (0, 21, 42, 63)], [" ", "▌", "▐", "█"])


class PlacementTests(unittest.TestCase):
    def test_wide_hall_box_sits_on_the_floor_between_the_lower_doors(self):
        office = make_office(rows=65)
        col, top, width, rows = office.field_rect()
        self.assertEqual(office.hall.rows, 65)
        self.assertLess(top + rows, 64)
        for panel in office.hall.plan.panels:
            if panel.free:
                self.assertTrue(panel.x + BAY_W <= col or panel.x >= col + width)

    def test_room_keeps_its_desks_and_footer_clear_of_the_box(self):
        office = make_office(rows=65)
        office.mode = "room"
        _, top, _, rows = office.field_rect()
        self.assertGreaterEqual(top, office.scene.rows - 1)
        self.assertLess(top + rows, 64)
        floor = office.render().cells[office.scene.rows][0]
        self.assertNotEqual(floor[2], (38, 34, 54))
        footer = "".join(cell[0] for cell in office.render().cells[64])
        self.assertTrue(footer.strip())

    def test_click_only_counts_inside_the_box(self):
        office = make_office(rows=65)
        col, top, width, rows = office.field_rect()
        self.assertTrue(office.in_composer(col, top))
        self.assertFalse(office.in_composer(col - 1, top))
        self.assertFalse(office.in_composer(col, top + rows))


class KeyTests(unittest.TestCase):
    def test_tab_focuses_only_when_field_is_shown(self):
        office = make_office(rows=50)
        claude_office.handle_key(office, "\t")
        self.assertTrue(office.composer.focused)

        small = make_office(rows=12)
        claude_office.handle_key(small, "\t")
        self.assertFalse(small.composer.focused)

    def test_typing_inserts_only_when_focused(self):
        office = make_office()
        claude_office.handle_key(office, "a")
        self.assertEqual(office.composer.text, "")
        claude_office.handle_key(office, "\t")
        for key in "ola":
            claude_office.handle_key(office, key)
        self.assertEqual(office.composer.text, "ola")

    def test_esc_blurs_and_keeps_draft(self):
        office = make_office()
        claude_office.handle_key(office, "\t")
        claude_office.handle_key(office, "x")
        claude_office.handle_key(office, "\x1b")
        self.assertFalse(office.composer.focused)
        self.assertEqual(office.composer.text, "x")

    def test_backspace_and_ctrl_u(self):
        office = make_office()
        claude_office.handle_key(office, "\t")
        for key in "abc":
            claude_office.handle_key(office, key)
        claude_office.handle_key(office, "\x7f")
        self.assertEqual(office.composer.text, "ab")
        claude_office.handle_key(office, "\x15")
        self.assertEqual(office.composer.text, "")

    def test_enter_when_focused_calls_submit(self):
        office = make_office()
        claude_office.handle_key(office, "\t")
        with mock.patch.object(office, "submit") as submit:
            claude_office.handle_key(office, "\r")
        submit.assert_called_once_with()

    def test_click_in_field_focuses_and_click_elsewhere_blurs(self):
        office = make_office(rows=50)
        col, top, _, _ = office.field_rect()
        claude_office.handle_key(office, f"\x1b[<0;{col + 2};{top + 2}M")
        self.assertTrue(office.composer.focused)
        claude_office.handle_key(office, "\x1b[<0;10;5M")
        self.assertFalse(office.composer.focused)

    def test_wheel_still_scrolls_with_field_focused(self):
        office = make_office(rows=50)
        claude_office.handle_key(office, "\t")
        with mock.patch.object(office, "scroll") as scroll:
            claude_office.handle_key(office, "\x1b[<64;10;10M")
        scroll.assert_called_once_with(-1)


class SendTests(unittest.TestCase):
    def test_draft_leaves_at_once_and_returns_when_the_send_fails(self):
        import threading
        gate = threading.Event()
        def slow(argv, cwd):
            gate.wait(5)
            return 1, ""
        office = make_office(sender=slow)
        claude_office.handle_key(office, "\t")
        for key in "oi":
            claude_office.handle_key(office, key)
        with mock.patch.object(Office, "_write_plan", return_value="/nonexistent-plan.json"):
            office.submit()
        self.assertEqual(office.composer.text, "")
        gate.set()
        for _ in range(200):
            office.drain()
            if not office.inflight:
                break
            import time; time.sleep(0.01)
        self.assertEqual(office.composer.text, "oi")

    def setUp(self):
        os.makedirs(SCRATCH, exist_ok=True)
        self._old_tmp = tempfile.tempdir
        tempfile.tempdir = SCRATCH
        self.patch_full = mock.patch("office.office.full_session_id", return_value=FULL_ID)
        self.patch_full.start()

    def tearDown(self):
        self.patch_full.stop()
        tempfile.tempdir = self._old_tmp

    def room(self, sender, state="done", cwd="/work/project"):
        office = make_office(sender=sender)
        office.set_workers([make_worker(state, cwd)])
        office.press()
        self.assertEqual(office.mode, "room")
        return office

    def type_text(self, office, text):
        office.composer.focus()
        office.composer.insert(text)

    def test_room_send_starts_one_new_session_in_room_cwd_under_parent(self):
        calls = []

        def sender(argv, cwd):
            calls.append((argv, cwd, json.load(open(argv[2]))))
            return 0, ""

        office = make_office(sender=sender)
        workers = [make_worker("done"), make_worker("blocked"), make_worker("done")]
        for i, worker in enumerate(workers):
            worker.id = worker.session_id = f"w{i}"
            worker.parent = "parent-session"
        office.set_workers(workers)
        office.press()
        self.assertEqual(office.mode, "room")
        self.type_text(office, "novo pedido")
        office.submit()
        wait_result(office)
        office.drain()
        self.assertEqual(len(calls), 1)  # never one send per item of the room
        argv, cwd, plan = calls[0]
        self.assertEqual(argv[1], DISPATCH)
        self.assertEqual(argv[3:], ["--parent", "parent-session"])
        self.assertNotIn("--resume", argv)
        self.assertEqual(cwd, "/work/project")
        self.assertEqual(plan["cwd"], "/work/project")
        self.assertEqual([g["prompt"] for g in plan["groups"]], ["novo pedido"])
        self.assertEqual(office.composer.text, "")

    def test_room_send_works_even_when_items_are_busy(self):
        calls = []
        office = self.room(lambda argv, cwd: (calls.append(argv), (0, ""))[1], state="working")
        self.type_text(office, "ola")
        office.submit()
        wait_result(office)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1], DISPATCH)

    def test_room_send_prefixes_leading_dash_with_space(self):
        prompts = []
        office = self.room(lambda argv, cwd: (prompts.append(json.load(open(argv[2]))["groups"][0]["prompt"]), (0, ""))[1])
        self.type_text(office, "-v")
        office.submit()
        wait_result(office)
        self.assertEqual(prompts, [" -v"])

    def test_failure_restores_text_when_field_is_empty(self):
        office = self.room(lambda argv, cwd: (1, "erro"))
        self.type_text(office, "ola")
        with mock.patch.object(office, "notify") as notify:
            office.submit()
            wait_result(office)
            office.drain()
        notify.assert_called_with("Nao foi possivel enviar")
        self.assertEqual(office.composer.text, "ola")

    def test_launch_exception_counts_as_failure(self):
        def boom(argv, cwd):
            raise OSError("no claude")

        office = self.room(boom)
        self.type_text(office, "ola")
        with mock.patch.object(office, "notify") as notify:
            office.submit()
            wait_result(office)
            office.drain()
        notify.assert_called_with("Nao foi possivel enviar")

    def test_inflight_guard_blocks_second_send(self):
        office = self.room(lambda argv, cwd: (0, ""))
        office.inflight = True
        self.type_text(office, "ola")
        with mock.patch.object(office, "notify") as notify:
            office.submit()
        notify.assert_called_with("Aguarde o envio anterior")

    def test_hall_send_writes_plan_and_runs_dispatch_then_removes_plan(self):
        seen = {}

        def sender(argv, cwd):
            seen["argv"], seen["cwd"] = argv, cwd
            plan_path = argv[2]
            with open(plan_path, encoding="utf-8") as handle:
                seen["plan"] = json.load(handle)
            seen["exists"] = os.path.exists(plan_path)
            return 0, ""

        office = make_office(sender=sender)
        self.type_text(office, "criar relatorio")
        with mock.patch.object(office, "notify") as notify:
            office.submit()
            wait_result(office)
            office.drain()
        self.assertEqual(seen["argv"][0], sys.executable)
        self.assertEqual(seen["argv"][1], DISPATCH)
        self.assertIsNone(seen["cwd"])
        self.assertTrue(seen["exists"])
        group = seen["plan"]["groups"][0]
        self.assertEqual(group["title"], "criar relatorio")
        self.assertEqual(group["prompt"], "criar relatorio")
        self.assertEqual(seen["plan"]["cwd"], os.getcwd())
        self.assertFalse(os.path.exists(seen["argv"][2]))
        notify.assert_called_with("Nova sessao iniciada")

    def test_demo_never_calls_sender_and_clears_field(self):
        calls = []
        office = make_office(demo=True, sender=lambda argv, cwd: (calls.append(argv), (0, ""))[1])
        self.type_text(office, "ola")
        with mock.patch.object(office, "notify") as notify:
            office.submit()
        self.assertEqual(calls, [])
        self.assertEqual(office.composer.text, "")
        notify.assert_called_with("Demo: nada foi enviado")

    def test_destination_text_in_room_and_hall(self):
        office = self.room(lambda argv, cwd: (0, ""))
        self.assertEqual(office._destination(), "Nova sessão nesta sala")
        hall = make_office()
        self.assertTrue(hall._destination().startswith("Nova sess"))


class LaunchTests(unittest.TestCase):
    def test_launch_runs_argv_list_without_shell(self):
        with mock.patch("claude_office.subprocess.run") as run:
            run.return_value = mock.Mock(returncode=0, stdout="out", stderr="err")
            code, output = claude_office.launch(["claude", "--bg", "x"], "/work")
        self.assertEqual((code, output), (0, "outerr"))
        args, kwargs = run.call_args
        self.assertEqual(args[0], ["claude", "--bg", "x"])
        self.assertEqual(kwargs["cwd"], "/work")
        self.assertFalse(kwargs.get("shell", False))


if __name__ == "__main__":
    unittest.main()


class ImageDraftTests(unittest.TestCase):
    def setUp(self):
        os.makedirs(SCRATCH, exist_ok=True)
        self.dir = tempfile.mkdtemp(dir=SCRATCH)
        self.png = os.path.join(self.dir, "shot one.png")
        self.jpg = os.path.join(self.dir, "b.JPG")
        for path in (self.png, self.jpg):
            with open(path, "wb") as handle:
                handle.write(b"x")

    def test_attach_inserts_numbered_placeholders_and_backspace_removes_whole_token(self):
        draft = Composer()
        draft.insert("veja")
        self.assertTrue(draft.attach(self.png))
        self.assertTrue(draft.attach(self.jpg))
        self.assertEqual(draft.text, "veja [Imagem #1] [Imagem #2]")
        draft.backspace()
        self.assertEqual(draft.text, "veja [Imagem #1]")
        self.assertEqual(draft.images, {1: os.path.abspath(self.png)})
        draft.backspace()
        self.assertEqual(draft.text, "veja")
        self.assertEqual(draft.images, {})

    def test_backspace_on_typed_text_keeps_images(self):
        draft = Composer()
        draft.attach(self.png)
        draft.insert("ab")
        draft.backspace()
        self.assertEqual(draft.text, "[Imagem #1]a")
        self.assertEqual(len(draft.images), 1)

    def test_clear_drops_images_and_restarts_numbering(self):
        draft = Composer()
        draft.attach(self.png)
        draft.clear()
        self.assertEqual((draft.text, draft.images), ("", {}))
        draft.attach(self.jpg)
        self.assertEqual(draft.text, "[Imagem #1]")

    def test_prompt_text_replaces_placeholders_with_absolute_mentions(self):
        draft = Composer()
        draft.insert("veja ")
        draft.attach(self.png)
        draft.insert(" e digo")
        self.assertEqual(draft.prompt_text(), f"veja @{os.path.abspath(self.png)} e digo")

    def test_image_only_draft_is_a_valid_prompt(self):
        draft = Composer()
        draft.attach(self.jpg)
        self.assertEqual(draft.prompt_text(), f"@{os.path.abspath(self.jpg)}")

    def test_paste_of_image_paths_attaches_them_with_quotes_uri_and_escapes(self):
        draft = Composer()
        draft.paste(f'"{self.png}"')
        self.assertEqual(list(draft.images.values()), [os.path.abspath(self.png)])
        draft = Composer()
        uri = "file://" + self.png.replace(" ", "%20")
        draft.paste(uri)
        self.assertEqual(list(draft.images.values()), [os.path.abspath(self.png)])
        draft = Composer()
        draft.paste(self.png.replace(" ", "\\ ") + "\n" + self.jpg)
        self.assertEqual(len(draft.images), 2)
        self.assertEqual(draft.text, "[Imagem #1] [Imagem #2]")

    def test_paste_that_is_not_only_image_files_is_inserted_as_text(self):
        draft = Composer()
        draft.paste(f"{self.png} and more")
        self.assertEqual(draft.images, {})
        self.assertEqual(draft.text, f"{self.png} and more")
        draft = Composer()
        draft.paste(os.path.join(self.dir, "missing.png"))
        self.assertEqual((draft.images, draft.text), ({}, os.path.join(self.dir, "missing.png")))
        draft = Composer()
        draft.paste("notes.txt")
        self.assertEqual(draft.text, "notes.txt")

    def run_tool(self, outputs, fail=()):
        """A subprocess.run stand-in: `outputs` maps the tool's argv tail to stdout, `fail` lists tools that are missing."""
        def fake(argv, **kwargs):
            if argv[0] in fail:
                raise FileNotFoundError(argv[0])
            key = " ".join(argv[1:])
            if key not in outputs:
                return mock.Mock(returncode=1, stdout=b"")
            return mock.Mock(returncode=0, stdout=outputs[key])
        return mock.patch("office.clipboard.subprocess.run", side_effect=fake)

    def test_clipboard_image_is_saved_and_attached(self):
        from office import clipboard
        outputs = {"--list-types": b"text/html\nimage/png\n", "--type image/png": b"PNGDATA"}
        with self.run_tool(outputs), mock.patch.object(clipboard, "IMAGE_DIR", self.dir):
            kind, path = clipboard.read_clipboard()
        self.assertEqual(kind, "image")
        self.assertTrue(path.endswith(".png") and os.path.dirname(path) == self.dir)
        with open(path, "rb") as handle:
            self.assertEqual(handle.read(), b"PNGDATA")

    def test_clipboard_text_is_returned_when_no_image_type(self):
        from office import clipboard
        outputs = {"--list-types": b"text/plain\n", "--no-newline": b"hello"}
        with self.run_tool(outputs):
            self.assertEqual(clipboard.read_clipboard(), ("text", "hello"))

    def test_missing_clipboard_tools_report_unavailable(self):
        from office import clipboard
        with self.run_tool({}, fail=("wl-paste", "xclip")):
            self.assertEqual(clipboard.read_clipboard(), (clipboard.UNAVAILABLE, ""))

    def test_ctrl_v_attaches_clipboard_image_and_ctrl_u_clears_it(self):
        office = make_office()
        claude_office.handle_key(office, "\t")
        with mock.patch("office.office.read_clipboard", return_value=("image", self.png)):
            claude_office.handle_key(office, "\x16")
        self.assertEqual(office.composer.text, "[Imagem #1]")
        claude_office.handle_key(office, "\x15")
        self.assertEqual((office.composer.text, office.composer.images), ("", {}))

    def test_ctrl_v_without_tools_notifies_the_user(self):
        office = make_office()
        claude_office.handle_key(office, "\t")
        with mock.patch("office.office.read_clipboard", return_value=("unavailable", "")), \
                mock.patch.object(office, "notify") as notify:
            claude_office.handle_key(office, "\x16")
        notify.assert_called_once_with("Area de transferencia indisponivel")
        self.assertEqual(office.composer.text, "")

    def test_submit_sends_prompt_text_with_mentions(self):
        sent = []
        def sender(argv, cwd):
            with open(argv[2], encoding="utf-8") as handle:
                sent.append([json.load(handle)["groups"][0]["prompt"]])  # read before the plan file is removed
            return 0, ""
        office = make_office(sender=sender)
        office.set_workers([make_worker("done", "/work/project")])
        office.press()
        office.composer.focus()
        office.composer.insert("olhe ")
        office.composer.attach(self.png)
        with mock.patch("office.office.full_session_id", return_value=FULL_ID):
            office.submit()
            wait_result(office)
            office.drain()
        self.assertEqual(sent[-1][-1], f"olhe @{os.path.abspath(self.png)}")
        self.assertEqual(office.composer.text, "")
        self.assertEqual(office.composer.images, {})


class CursorModelTests(unittest.TestCase):
    def test_cursor_moves_clamps_and_clears_selection(self):
        draft = Composer()
        draft.insert("abc")
        self.assertEqual(draft.cursor, 3)
        draft.move_left()
        self.assertEqual(draft.cursor, 2)
        draft.move_home()
        self.assertEqual(draft.cursor, 0)
        draft.move_left()
        self.assertEqual(draft.cursor, 0)
        draft.move_end()
        self.assertEqual(draft.cursor, 3)
        draft.move_right()
        self.assertEqual(draft.cursor, 3)
        draft.shift_left()
        self.assertEqual(draft.selected_text(), "c")
        draft.move_left()
        self.assertEqual((draft.cursor, draft.selection()), (2, None))

    def test_placeholder_is_atomic_for_moves(self):
        draft = Composer()
        draft.insert("a")
        draft.attach("/tmp/pic.png")
        start = 2
        end = len(draft.text)
        self.assertEqual(draft.text[start:], "[Imagem #1]")
        draft.move_left()
        self.assertEqual(draft.cursor, start)
        draft.move_right()
        self.assertEqual(draft.cursor, end)
        draft.cursor = 4  # inside the placeholder
        draft.move_left()
        self.assertEqual(draft.cursor, start)
        draft.cursor = 4
        draft.move_right()
        self.assertEqual(draft.cursor, end)
        draft.move_word_left()
        self.assertEqual(draft.cursor, start)

    def test_word_moves_use_word_boundaries(self):
        draft = Composer()
        draft.insert("abc def")
        draft.move_word_left()
        self.assertEqual(draft.cursor, 4)
        draft.move_word_left()
        self.assertEqual(draft.cursor, 0)
        draft.move_word_right()
        self.assertEqual(draft.cursor, 3)

    def test_insert_backspace_and_delete_happen_at_the_cursor(self):
        draft = Composer()
        draft.insert("abcd")
        draft.cursor = 2
        draft.insert("X")
        self.assertEqual((draft.text, draft.cursor), ("abXcd", 3))
        draft.backspace()
        self.assertEqual((draft.text, draft.cursor), ("abcd", 2))
        draft.delete()
        self.assertEqual((draft.text, draft.cursor), ("abd", 2))

    def test_backspace_and_delete_remove_a_whole_placeholder(self):
        draft = Composer()
        draft.insert("a")
        draft.attach("/tmp/pic.png")
        draft.move_end()
        draft.backspace()
        self.assertEqual((draft.text, draft.images, draft.cursor), ("a", {}, 1))
        draft.attach("/tmp/pic.png")
        draft.move_home()
        draft.move_right()
        draft.move_right()  # start of the placeholder
        draft.delete()
        self.assertEqual((draft.text, draft.images, draft.cursor), ("a", {}, 1))

    def test_typing_replaces_a_selection(self):
        draft = Composer()
        draft.insert("hello")
        draft.shift_left()
        draft.shift_left()
        self.assertEqual(draft.selected_text(), "lo")
        draft.insert("X")
        self.assertEqual((draft.text, draft.cursor, draft.selection()), ("helX", 4, None))

    def test_trigger_and_accept_leave_the_text_after_the_cursor(self):
        draft = Composer()
        draft.text = "run @fiZZy"
        draft.cursor = 7
        self.assertEqual(draft.trigger(), ("file", "fi", 4))
        with mock.patch.object(draft, "suggestions", return_value=[("file.txt", "@file.txt ", "")]):
            self.assertTrue(draft.accept("/tmp"))
        self.assertEqual(draft.text, "run @file.txt ZZy")
        self.assertEqual(draft.cursor, len("run @file.txt "))

    def test_slash_command_trigger_uses_the_text_before_the_cursor(self):
        draft = Composer()
        draft.text = "/heXYZ"
        draft.cursor = 3
        self.assertEqual(draft.trigger(), ("command", "he", 0))
        with mock.patch.object(draft, "suggestions", return_value=[("/help", "/help ", "")]):
            self.assertTrue(draft.accept("/tmp"))
        self.assertEqual(draft.text, "/help XYZ")
        self.assertEqual(draft.cursor, len("/help "))

    def test_clear_and_restore_put_the_cursor_in_a_valid_place(self):
        draft = Composer()
        draft.insert("abc")
        draft.move_home()
        draft.clear()
        self.assertEqual(draft.cursor, 0)
        draft.restore(("draft", {}, set()))
        self.assertEqual(draft.cursor, len("draft"))


class CursorKeyTests(unittest.TestCase):
    def focused_office(self):
        office = make_office()
        claude_office.handle_key(office, "\t")
        return office

    def test_application_mode_arrows_are_single_keys(self):
        self.assertEqual(claude_office.keys_of("\x1bOA\x1bOB\x1bOC\x1bOD"), ["\x1b[A", "\x1b[B", "\x1b[C", "\x1b[D"])
        self.assertTrue(claude_office.PARTIAL.fullmatch("\x1bO"))

    def test_up_and_down_walk_wrapped_lines_and_keep_focus(self):
        office = self.focused_office()
        for key in "palavra " * 40:
            claude_office.handle_key(office, key)
        office.render()  # the draw stores the wrapped lines the arrows walk.
        draft = office.composer
        self.assertGreater(len(draft._lines), 2)
        end = draft.cursor
        claude_office.handle_key(office, "\x1b[A")
        self.assertTrue(draft.focused)
        self.assertEqual(office.mode, "hall")
        line = composer_mod._cursor_line(draft.cursor, list(draft._starts), len(draft._lines))
        self.assertEqual(line, len(draft._lines) - 2)
        claude_office.handle_key(office, "\x1b[B")
        claude_office.handle_key(office, "\x1b[B")  # Down on the last line goes to the end of the draft.
        self.assertEqual(draft.cursor, end)
        for _ in range(len(draft._lines)):
            claude_office.handle_key(office, "\x1b[A")
        self.assertEqual(draft.cursor, 0)
        for key in claude_office.keys_of("\x1bOB" * (len(draft._lines) + 1)):
            claude_office.handle_key(office, key)
        self.assertEqual(draft.cursor, end)
        self.assertTrue(draft.focused)

    def test_arrow_home_and_end_sequences_move_the_cursor(self):
        office = self.focused_office()
        for key in "abc":
            claude_office.handle_key(office, key)
        claude_office.handle_key(office, "\x1b[D")
        self.assertEqual(office.composer.cursor, 2)
        for key in ("\x1b[H", "\x1b[1~", "\x1bOH"):
            claude_office.handle_key(office, key)
            self.assertEqual(office.composer.cursor, 0)
        for key in ("\x1b[F", "\x1b[4~", "\x1bOF"):
            claude_office.handle_key(office, key)
            self.assertEqual(office.composer.cursor, 3)

    def test_ctrl_arrows_move_by_word_and_delete_removes_forward(self):
        office = self.focused_office()
        for key in "abc def":
            claude_office.handle_key(office, key)
        claude_office.handle_key(office, "\x1b[1;5D")
        self.assertEqual(office.composer.cursor, 4)
        claude_office.handle_key(office, "\x1b[H")
        claude_office.handle_key(office, "\x1b[3~")
        self.assertEqual(office.composer.text, "bc def")

    def test_shift_keys_extend_selection_and_copy_each_change(self):
        office = self.focused_office()
        for key in "abc":
            claude_office.handle_key(office, key)
        with mock.patch("office.clipboard.write_clipboard") as write:
            claude_office.handle_key(office, "\x1b[1;2D")
            write.assert_called_once_with("c")
            claude_office.handle_key(office, "\x1b[1;2D")
            write.assert_called_with("bc")
            claude_office.handle_key(office, "\x1b[1;6D")  # ctrl+shift+left: the whole word
            write.assert_called_with("abc")
        self.assertEqual(office.composer.selected_text(), "abc")

    def test_shift_home_and_end_sequences_select_to_the_edges(self):
        office = self.focused_office()
        for key in "abc":
            claude_office.handle_key(office, key)
        with mock.patch("office.clipboard.write_clipboard") as write:
            claude_office.handle_key(office, "\x1b[1;2H")
            write.assert_called_once_with("abc")
        office.composer.move_end()
        with mock.patch("office.clipboard.write_clipboard") as write:
            claude_office.handle_key(office, "\x1b[1;2H")
            write.assert_called_once_with("abc")


class MouseSelectionTests(unittest.TestCase):
    def setUp(self):
        self.office = make_office(rows=50)
        claude_office.handle_key(self.office, "\t")
        self.office.composer.insert("hello")
        self.office.render()
        self.col, self.top, _, _ = self.office.field_rect()
        self.x = self.col + PAD_CELLS
        self.first = self.top + PLATE_ROWS + TEXT_TOP_ROWS

    def cell(self, col, row):
        return f"\x1b[<{0 if row is None else 0};{col + 1};{row + 1}M"

    def test_index_at_maps_cells_to_text_indices(self):
        draft = self.office.composer
        self.assertEqual(draft.index_at(self.x, self.first), 0)
        end_x = self.x + (pixelfont.text_width("hello") + 1) // pixelfont.CELL_X
        self.assertEqual(draft.index_at(end_x, self.first), 5)
        self.assertEqual(draft.index_at(self.x + 100, self.first), 5)

    def test_press_drag_and_release_select_and_copy_once(self):
        end_x = self.x + (pixelfont.text_width("hello") + 1) // pixelfont.CELL_X
        with mock.patch("office.clipboard.write_clipboard") as write:
            claude_office.handle_key(self.office, f"\x1b[<0;{self.x + 1};{self.first + 1}M")
            self.assertEqual(self.office.composer.cursor, 0)
            self.assertTrue(self.office.composer.dragging)
            claude_office.handle_key(self.office, f"\x1b[<32;{end_x + 1};{self.first + 1}M")
            self.assertEqual(self.office.composer.selected_text(), "hello")
            write.assert_not_called()  # motion does not copy.
            claude_office.handle_key(self.office, f"\x1b[<0;{end_x + 1};{self.first + 1}m")
            write.assert_called_once_with("hello")
        self.assertFalse(self.office.composer.dragging)
        self.assertEqual(self.office.composer.selected_text(), "hello")

    def test_hover_motion_without_a_button_does_not_select(self):
        with mock.patch.object(self.office, "hover") as hover, \
                mock.patch("office.clipboard.write_clipboard") as write:
            claude_office.handle_key(self.office, f"\x1b[<35;{self.x + 1};{self.first + 1}M")
        hover.assert_called_once()
        write.assert_not_called()
        self.assertIsNone(self.office.composer.selection())


class CursorDrawTests(unittest.TestCase):
    def test_caret_is_drawn_at_the_cursor_column(self):
        draft = Composer()
        draft.focus()
        draft.insert("abc")
        draft.move_home()
        frame = field_snapshot(draft, 0)
        self.assertEqual(frame.cells[TEXT_TOP_ROWS + PLATE_ROWS + 2][PAD_CELLS][1], INK_BROWN)
        end_x = PAD_CELLS + (pixelfont.text_width("abc") + 1) // pixelfont.CELL_X
        draft.move_end()
        frame = field_snapshot(draft, 0)
        self.assertEqual(frame.cells[TEXT_TOP_ROWS + PLATE_ROWS + 2][end_x][1], INK_BROWN)
        self.assertNotEqual(frame.cells[TEXT_TOP_ROWS + PLATE_ROWS + 2][end_x],
                            field_snapshot(draft, 4).cells[TEXT_TOP_ROWS + PLATE_ROWS + 2][end_x])

    def test_visible_window_follows_the_cursor(self):
        draft = Composer()
        draft.focus()
        draft.insert("word " * 60)
        draft.move_home()
        field_snapshot(draft)
        self.assertEqual(draft._window, 0)
        self.assertEqual(draft.index_at(PAD_CELLS, TEXT_TOP_ROWS + PLATE_ROWS), 0)
        draft.move_end()
        field_snapshot(draft)
        self.assertGreater(draft._window, 0)
        self.assertGreater(draft.index_at(PAD_CELLS, TEXT_TOP_ROWS + PLATE_ROWS), 0)

    def test_selection_is_highlighted_only_while_focused(self):
        draft = Composer()
        draft.focus()
        draft.insert("abc")
        draft.move_home(True)
        frame = field_snapshot(draft, 0)
        self.assertEqual(frame.cells[TEXT_TOP_ROWS + PLATE_ROWS][PAD_CELLS][2], GOLD_FOCUSED)
        draft.blur()
        frame = field_snapshot(draft, 0)
        self.assertNotEqual(frame.cells[TEXT_TOP_ROWS + PLATE_ROWS][PAD_CELLS][2], GOLD_FOCUSED)
