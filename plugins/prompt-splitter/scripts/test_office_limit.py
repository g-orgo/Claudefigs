"""Tests for the room send (only to the room's parent session, never a broadcast) and the batch job of the office viewer, with a mock sender."""
import os
import sys
import time
import unittest
from datetime import datetime
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from office.model import Worker  # noqa: E402
from office import notice  # noqa: E402
from office.office import Office  # noqa: E402


def make(wid, state="done", session="abc", attachable=False, parent="p1"):
    return Worker(id=wid, session_id=session, name="n", title=f"Split {wid}", item_label="1", group="g", index=1,
                  cwd="/work", started_ms=0.0, state=state, parent=parent, attachable=attachable)


class RoomSendTest(unittest.TestCase):
    def office(self, workers, code=0, output=""):
        sender = mock.Mock(return_value=(code, output))
        patch = mock.patch("office.office.full_session_id", side_effect=lambda value: value)  # no real transcripts
        patch.start()
        self.addCleanup(patch.stop)
        agents = mock.patch("office.office.load_agents_once", return_value=[])  # no real agent registry
        agents.start()
        self.addCleanup(agents.stop)
        office = Office(200, 60, sender=sender)
        office.mode = "room"
        office.door_key = "p1"
        office.set_workers(workers)
        office.composer.focus()
        office.composer.insert("oi a todos")
        return office, sender

    def run_submit(self, office):
        office.submit()
        for _ in range(500):
            if not office.inflight:
                break
            time.sleep(0.01)
        office.drain()

    def test_room_message_goes_only_to_the_parent_session(self):
        office, sender = self.office([make("a"), make("b", state="working"), make("c", state="waiting"), make("d")])
        self.assertTrue(office._destination().startswith("Para: sessao da sala"))
        with mock.patch("office.office.subprocess.run") as run:
            self.run_submit(office)
        run.assert_not_called()  # no item of the room is stopped or resumed
        self.assertEqual(sender.call_count, 1)
        argv = sender.call_args.args[0]
        self.assertEqual(argv[:4], ["claude", "--bg", "--resume", "p1"])
        self.assertTrue(argv[4].endswith("oi a todos"))

    def test_registered_idle_parent_is_stopped_before_resume(self):
        office, sender = self.office([make("a")])
        agents = [{"id": "p1short", "sessionId": "p1", "state": "blocked"}]
        with mock.patch("office.office.load_agents_once", return_value=agents), \
                mock.patch("office.office.subprocess.run") as run:
            self.run_submit(office)
        self.assertEqual(run.call_args.args[0], ["claude", "stop", "p1short"])
        self.assertEqual(sender.call_count, 1)

    def test_running_parent_refuses_instead_of_copying(self):
        office, sender = self.office([make("a")])
        agents = [{"id": "p1short", "sessionId": "p1", "state": "working"}]
        with mock.patch("office.office.load_agents_once", return_value=agents), \
                mock.patch.object(office, "notify") as notify:
            self.run_submit(office)
        self.assertEqual(sender.call_count, 0)
        notify.assert_called_with("A sessao da sala esta rodando: envie quando ela parar")
        self.assertEqual(office.composer.text, "oi a todos")

    def test_batch_shape_is_generic(self):
        office, _ = self.office([make("a")])
        job = {"kind": "room", "batch": True, "draft": None, "prompt": "x", "total": 1,
               "counts": {"busy": 0, "waiting": 0, "no_session": 0},
               "targets": [{"worker_id": "a", "session_id": "abc", "cwd": "/work", "attachable": False, "title": "t"}]}
        office._run_batch(job)
        _, ok, _ = office.results.get_nowait()
        self.assertTrue(ok)
        self.assertEqual(job["outcomes"][0]["ok"], True)

    def test_failed_send_restores_draft(self):
        office, _ = self.office([make("a")], code=1)
        self.run_submit(office)
        self.assertEqual(office.composer.text, "oi a todos")


