"""Tests for the office data layer and the demo source."""
import json
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from office import data  # noqa: E402
from office.demo import DemoSource  # noqa: E402

NOW = time.time() * 1000.0


def entry(kind, *blocks):
    content = [dict(b) for b in blocks]
    return json.dumps({"type": kind, "message": {"content": content}})


def tool(name):
    return {"type": "tool_use", "name": name, "id": "x"}


def text(value):
    return {"type": "text", "text": value}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "child.jsonl")

    def write(self, *lines):
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")

    def build(self, rec, agent=None, awaits=False):
        agents = {rec["id"]: agent} if agent is not None else {}
        with mock.patch.object(data.status, "child_transcript", return_value=self.path), \
                mock.patch.object(data.status, "awaits_answer", return_value=awaits):
            workers = data.build_workers([rec], agents, NOW)
        self.assertEqual(len(workers), 1)
        return workers[0]


def rec(**extra):
    base = {"id": "a1", "name": "split-tarefa", "cwd": "/tmp", "group": "g1",
            "started": NOW - 1000, "state": "running"}
    base.update(extra)
    return base


class StateMapping(Base):
    def test_waiting_record_wins(self):
        w = self.build(rec(state="waiting"), {"status": "busy"})
        self.assertEqual(w.state, "waiting")

    def test_busy_agent_ending_in_bash_is_working_term(self):
        self.write(entry("assistant", tool("Bash")))
        w = self.build(rec(), {"status": "busy", "state": "working"})
        self.assertEqual((w.state, w.activity), ("working", "term"))

    def test_tool_kinds(self):
        cases = {"Read": "doc", "Grep": "doc", "Glob": "doc", "Edit": "code", "Write": "code",
                 "NotebookEdit": "code", "WebSearch": "web", "WebFetch": "web", "Agent": "delegate",
                 "Unknown": "code"}
        for name, kind in cases.items():
            self.write(entry("assistant", tool(name)))
            w = self.build(rec(), {"state": "working"})
            self.assertEqual((w.state, w.activity), ("working", kind), name)

    def test_running_without_transcript_is_thinking(self):
        w = self.build(rec(), {"state": "working"})
        self.assertEqual((w.state, w.activity), ("thinking", "none"))

    def test_running_with_text_ending_is_thinking(self):
        self.write(entry("assistant", text("Pensando")))
        w = self.build(rec(), {"status": "busy"})
        self.assertEqual((w.state, w.activity), ("thinking", "none"))

    def test_missing_agent_recent_start_is_running(self):
        w = self.build(rec(started=NOW - 10_000))
        self.assertEqual(w.state, "thinking")

    def test_missing_agent_old_start_is_done(self):
        w = self.build(rec(started=NOW - 200_000))
        self.assertEqual(w.state, "done")

    def test_failed_agent(self):
        self.assertEqual(self.build(rec(), {"state": "failed"}).state, "failed")

    def test_idle_agent_awaiting_answer_is_ask(self):
        self.assertEqual(self.build(rec(), {"state": "blocked"}, awaits=True).state, "ask")

    def test_idle_agent_not_done_is_blocked(self):
        self.assertEqual(self.build(rec(), {"state": "blocked"}).state, "blocked")

    def test_idle_agent_done(self):
        self.assertEqual(self.build(rec(), {"state": "done"}).state, "done")

    def test_subagents_counted_while_running(self):
        sub = os.path.join(self.tmp.name, "child", "subagents")
        os.makedirs(sub)
        self.write(entry("assistant", text("oi")))
        for name, body in {"a.meta.json": {"finished": False}, "b.meta.json": {"finished": True},
                           "c.meta.json": {}}.items():
            with open(os.path.join(sub, name), "w", encoding="utf-8") as handle:
                json.dump(body, handle)
        w = self.build(rec(), {"status": "busy"})
        self.assertEqual(w.subagents, 2)


class Titles(Base):
    def test_explicit_title(self):
        self.assertEqual(data.worker_title({"title": "  Oi  ", "name": "split-x"}), "Oi")

    def test_prompt_head_clipped(self):
        head = "a" * 70
        self.assertEqual(data.worker_title({"prompt_head": head}), "a" * 60 + "...")

    def test_name_fallback(self):
        self.assertEqual(data.worker_title({"name": "split-tarefa"}), "tarefa")


class Timestamps(unittest.TestCase):
    def test_number_and_iso(self):
        self.assertEqual(data.to_ms(123.0), 123.0)
        self.assertEqual(data.to_ms("1970-01-01T00:00:01Z"), 1000.0)
        self.assertEqual(data.to_ms("nao e data"), 0.0)


