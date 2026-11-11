"""Tests for the questions a dispatched session asks, answered from the office box. No real claude runs."""
import json
import os
import tempfile
import unittest
from unittest import mock

import claude_office
from office import data
from office.model import Question, Worker
from office.office import Office

FULL_ID = "full-session-id-0001"


def ask_worker(wid: str = "w1", asked_ms: float = 10.0, multi: bool = False) -> Worker:
    questions = [
        Question(ask=f"ask-{wid}", header="Cor", text="Qual cor?", options=(("Azul", "frio"), ("Verde", "")), asked_ms=asked_ms),
        Question(ask=f"ask-{wid}", header="Itens", text="Quais itens?", options=(("A", ""), ("B", ""), ("C", "")),
                 multi=True, asked_ms=asked_ms),
    ]
    return Worker(id=wid, session_id=wid, name="n", title=f"Split {wid}", item_label="1", group="g", index=1,
                  cwd="/work", started_ms=0.0, state="ask", questions=questions[: 2 if multi else 1])


def office_with(*workers, sender=None) -> Office:
    office = Office(200, 50, sender=sender or (lambda argv, cwd: (0, "")))
    office.set_workers(list(workers))
    return office


def press(office: Office, *keys: str) -> None:
    for key in keys:
        claude_office.handle_key(office, key)