class NoticeTest(unittest.TestCase):
    def office(self, cols=200, rows=60, workers=()):
        patch = mock.patch("office.office.full_session_id", side_effect=lambda value: value)  # no real transcripts
        patch.start()
        self.addCleanup(patch.stop)
        office = Office(cols, rows, sender=mock.Mock(return_value=(0, "")))
        office.workers = list(workers)
        return office

    def test_limit_text_plural_and_known_reset(self):
        reset = now_ms() + HOUR
        workers = [limited(f"w{i}", reset=reset) for i in range(3)]
        plate, lines = notice.limit_content(workers)
        when = datetime.fromtimestamp(reset / 1000).strftime("%H:%M")
        self.assertEqual(plate, "Limite de uso")
        self.assertEqual(lines, ("3 sessões pararam no limite de 5 horas", f"Libera às {when}. Continuo sozinho quando você voltar."))

    def test_limit_text_singular_and_unknown_reset(self):
        plate, lines = notice.limit_content([limited("a", limit="weekly")])
        self.assertEqual(lines[0], "1 sessão parou no limite semanal")
        self.assertEqual(lines[1], "Libera em breve. Continuo sozinho quando você voltar.")

    def test_limit_text_mixed_kinds_uses_most_common(self):
        workers = [limited("a", limit="session"), limited("b", limit="weekly"), limited("c", limit="session")]
        self.assertEqual(notice.limit_content(workers)[1][0], "3 sessões pararam no limite da sessão")

    def test_resume_text_with_and_without_failures(self):
        self.assertEqual(notice.resume_content(2, 0), ("Limite liberado", ("Continuando 2 sessões",)))
        self.assertEqual(notice.resume_content(1, 2), ("Limite liberado", ("Continuando 1 sessão", "2 não puderam continuar")))
        self.assertEqual(notice.resume_content(0, 1), ("Limite liberado", ("1 não pôde continuar",)))
        self.assertIsNone(notice.resume_content(0, 0))

    def test_new_limit_key_shows_once(self):
        worker = limited("a", reset=now_ms() + HOUR)
        office = self.office()
        office.workers = [worker]
        office._announce_limits()
        self.assertTrue(office.notice.visible(office.tick))
        office.notice.close()
        office._announce_limits()  # same key again: stays hidden.
        self.assertFalse(office.notice.visible(office.tick))

    def test_first_load_with_limited_worker_shows(self):
        worker = limited("a", reset=now_ms() + HOUR)
        office = self.office()
        office.set_workers([worker])
        self.assertTrue(office.notice.visible(office.tick))

    def test_auto_hide_after_tick_budget(self):
        office = self.office()
        office.notice.show("Limite de uso", ("x",), office.tick)
        office.tick += notice.SHOW_TICKS - 1
        self.assertTrue(office.notice.visible(office.tick))
        office.tick += 1
        self.assertFalse(office.notice.visible(office.tick))

    def test_esc_closes_only_when_composer_not_focused(self):
        import claude_office
        office = self.office()
        office.notice.show("Limite de uso", ("x",), office.tick)
        office.composer.focus()
        claude_office.handle_key(office, "\x1b")
        self.assertTrue(office.notice.visible(office.tick))  # the field keeps Esc.
        office.composer.blur()
        claude_office.handle_key(office, "\x1b")
        self.assertFalse(office.notice.visible(office.tick))

    def test_click_inside_closes_and_does_not_select(self):
        import claude_office
        office = self.office()
        office.notice.show("Limite de uso", ("x",), office.tick)
        placed = office.notice_place()
        with mock.patch.object(office, "click") as click:
            claude_office.handle_key(office, f"\x1b[<0;{placed.col + 2};{placed.top + 2}M")
            claude_office.handle_key(office, f"\x1b[<0;{placed.col + 2};{placed.top + 2}m")
        click.assert_not_called()
        self.assertFalse(office.notice.visible(office.tick))

    def test_render_fits_frame_at_two_sizes(self):
        for cols, rows in ((200, 60), (80, 24)):
            office = self.office(cols, rows)
            office.notice.show("Limite liberado", ("Continuando 3 sessões", "1 não pôde continuar"), office.tick)
            frame = office.render()
            self.assertEqual((frame.cols, frame.nrows), (cols, rows))
            placed = office.notice_place()
            self.assertIsNotNone(placed)
            self.assertLessEqual(placed.col + placed.width, cols)
            self.assertGreaterEqual(placed.top, 0)
            self.assertLessEqual(placed.top + placed.rows, rows)

    def test_hidden_when_viewer_too_small(self):
        office = self.office(30, 12)
        office.notice.show("Limite liberado", ("Continuando 1 sessão",), office.tick)
        self.assertIsNone(office.notice_place())
        office.render()


if __name__ == "__main__":
    unittest.main()


RESUME_PROMPT = "Continue de onde parou: o limite de uso foi liberado."
HOUR = 3600 * 1000


def now_ms() -> float:
    return time.time() * 1000


def limited(wid, limit="5-hour", at=None, reset=0.0, state="done", session="abc"):
    worker = make(wid, state=state, session=session)
    worker.limit = limit
    worker.limit_at_ms = now_ms() - HOUR if at is None else at
    worker.limit_reset_ms = reset
    return worker