class LinesAndLabels(Base):
    def test_collapse_repeated_tools(self):
        self.write(entry("assistant", tool("Bash")), entry("assistant", tool("Bash")),
                   entry("assistant", tool("Bash")))
        lines = data.transcript_lines(open(self.path, encoding="utf-8").read())
        self.assertEqual(len(lines), 1)
        self.assertEqual((lines[0].role, lines[0].text, lines[0].count),
                         ("tool", "Utilizando ferramentas do terminal", 3))

    def test_pt_br_labels_and_roles(self):
        self.write(entry("user", text("oi")), entry("assistant", tool("Read")),
                   entry("assistant", tool("Zebra")))
        lines = data.transcript_lines(open(self.path, encoding="utf-8").read())
        self.assertEqual([(l.role, l.text) for l in lines], [
            ("voce", "oi"), ("tool", "Lendo arquivos"), ("tool", "Utilizando Zebra")])

    def test_clip_300(self):
        self.write(entry("user", text("x" * 500)))
        lines = data.transcript_lines(open(self.path, encoding="utf-8").read())
        self.assertEqual(len(lines[0].text), 300)

    def test_tail_only_last_tail_lines(self):
        self.write(*[entry("user", text(f"m{i}")) for i in range(40)])
        lines = data.transcript_lines(open(self.path, encoding="utf-8").read())
        self.assertEqual(len(lines), data.TAIL)
        self.assertEqual(lines[-1].text, "m39")

    def test_big_file_drops_cut_first_line(self):
        filler = entry("user", text("y" * 1000))
        last = entry("user", text("ultima"))
        self.write(*([filler] * 400), last)  # well over 256 KB
        tail = data.read_tail(self.path)
        self.assertTrue(tail.startswith("{"))
        self.assertIn("ultima", tail)

    def test_read_lines_cache_and_missing(self):
        self.assertEqual(data.default_read_lines(os.path.join(self.tmp.name, "nada.jsonl")), [])
        self.write(entry("user", text("um")))
        self.assertEqual(data.default_read_lines(self.path)[0].text, "um")


class Ordering(unittest.TestCase):
    def worker(self, group, index, state, started):
        return data.Worker(id=f"{group}{index}", session_id="s", name="n", title="t", item_label=str(index),
                           group=group, index=index, cwd="", started_ms=started, state=state)

    def test_newest_group_first_and_index_order(self):
        items = [self.worker("old", 2, "done", 100), self.worker("old", 1, "done", 100),
                 self.worker("live", 2, "working", 50), self.worker("live", 1, "done", 50)]
        names = [w.id for w in data.order_workers(items)]
        self.assertEqual(names, ["old1", "old2", "live1", "live2"])

    def test_only_ten_recent_groups(self):
        items = [self.worker(f"g{i}", 1, "done", 1000 + i) for i in range(12)]
        out = data.order_workers(items)
        self.assertEqual(len(out), 10)
        self.assertNotIn("g0", {w.group for w in out})

    def test_newest_group_first_within_rank(self):
        items = [self.worker("a", 1, "done", 1), self.worker("b", 1, "done", 9)]
        self.assertEqual([w.group for w in data.order_workers(items)], ["b", "a"])


class DemoTests(unittest.TestCase):
    def test_demo_covers_all_states(self):
        workers = DemoSource().snapshot()
        self.assertEqual(len(workers), 11)
        states = {w.state for w in workers}
        self.assertEqual(states, {"working", "thinking", "waiting", "ask", "blocked", "done", "failed"})
        self.assertEqual({w.activity for w in workers if w.state == "working"}, {"code", "doc", "delegate"})

    def test_demo_groups_and_chain(self):
        workers = DemoSource().snapshot()
        first = [w for w in workers if w.group == "demo"]
        self.assertEqual(len(first), 7)
        by_index = {w.index: w for w in first}
        self.assertEqual(by_index[5].after, [1])
        self.assertEqual(by_index[6].after, [5])
        self.assertEqual(by_index[3].subagents, 2)
        self.assertEqual(by_index[1].item_label, "1")

    def test_start_is_noop(self):
        DemoSource().start()


class PollerTests(unittest.TestCase):
    def test_snapshot_is_list_and_never_raises(self):
        poller = data.Poller(read_lines=lambda path: [])
        self.assertIsInstance(poller.snapshot(), list)

    def test_agents_failure_keeps_none(self):
        with mock.patch.object(data.subprocess, "run", side_effect=OSError("sem claude")):
            self.assertIsNone(data.load_agents_once())