class PendingQuestionsTests(unittest.TestCase):
    def write(self, entries) -> str:
        folder = tempfile.mkdtemp()
        path = os.path.join(folder, "child.jsonl")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(json.dumps(e) for e in entries) + "\n")
        return path

    def ask_entry(self) -> dict:
        tool_input = {"questions": [{"question": "Qual cor?", "header": "Cor", "multiSelect": True,
                                     "options": [{"label": "Azul", "description": "frio"}, {"label": "Verde"}]}]}
        return {"type": "assistant", "timestamp": "2026-11-10T10:00:00Z", "message": {"content": [
            {"type": "tool_use", "id": "t1", "name": "AskUserQuestion", "input": tool_input}]}}

    def test_unanswered_question_is_read(self):
        questions = data.pending_questions(self.write([self.ask_entry()]))
        self.assertEqual(len(questions), 1)
        self.assertEqual((questions[0].ask, questions[0].text, questions[0].multi), ("t1", "Qual cor?", True))
        self.assertEqual(questions[0].options, (("Azul", "frio"), ("Verde", "")))
        self.assertGreater(questions[0].asked_ms, 0)

    def test_answered_question_is_gone(self):
        result = {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": "ok"}]}}
        self.assertEqual(data.pending_questions(self.write([self.ask_entry(), result])), [])

    def write_job(self, state: dict) -> str:
        jobs = tempfile.mkdtemp()
        os.makedirs(os.path.join(jobs, "abcd1234"))
        with open(os.path.join(jobs, "abcd1234", "state.json"), "w", encoding="utf-8") as handle:
            json.dump(state, handle)
        return jobs

    def test_live_job_block_is_read(self):
        block = {"questions": [{"question": "Qual cor?", "options": [{"label": "Azul", "description": "frio"}]}]}
        jobs = self.write_job({"needs": "answer: Qual cor? (Azul)", "updatedAt": "2026-11-10T03:37:56Z", "block": block})
        questions = data.job_questions("abcd1234", jobs)
        self.assertEqual([(q.text, q.options, q.multi) for q in questions], [("Qual cor?", (("Azul", "frio"),), False)])
        self.assertTrue(questions[0].ask.startswith("job:abcd1234:"))

    def test_stale_job_block_is_ignored(self):
        block = {"questions": [{"question": "Velha?", "options": []}]}
        self.assertEqual(data.job_questions("abcd1234", self.write_job({"needs": None, "block": block})), [])

    def test_agent_waiting_for_input_is_ask(self):
        agent = {"status": "waiting", "waitingFor": "input needed", "state": "blocked"}
        self.assertEqual(data.map_state({}, agent, "", 0.0, 0.0), ("ask", "none"))

    def test_missing_transcript_has_no_questions(self):
        self.assertEqual(data.pending_questions("/nonexistent/x.jsonl"), [])


class AskingFlowTests(unittest.TestCase):
    def test_question_shows_in_every_view_and_grows_the_box(self):
        plain = office_with()
        office = office_with(ask_worker(multi=True))
        self.assertIsNotNone(office.asking)
        self.assertGreater(office.field_rect()[3], plain.field_rect()[3])
        for toggle in (office.toggle_warehouse, office.toggle_warehouse):
            self.assertTrue(office._destination().startswith("Pergunta de: Split w1"))
            office.render()
            toggle()

    def test_keys_answer_every_question_and_send_them(self):
        sent = []
        office = office_with(ask_worker(multi=True), sender=lambda argv, cwd: (sent.append((argv, cwd)) or (0, "")))
        with mock.patch("office.office.full_session_id", return_value=FULL_ID):
            press(office, "\t", "\x1b[B", "\r")  # Verde on the first question
            self.assertEqual(office.asking.current, 1)
            press(office, " ", "\x1b[B", "\x1b[B", " ", "\r")  # A and C on the second
            office.results.put(office.results.get(timeout=5))
            office.drain()
        argv, cwd = sent[0]
        self.assertEqual(argv[:4], ["claude", "--bg", "--resume", FULL_ID])
        self.assertIn('"Qual cor?" = "Verde"', argv[4])
        self.assertIn('"Quais itens?" = "A, C"', argv[4])
        self.assertEqual(cwd, "/work")
        self.assertIsNone(office.asking)  # hidden until the transcript shows the answer
        office.set_workers([ask_worker(multi=True)])
        self.assertIsNone(office.asking)

    def test_typed_text_is_the_answer(self):
        office = office_with(ask_worker())
        press(office, "\t", *"rosa")
        self.assertEqual(office.composer.text, "rosa")
        with mock.patch("office.office.full_session_id", return_value=FULL_ID):
            press(office, "\r")
        self.assertEqual(office.results.get(timeout=5)[0]["asking"].answers, ["rosa"])

    def test_click_on_option_answers_a_single_choice(self):
        office = office_with(ask_worker())
        office.render()
        row = next(r for r, qi, oi in office.asking._rows if oi == 1)
        with mock.patch("office.office.full_session_id", return_value=FULL_ID):
            press(office, f"\x1b[<0;{office.asking._cols[0] + 3};{row + 1}M")
        self.assertEqual(office.results.get(timeout=5)[0]["asking"].answers, ["Verde"])

    def test_failed_send_brings_the_answers_back(self):
        office = office_with(ask_worker(), sender=lambda argv, cwd: (1, "erro"))
        with mock.patch("office.office.full_session_id", return_value=FULL_ID):
            press(office, "\t", "\r")
            office.results.put(office.results.get(timeout=5))
            office.drain()
        self.assertIsNotNone(office.asking)
        self.assertEqual(office.asking.answers, ["Azul"])

    def test_ctrl_x_postpones_to_the_next_session(self):
        office = office_with(ask_worker("old", 1.0), ask_worker("new", 2.0))
        self.assertEqual(office.asking.worker.id, "new")
        press(office, "\x18")
        self.assertEqual(office.asking.worker.id, "old")
        press(office, "\x18")
        self.assertIsNone(office.asking)

    def test_a_draft_being_typed_keeps_the_box(self):
        office = office_with()
        press(office, "\t", *"oi")
        office.set_workers([ask_worker()])
        self.assertIsNone(office.asking)
        self.assertEqual(office.composer.text, "oi")
        press(office, "\x1b")
        office.step()
        self.assertIsNotNone(office.asking)
        office.postpone()
        self.assertEqual(office.composer.text, "oi")  # the draft waited under the question


if __name__ == "__main__":
    unittest.main()
