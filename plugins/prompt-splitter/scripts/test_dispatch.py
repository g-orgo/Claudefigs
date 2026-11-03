"""Tests for dispatch ordering, waiting records, the waiter and status listing.

Run with: python3 -m pytest -q scripts/test_dispatch.py  (or python3 scripts/test_dispatch.py)
Subprocess calls are mocked and the state directory is a temp dir: no real session is launched.
"""

import contextlib
import io
import json
import os
import re
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import dispatch  # noqa: E402
import status  # noqa: E402


def plan_file(directory: str, groups: list[dict]) -> str:
    path = os.path.join(directory, "plan.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"cwd": directory, "groups": groups}, fh)
    return path


def read_records(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


class DispatchTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.state_dir = os.path.join(self.tmp, "state")
        self.state_file = os.path.join(self.state_dir, "prompt-splitter.jsonl")
        patches = [
            mock.patch.object(dispatch, "STATE_DIR", self.state_dir),
            mock.patch.object(dispatch, "STATE_FILE", self.state_file),
            mock.patch.object(dispatch, "find_parent_transcript", return_value=""),
            mock.patch.object(dispatch, "open_konsole"),
        ]
        self.start = mock.patch.object(dispatch, "start_group", side_effect=self._fake_start).start()
        self.spawn = mock.patch.object(dispatch, "spawn_waiter", return_value="log").start()
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.addCleanup(mock.patch.stopall)
        self.counter = 0

    def _fake_start(self, group, cwd, mode):
        self.counter += 1
        return f"sid-{self.counter}", "split-" + group["name"]

    def run_main(self, groups, extra=None):
        path = plan_file(self.tmp, groups)
        argv = ["dispatch.py", path] + (extra or [])
        with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()):
            return dispatch.main()

    def test_order_is_topological_and_stable(self):
        groups = [
            {"name": "a", "prompt": "pa", "after": ["c"]},
            {"name": "b", "prompt": "pb"},
            {"name": "c", "prompt": "pc"},
        ]
        names = [g["name"] for g in dispatch.order_groups(groups)]
        self.assertEqual(names, ["b", "c", "a"])

    def test_sync_chain_waits_each_group_on_previous(self):
        groups = [
            {"name": "one", "prompt": "1"},
            {"name": "two", "prompt": "2", "after": ["one"]},
            {"name": "three", "prompt": "3", "after": ["two"]},
        ]
        self.assertEqual(self.run_main(groups), 0)
        records = read_records(self.state_file)
        self.assertEqual([r["index"] for r in records], [1, 2, 3])
        self.assertEqual(records[0]["after"], [])
        self.assertEqual(records[1]["after"], [1])
        self.assertEqual(records[2]["after"], [2])
        self.assertEqual([r["label"] for r in records], ["1.1", "1.2", "1.3"])
        self.assertEqual({r["mode"] for r in records}, {"sync"})
        self.assertEqual({r["chain_len"] for r in records}, {3})
        self.assertEqual(self.start.call_count, 1)  # only the first group launches now
        self.spawn.assert_called_once()

    def test_waiting_record_shape(self):
        groups = [
            {"name": "first", "title": "First", "prompt": "do first"},
            {"name": "second", "title": "Second", "prompt": "do second", "after": ["first"]},
        ]
        self.run_main(groups)
        waiting = read_records(self.state_file)[1]
        self.assertEqual(waiting["id"], "wait-" + waiting["group"] + "-2")
        self.assertEqual(waiting["state"], "waiting")
        for key in ("name", "title", "cwd", "prompt_head", "started", "parent", "group", "index",
                    "total", "parent_transcript", "parent_cwd", "after",
                    "chain", "step", "chain_len", "label", "mode"):
            self.assertIn(key, waiting)
        self.assertEqual(waiting["name"], "split-second")
        self.assertEqual(waiting["title"], "Second")
        self.assertEqual(waiting["total"], 2)

    def test_independent_groups_and_chain_are_contiguous(self):
        groups = [
            {"name": "solo1", "prompt": "s1"},
            {"name": "c1", "prompt": "c1"},
            {"name": "solo2", "prompt": "s2"},
            {"name": "c2", "prompt": "c2", "after": ["c1"]},
            {"name": "c3", "prompt": "c3", "after": ["c2"]},
        ]
        self.assertEqual(self.run_main(groups), 0)
        records = read_records(self.state_file)
        self.assertEqual([r["index"] for r in records], [1, 2, 3, 4, 5])
        self.assertEqual([r["name"] for r in records],
                         ["split-solo1", "split-c1", "split-c2", "split-c3", "split-solo2"])
        self.assertEqual([r["label"] for r in records], ["1", "2.1", "2.2", "2.3", "3"])
        self.assertEqual([r["mode"] for r in records], ["async", "sync", "sync", "sync", "async"])
        self.assertEqual([r["chain_len"] for r in records], [1, 3, 3, 3, 1])
        self.assertEqual([r["chain"] for r in records], [1, 2, 2, 2, 3])
        self.assertEqual([r["step"] for r in records], [1, 1, 2, 3, 1])
        self.assertEqual(records[2]["after"], [2])
        self.assertEqual(records[3]["after"], [3])
        self.assertEqual(self.start.call_count, 3)  # solo1, c1 and solo2 launch now

    def test_diamond_linearizes_chain(self):
        groups = [
            {"name": "a", "prompt": "a"},
            {"name": "b", "prompt": "b", "after": ["a"]},
            {"name": "c", "prompt": "c", "after": ["a"]},
            {"name": "d", "prompt": "d", "after": ["b", "c"]},
        ]
        items = dispatch.plan_items(groups)
        self.assertEqual([i["after"] for i in items], [[], [1], [1, 2], [2, 3]])
        self.assertEqual([i["label"] for i in items], ["1.1", "1.2", "1.3", "1.4"])

    def test_table_shows_marks_and_legend(self):
        groups = [
            {"name": "solo", "prompt": "s"},
            {"name": "first", "prompt": "f"},
            {"name": "second", "prompt": "g", "after": ["first"]},
        ]
        argv = ["dispatch.py", plan_file(self.tmp, groups)]
        out = io.StringIO()
        with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(out):
            self.assertEqual(dispatch.main(), 0)
        text = out.getvalue()
        rows = [line for line in text.splitlines() if line.startswith(dispatch.PENDING_MARK)]
        self.assertEqual(len(rows), 3)
        self.assertTrue(rows[0].startswith("○ 1 "))
        self.assertTrue(rows[1].startswith("○ 2.1 "))
        self.assertTrue(rows[2].startswith("○ 2.2 "))
        self.assertIn("aguardando", rows[2])
        self.assertIn(dispatch.LEGEND, text)
        self.assertNotIn("⇉", text)
        self.assertNotIn("→", text)

    def test_waiter_record_carries_chain_fields(self):
        groups = [
            {"name": "first", "prompt": "f"},
            {"name": "second", "prompt": "s", "after": ["first"]},
        ]
        items = dispatch.plan_items(groups)
        common = {"cwd": self.tmp, "parent": None, "group": "g1", "total": 2,
                  "parent_transcript": "", "parent_cwd": self.tmp}
        state = {"common": common, "permission_mode": None, "view": "none", "launched": {}}
        dispatch.launch_waiting(state, items[1])
        rec = read_records(self.state_file)[-1]
        self.assertEqual(rec["label"], "1.2")
        self.assertEqual((rec["chain"], rec["step"], rec["chain_len"]), (1, 2, 2))
        self.assertEqual(rec["mode"], "sync")
        self.assertEqual(rec["after"], [1])

    def test_unknown_name_exits_2_without_records(self):
        groups = [{"name": "a", "prompt": "x", "after": ["ghost"]}]
        with self.assertRaises(SystemExit) as ctx:
            self.run_main(groups)
        self.assertEqual(ctx.exception.code, 2)
        self.assertEqual(read_records(self.state_file), [])
        self.start.assert_not_called()

    def test_cycle_exits_2_without_records(self):
        groups = [
            {"name": "a", "prompt": "x", "after": ["b"]},
            {"name": "b", "prompt": "y", "after": ["a"]},
        ]
        with self.assertRaises(SystemExit) as ctx:
            self.run_main(groups)
        self.assertEqual(ctx.exception.code, 2)
        self.assertEqual(read_records(self.state_file), [])
        self.start.assert_not_called()

    def test_item_ended_rule(self):
        now = 1000.0
        self.assertFalse(dispatch.item_ended({"status": "busy"}, now - 500, now))
        self.assertFalse(dispatch.item_ended({"state": "working"}, now - 500, now))
        self.assertTrue(dispatch.item_ended({"status": "idle"}, now - 500, now))
        self.assertFalse(dispatch.item_ended(None, now - 60, now))
        self.assertTrue(dispatch.item_ended(None, now - 91, now))

    def test_waiter_launches_when_dependency_ends(self):
        state = {
            "common": {"cwd": self.tmp, "parent": None, "group": "g1", "total": 2,
                       "parent_transcript": "", "parent_cwd": self.tmp},
            "permission_mode": None,
            "view": "none",
            "deadline": time.time() + 3600,
            "launched": {"1": {"id": "dep-1", "started": time.time() - 500}},
            "pending": [{"index": 2, "after": [1], "group": {"name": "second", "prompt": "p2"},
                         "chain": 1, "step": 2, "chain_len": 2, "label": "1.2", "mode": "sync"}],
        }
        state_path = os.path.join(self.tmp, "wait.json")
        with open(state_path, "w", encoding="utf-8") as fh:
            json.dump(state, fh)
        agents = {"dep-1": {"id": "dep-1", "status": "idle"}}
        with mock.patch.object(dispatch, "load_live_agents", return_value=agents), \
                mock.patch.object(dispatch.time, "sleep"), \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(dispatch.wait_main(state_path), 0)
        self.assertEqual(self.start.call_count, 1)
        launched = read_records(self.state_file)
        self.assertEqual(len(launched), 1)
        self.assertEqual(launched[0]["id"], "sid-1")
        self.assertEqual(launched[0]["index"], 2)
        self.assertEqual(launched[0]["after"], [1])
        self.assertNotIn("state", launched[0])


class StatusTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.state_file = os.path.join(self.tmp, "prompt-splitter.jsonl")
        mock.patch.object(status, "STATE_FILE", self.state_file).start()
        mock.patch.object(status, "load_agents", return_value={}).start()
        mock.patch.object(status, "parent_title", return_value="Sessao teste").start()
        self.addCleanup(mock.patch.stopall)

    def write(self, records):
        with open(self.state_file, "w", encoding="utf-8") as fh:
            for rec in records:
                fh.write(json.dumps(rec) + "\n")

    def test_dedupe_order_and_no_item_counter(self):
        base = {"group": "g", "parent": None, "cwd": self.tmp, "parent_cwd": self.tmp, "total": 2}
        self.write([
            {**base, "id": "wait-g-2", "state": "waiting", "index": 2, "name": "split-two",
             "title": "Two", "after": [1]},
            {**base, "id": "sid-1", "index": 1, "name": "split-one", "title": "One", "after": []},
            {**base, "id": "sid-2", "index": 2, "name": "split-two", "title": "Two", "after": [1]},
        ])
        records = status.load_records(os.path.realpath(self.tmp))
        self.assertEqual(len(records), 2)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            for group_id, recs in status.group_records(records):
                status.print_group(group_id, recs, {})
        text = out.getvalue()
        self.assertLess(text.index("One"), text.index("Two"))
        self.assertIn("sid-2", text)
        self.assertNotIn("wait-g-2", text)
        self.assertIsNone(re.search(r"\d+ de \d+", text))
        self.assertNotIn("Item ", text)

    def test_waiting_shows_dependency_titles(self):
        base = {"group": "g", "parent": None, "cwd": self.tmp, "parent_cwd": self.tmp, "total": 2}
        self.write([
            {**base, "id": "sid-1", "index": 1, "name": "split-one", "title": "One", "after": []},
            {**base, "id": "wait-g-2", "state": "waiting", "index": 2, "name": "split-two",
             "title": "Two", "after": [1]},
        ])
        records = status.load_records(None)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            for group_id, recs in status.group_records(records):
                status.print_group(group_id, recs, {})
        self.assertIn("aguardando One", out.getvalue())

    def test_cwd_filter_and_var_home_alias(self):
        base = {"group": "g", "parent": None, "total": 1, "index": 1, "after": []}
        inside = os.path.join(self.tmp, "proj")
        os.makedirs(inside)
        self.write([
            {**base, "id": "in", "name": "split-a", "cwd": inside, "parent_cwd": inside},
            {**base, "group": "h", "id": "out", "name": "split-b", "cwd": "/elsewhere/x", "parent_cwd": "/elsewhere"},
        ])
        found = [r["id"] for r in status.load_records(status.normalize_path(self.tmp))]
        self.assertEqual(found, ["in"])
        self.assertEqual(len(status.load_records(None)), 2)
        self.assertEqual(status.normalize_path("/var/home/Orgo/x"), "/home/Orgo/x")
        self.assertEqual(status.normalize_path("/home/Orgo/x"), "/home/Orgo/x")


class StatusStateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cwd = os.path.join(self.tmp, "proj")
        os.makedirs(self.cwd)
        self.rec = {"id": "child-1", "cwd": self.cwd, "name": "split-x", "index": 1, "label": "2.1"}
        self.transcript = os.path.join(self.tmp, "child-1.jsonl")
        patcher = mock.patch.object(status, "child_transcript", return_value=self.transcript)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write_transcript(self, lines):
        with open(self.transcript, "w", encoding="utf-8") as fh:
            for line in lines:
                fh.write(json.dumps(line) + "\n")

    def test_missing_agent_is_encerrada_and_complete(self):
        self.assertEqual(status.item_state(self.rec, {}), ("encerrada", True))

    def test_busy_agent_is_rodando_and_pending(self):
        agents = {"child-1": {"id": "child-1", "status": "busy", "state": "working"}}
        self.assertEqual(status.item_state(self.rec, agents), ("rodando", False))

    def test_failed_agent_is_falhou_and_pending(self):
        agents = {"child-1": {"id": "child-1", "status": "idle", "state": "failed"}}
        self.assertEqual(status.item_state(self.rec, agents), ("falhou", False))

    def test_done_agent_is_complete(self):
        agents = {"child-1": {"id": "child-1", "status": "idle", "state": "done"}}
        self.assertEqual(status.item_state(self.rec, agents), ("concluida", True))

    def test_blocked_agent_without_question_waits_for_user_and_is_complete(self):
        self.write_transcript([{"type": "assistant", "message": {"content": [{"type": "text", "text": "ok"}]}}])
        agents = {"child-1": {"id": "child-1", "status": "idle", "state": "blocked"}}
        self.assertEqual(status.item_state(self.rec, agents), ("concluida, aguarda voce", True))

    def test_ask_user_question_is_aguarda_sua_resposta(self):
        self.write_transcript([
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "t1", "name": "AskUserQuestion", "input": {}}]}},
        ])
        agents = {"child-1": {"id": "child-1", "status": "idle", "state": "blocked"}}
        self.assertEqual(status.item_state(self.rec, agents), ("aguarda sua resposta", False))

    def test_unanswered_tool_use_is_aguarda_sua_resposta(self):
        self.write_transcript([
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "t2", "name": "Bash", "input": {}}]}},
        ])
        agents = {"child-1": {"id": "child-1", "status": "idle", "state": "blocked"}}
        self.assertEqual(status.item_state(self.rec, agents), ("aguarda sua resposta", False))

    def test_answered_tool_use_is_not_a_question(self):
        self.write_transcript([
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "t3", "name": "Bash", "input": {}}]}},
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "t3", "content": "ok"}]}},
        ])
        self.assertFalse(status.awaits_answer(self.transcript))

    def test_missing_transcript_is_not_a_question(self):
        self.assertFalse(status.awaits_answer(os.path.join(self.tmp, "nope.jsonl")))

    def test_print_group_shows_marks_and_legacy_fallback(self):
        recs = [
            {"id": "child-1", "cwd": self.cwd, "name": "split-a", "index": 1, "label": "1",
             "group": "g1", "parent": None, "title": "A"},
            {"id": "child-2", "cwd": self.cwd, "name": "split-b", "index": 2, "label": "2.1",
             "group": "g1", "parent": None, "title": "B"},
            {"id": "child-3", "cwd": self.cwd, "name": "split-c", "index": 3,
             "group": "g1", "parent": None, "title": "C"},
        ]
        agents = {
            "child-1": {"id": "child-1", "status": "idle", "state": "done"},
            "child-2": {"id": "child-2", "status": "busy", "state": "working"},
        }
        out = io.StringIO()
        with mock.patch.object(status, "parent_title", return_value="T"), \
                contextlib.redirect_stdout(out):
            status.print_group("g1", recs, agents)
        lines = out.getvalue().splitlines()
        self.assertIn(f"{status.DONE_MARK} 1  A  concluida  child-1", lines[2])
        self.assertIn(f"{status.PENDING_MARK} 2.1  B  rodando  child-2", lines[3])
        self.assertIn(f"{status.DONE_MARK} 3  C  encerrada  child-3", lines[4])
        self.assertEqual(status.LEGEND, "✓ completo   ○ em andamento ou aguardando")


if __name__ == "__main__":
    unittest.main()