class SessionIdentity(unittest.TestCase):
    def transcript(self, home: str, project: str, name: str) -> None:
        folder = os.path.join(home, ".claude", "projects", project)
        os.makedirs(folder, exist_ok=True)
        open(os.path.join(folder, name + ".jsonl"), "w").close()

    def test_full_session_id_from_a_short_id(self):
        with tempfile.TemporaryDirectory() as home, mock.patch.dict(os.environ, {"HOME": home}):
            self.transcript(home, "-some-project", "3190a3b3-637f")
            self.assertEqual(data.full_session_id("3190a3b3"), "3190a3b3-637f")
            self.assertEqual(data.full_session_id("3190a3b3-637f"), "3190a3b3-637f")

    def test_unknown_empty_or_ambiguous_id_gives_nothing(self):
        with tempfile.TemporaryDirectory() as home, mock.patch.dict(os.environ, {"HOME": home}):
            self.transcript(home, "-a", "aa11-one")
            self.transcript(home, "-a", "aa11-two")
            self.assertEqual(data.full_session_id("aa11"), "")
            self.assertEqual(data.full_session_id("bb22"), "")
            self.assertEqual(data.full_session_id(""), "")

    def test_only_sessions_in_the_registry_are_attachable(self):
        records = [{"id": "known", "cwd": "/tmp", "started": 1.0}, {"id": "gone", "cwd": "/tmp", "started": 1.0}]
        agents = {"known": {"id": "known", "sessionId": "known-full", "state": "done"}}
        workers = {w.id: w for w in data.build_workers(records, agents, time.time() * 1000.0, lambda _path: [])}
        self.assertTrue(workers["known"].attachable)
        self.assertFalse(workers["gone"].attachable)


class SessionOpening(Base):
    def test_only_sessions_in_the_registry_are_attachable(self):
        self.assertTrue(self.build(rec(), {"state": "done", "sessionId": "full"}).attachable)
        self.assertFalse(self.build(rec(started=NOW - 10_000_000)).attachable)

    def transcript(self, name):
        folder = os.path.join(self.tmp.name, ".claude", "projects", "slug")
        os.makedirs(folder, exist_ok=True)
        open(os.path.join(folder, name + ".jsonl"), "w", encoding="utf-8").close()

    def test_full_session_id_comes_from_the_transcript(self):
        self.transcript("abc12345-0000-4000-8000-000000000001")
        with mock.patch.dict(os.environ, {"HOME": self.tmp.name}):
            self.assertEqual(data.full_session_id("abc12345"), "abc12345-0000-4000-8000-000000000001")
            self.assertEqual(data.full_session_id("abc12345-0000-4000-8000-000000000001"),
                             "abc12345-0000-4000-8000-000000000001")

    def test_full_session_id_is_empty_when_unknown_or_ambiguous(self):
        self.transcript("abc12345-1")
        self.transcript("abc12345-2")
        with mock.patch.dict(os.environ, {"HOME": self.tmp.name}):
            self.assertEqual(data.full_session_id(""), "")
            self.assertEqual(data.full_session_id("ffffffff"), "")
            self.assertEqual(data.full_session_id("abc12345"), "")


class RoomTitleTests(unittest.TestCase):
    def record(self, parent=""):
        rec = {"id": "r1", "name": "split-a", "group": "g", "label": "1", "index": 1, "started": 1000}
        if parent:
            rec["parent"] = parent
            rec["parent_transcript"] = "/tmp/parent.jsonl"
        return rec

    def setUp(self):
        data._room_titles.clear()

    def test_room_title_comes_from_parent_title(self):
        with mock.patch("status.parent_title", return_value="Sessao pai") as title:
            workers = data.build_workers([self.record("abc123")], {}, NOW, read_lines=lambda p: [])
        self.assertEqual(workers[0].room_title, "Sessao pai")
        title.assert_called_once_with("abc123", "/tmp/parent.jsonl")

    def test_second_call_within_period_reuses_cached_title(self):
        with mock.patch("status.parent_title", return_value="Sessao pai") as title:
            data.build_workers([self.record("abc123")], {}, NOW, read_lines=lambda p: [])
            data.build_workers([self.record("abc123")], {}, NOW, read_lines=lambda p: [])
        self.assertEqual(title.call_count, 1)

    def test_empty_parent_gives_empty_title_without_call(self):
        with mock.patch("status.parent_title", return_value="x") as title:
            workers = data.build_workers([self.record()], {}, NOW, read_lines=lambda p: [])
        self.assertEqual(workers[0].room_title, "")
        title.assert_not_called()


if __name__ == "__main__":
    unittest.main()
