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
from office.composer import MAX_TEXT, PANEL_ROWS, Composer, draw_composer, field_geometry
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

    def test_room_send_uses_resume_argv_and_worker_cwd(self):
        calls = []

        def sender(argv, cwd):
            calls.append((argv, cwd))
            return 0, ""

        office = self.room(sender)
        self.type_text(office, "ola")
        with mock.patch.object(office, "notify") as notify:
            office.submit()
            wait_result(office)
            office.drain()
        self.assertEqual(calls, [(["claude", "--bg", "--resume", FULL_ID, "ola"], "/work/project")])
        self.assertEqual(office.composer.text, "")
        notify.assert_called_with("Enviado para Titulo do split")

    def test_room_send_prefixes_leading_dash_with_space(self):
        calls = []
        office = self.room(lambda argv, cwd: (calls.append(argv), (0, ""))[1])
        self.type_text(office, "-v")
        office.submit()
        wait_result(office)
        self.assertEqual(calls[0][-1], " -v")

    def test_busy_session_is_not_sent(self):
        calls = []
        office = self.room(lambda argv, cwd: (calls.append(argv), (0, ""))[1], state="working")
        self.type_text(office, "ola")
        with mock.patch.object(office, "notify") as notify:
            office.submit()
        self.assertEqual(calls, [])
        notify.assert_called_with("Esta sessao esta rodando: espere terminar para enviar")
        self.assertEqual(office.composer.text, "ola")

    def test_copy_wording_gets_copy_notice(self):
        office = self.room(lambda argv, cwd: (0, "Criada uma copia da sessao"))
        self.type_text(office, "ola")
        with mock.patch.object(office, "notify") as notify:
            office.submit()
            wait_result(office)
            office.drain()
        notify.assert_called_with("A sessao estava ativa: continuou em uma copia")

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

    def test_room_without_selection_is_refused(self):
        office = self.room(lambda argv, cwd: (0, ""))
        office.scene.selected_id = None
        self.type_text(office, "ola")
        with mock.patch.object(office, "notify") as notify:
            office.submit()
        notify.assert_called_with("Selecione um item primeiro")

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
        self.assertEqual(office._destination(), "Para: Titulo do split")
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
