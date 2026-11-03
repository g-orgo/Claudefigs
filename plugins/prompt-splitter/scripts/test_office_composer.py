"""Tests for the writing field: draft model, drawing, keys, sending and the launch wrapper. No real claude or dispatch.py runs."""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

import claude_office
from office import composer as composer_mod
from office.composer import MAX_TEXT, Composer, draw_composer, field_geometry
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
        self.assertEqual(field_geometry(200), (120, 40))
        self.assertEqual(field_geometry(60), (56, 2))


class DrawTests(unittest.TestCase):
    def test_draws_placeholder_and_border_in_four_rows(self):
        from office.term import Frame
        frame = Frame(80, 4)
        draw_composer(frame, 0, Composer(), "Para: x", "Enter envia", 0)
        top_row = "".join(cell[0] for cell in frame.cells[0])
        bottom_row = "".join(cell[0] for cell in frame.cells[3])
        self.assertIn("╭", top_row)
        self.assertIn("╰", bottom_row)
        middle = "".join(cell[0] for cell in frame.cells[1])
        self.assertIn("Aperte Tab para escrever", middle)

    def test_draws_focused_placeholder(self):
        from office.term import Frame
        draft = Composer()
        draft.focus()
        frame = Frame(80, 4)
        draw_composer(frame, 0, draft, "Para: x", "Enter envia", 0)
        middle = "".join(cell[0] for cell in frame.cells[1])
        self.assertIn("Escreva aqui", middle)


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
        claude_office.handle_key(office, "\x1b[<0;10;47M")
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