class LimitResumeTest(unittest.TestCase):
    def office(self, workers=(), code=0, demo=False):
        sender = mock.Mock(return_value=(code, ""))
        patch = mock.patch("office.office.full_session_id", side_effect=lambda value: value)  # no real transcripts
        patch.start()
        self.addCleanup(patch.stop)
        office = Office(200, 60, sender=sender, demo=demo)
        office.workers = list(workers)  # direct, so the first-set_workers trigger stays out of these tests.
        return office, sender

    def drain_batch(self, office):
        item = office.results.get(timeout=5)  # the batch thread reports here; put it back for drain().
        office.results.put(item)
        office.drain()

    def test_reset_passed_is_due_and_not_passed_is_not(self):
        due = limited("a", reset=now_ms() - 60_000)
        later = limited("b", reset=now_ms() + HOUR)
        office, _ = self.office([due, later])
        self.assertEqual([w.id for w in office._resume_due(now_ms())], ["a"])

    def test_unknown_reset_waits_fifteen_minutes(self):
        early = limited("a", at=now_ms() - 10 * 60_000)
        late = limited("b", at=now_ms() - 20 * 60_000)
        office, _ = self.office([early, late])
        self.assertEqual([w.id for w in office._resume_due(now_ms())], ["b"])

    def test_recency_is_24_hours_or_8_days_for_weekly(self):
        old = limited("a", at=now_ms() - 25 * HOUR)
        weekly = limited("b", limit="weekly", at=now_ms() - 25 * HOUR)
        too_old = limited("c", limit="weekly", at=now_ms() - 9 * 24 * HOUR)
        office, _ = self.office([old, weekly, too_old])
        self.assertEqual([w.id for w in office.limited_workers()], ["b"])

    def test_resumed_key_and_busy_or_waiting_are_excluded(self):
        done = limited("a", reset=now_ms() - 1)
        busy = limited("b", reset=now_ms() - 1, state="working")
        waiting = limited("c", reset=now_ms() - 1, state="waiting")
        office, _ = self.office([done, busy, waiting])
        office.resumed.add((done.id, done.limit_at_ms))
        self.assertEqual(office._resume_due(now_ms()), [])

    def test_user_active_sends_one_batch_with_exact_argv(self):
        worker = limited("a", reset=now_ms() - 1)
        office, sender = self.office([worker])
        office.user_active()
        self.drain_batch(office)
        sender.assert_called_once_with(["claude", "--bg", "--resume", "abc", RESUME_PROMPT], "/work")
        self.assertEqual(office.last_resume, (1, 0))

    def test_user_active_does_nothing_in_demo_or_while_inflight(self):
        worker = limited("a", reset=now_ms() - 1)
        office, sender = self.office([worker], demo=True)
        office.user_active()
        self.assertFalse(sender.called)
        office.demo = False
        office.inflight = True
        office.user_active()
        self.assertFalse(sender.called)

    def test_failed_outcome_leaves_resumed_so_it_retries(self):
        worker = limited("a", reset=now_ms() - 1)
        office, sender = self.office([worker], code=1)
        office.user_active()
        self.drain_batch(office)
        self.assertNotIn((worker.id, worker.limit_at_ms), office.resumed)
        self.assertEqual(office.last_resume, (0, 1))
        sender.return_value = (0, "")
        office.user_active()
        self.drain_batch(office)
        self.assertEqual(sender.call_count, 2)

    def test_screen_change_triggers_user_active(self):
        worker = limited("a", reset=now_ms() - 1)
        office, sender = self.office([worker])
        office._go("p1")
        self.drain_batch(office)
        self.assertEqual(sender.call_count, 1)

    def test_first_non_empty_set_workers_triggers_user_active(self):
        worker = limited("a", reset=now_ms() - 1)
        office, sender = self.office([])
        office.set_workers([worker])
        self.drain_batch(office)
        self.assertEqual(sender.call_count, 1)


class FocusKeysTest(unittest.TestCase):
    def test_focus_tokens_are_single_keys(self):
        import claude_office
        self.assertEqual(claude_office.keys_of("\x1b[I"), ["\x1b[I"])
        self.assertEqual(claude_office.keys_of("a\x1b[Ob"), ["a", "\x1b[O", "b"])

    def test_cut_focus_token_stays_pending(self):
        import claude_office
        keys = claude_office.keys_of("\x1b[")
        self.assertTrue(claude_office.PARTIAL.fullmatch(keys[-1]))
