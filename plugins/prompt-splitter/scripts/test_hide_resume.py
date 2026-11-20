"""Hidden split sessions: the tail scan, the target choice and the marker write."""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hide_resume  # noqa: E402


def assistant(stop: str = "end_turn") -> str:
    return json.dumps({"type": "assistant", "message": {"stop_reason": stop, "content": []}})


def user_text() -> str:
    return json.dumps({"type": "user", "message": {"content": [{"type": "text", "text": "oi"}]}})


def user_tool_result() -> str:
    return json.dumps({"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "t1", "content": "ok"}
    ]}})


def user_meta() -> str:
    return json.dumps({"type": "user", "isMeta": True, "message": {"content": "meta"}})


def marker(target: str) -> str:
    return json.dumps({"type": "continued-in", "sessionId": "s", "continuedInSessionId": target}, separators=(",", ":"))


def tail(*lines: str) -> str:
    return "\n".join(lines) + "\n"


class NeedsMarkerTests(unittest.TestCase):
    def test_spaced_marker_does_not_count(self):
        spaced = json.dumps({"type": "continued-in", "sessionId": "s", "continuedInSessionId": "t"})
        self.assertTrue(hide_resume.needs_marker(tail(user_text(), spaced), "t"))

    def test_marker_at_the_tail_hides_already(self):
        self.assertFalse(hide_resume.needs_marker(tail(user_text(), marker("p")), "p"))

    def test_assistant_after_marker_makes_it_stale(self):
        self.assertTrue(hide_resume.needs_marker(tail(marker("p"), assistant()), "p"))

    def test_human_prompt_after_marker_makes_it_stale(self):
        self.assertTrue(hide_resume.needs_marker(tail(marker("p"), user_text()), "p"))

    def test_tool_results_after_marker_do_not_count(self):
        self.assertFalse(hide_resume.needs_marker(tail(marker("p"), user_tool_result()), "p"))

    def test_meta_user_lines_do_not_count(self):
        self.assertFalse(hide_resume.needs_marker(tail(marker("p"), user_meta()), "p"))

    def test_marker_for_another_target_needs_ours(self):
        self.assertTrue(hide_resume.needs_marker(tail(marker("other")), "p"))

    def test_unparseable_lines_are_ignored(self):
        self.assertFalse(hide_resume.needs_marker(tail(marker("p"), "{broken"), "p"))


class TargetTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(self.dir, ignore_errors=True))

    def test_parent_transcript_present_is_the_target(self):
        parent = "11111111-2222-3333-4444-555555555555"
        open(os.path.join(self.dir, parent + ".jsonl"), "w").close()
        child = os.path.join(self.dir, "child.jsonl")
        self.assertEqual(hide_resume.target_for(child, "child", parent), parent)

    def test_missing_parent_falls_back_to_the_session(self):
        child = os.path.join(self.dir, "child.jsonl")
        self.assertEqual(hide_resume.target_for(child, "child", "absent"), "child")
        self.assertEqual(hide_resume.target_for(child, "child", ""), "child")


class HideTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(self.dir, ignore_errors=True))
        self.path = os.path.join(self.dir, "sid.jsonl")

    def write(self, text: str) -> None:
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write(text)

    def test_keeps_the_modification_time(self):
        self.write(user_text() + "\n" + json.dumps({"parentUuid": "u", "type": "user"}) + "\n")
        os.utime(self.path, (1_000_000, 1_000_000))
        self.assertTrue(hide_resume.hide(self.path, "sid", ""))
        self.assertEqual(int(os.stat(self.path).st_mtime), 1_000_000)

    def test_appends_one_marker_only_once(self):
        self.write(user_text() + "\n" + json.dumps({"parentUuid": "u", "type": "user"}) + "\n")
        self.assertTrue(hide_resume.hide(self.path, "sid", ""))
        with open(self.path, encoding="utf-8") as fh:
            lines = [line for line in fh.read().splitlines() if line.strip()]
        record = json.loads(lines[-1])
        self.assertEqual(record["type"], "continued-in")
        self.assertIn('"type":"continued-in"', lines[-1])
        self.assertEqual(record["sessionId"], "sid")
        self.assertEqual(record["continuedInSessionId"], "sid")
        self.assertFalse(hide_resume.hide(self.path, "sid", ""))
        with open(self.path, encoding="utf-8") as fh:
            self.assertEqual(len([line for line in fh.read().splitlines() if line.strip()]), len(lines))

    def test_missing_transcript_returns_false(self):
        self.assertFalse(hide_resume.hide(os.path.join(self.dir, "nope.jsonl"), "sid", ""))

    def test_transcript_without_parent_uuid_returns_false(self):
        self.write(user_text() + "\n")
        self.assertFalse(hide_resume.hide(self.path, "sid", ""))

    def test_parent_target_is_used_and_missing_newline_is_prefixed(self):
        parent = "abcdef12-0000-0000-0000-000000000000"
        open(os.path.join(self.dir, parent + ".jsonl"), "w").close()
        self.write(user_text() + "\n" + json.dumps({"parentUuid": "u"}))
        self.assertTrue(hide_resume.hide(self.path, "sid", parent))
        with open(self.path, encoding="utf-8") as fh:
            lines = [line for line in fh.read().splitlines() if line.strip()]
        self.assertEqual(json.loads(lines[-1])["continuedInSessionId"], parent)


if __name__ == "__main__":
    unittest.main()
