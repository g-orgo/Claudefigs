#!/usr/bin/env python3
"""End-to-end tests for publish.py: a temporary clone, a local bare remote and a fake HOME."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
# Joined so that this file does not match the scan it exercises.
FAKE_SECRET = "sk" + "-ant-" + "x" * 30
ENV = {
    **os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0",
    "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.invalid",
}


def git(cwd, *args):
    done = subprocess.run(["git", *args], cwd=cwd, env=ENV, capture_output=True, text=True, check=True)
    return done.stdout.strip()


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class PublishTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.remote = self.root / "remote.git"
        self.clone = self.root / "clone"
        self.home = self.root / "home"
        git(self.root, "init", "-q", "--bare", "-b", "main", str(self.remote))
        git(self.root, "clone", "-q", str(self.remote), str(self.clone))
        git(self.clone, "checkout", "-q", "-B", "main")
        (self.clone / "scripts").mkdir()
        for name in ("sync.py", "publish.py"):
            shutil.copy2(SCRIPTS / name, self.clone / "scripts" / name)
        write(self.clone / ".gitignore", "__pycache__/\n")
        git(self.clone, "add", "-A")
        git(self.clone, "commit", "-q", "-m", "init")
        git(self.clone, "push", "-q", "origin", "main")

        claude = self.home / ".claude"
        write(claude / "CLAUDE.md", "rules\n")
        write(claude / "settings.json", "{}\n")
        write(claude / "statusline.py", "# status\n")
        write(claude / "agents/a.md", "agent\n")
        write(claude / "hooks/h.py", "# hook\n")
        plugins = claude / "local-plugins"
        write(plugins / ".claude-plugin/marketplace.json", json.dumps({"name": "m"}))
        write(plugins / "plugins/demo/.claude-plugin/plugin.json", json.dumps({"name": "demo"}))

    def publish(self):
        return subprocess.run(
            [sys.executable, str(self.clone / "scripts/publish.py")],
            cwd=self.root, env={**ENV, "HOME": str(self.home)}, capture_output=True, text=True,
        )

    def remote_head(self):
        return git(self.remote, "rev-parse", "main")

    def other_clone_pushes(self, relative, text):
        other = self.root / "other"
        git(self.root, "clone", "-q", str(self.remote), str(other))
        write(other / relative, text)
        git(other, "add", "-A")
        git(other, "commit", "-q", "-m", "remote change")
        git(other, "push", "-q", "origin", "main")

    def test_publishes_then_reports_no_change(self):
        first = self.publish()
        self.assertEqual(first.returncode, 0, first.stderr)
        head = self.remote_head()
        self.assertEqual(head, git(self.clone, "rev-parse", "HEAD"))
        self.assertIn(head[:7], first.stdout)
        message = git(self.clone, "log", "-1", "--format=%B")
        self.assertIn("claude/CLAUDE.md", message)
        self.assertTrue(message.endswith("Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"))

        second = self.publish()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("Nada mudou", second.stdout)
        self.assertEqual(self.remote_head(), head)
        self.assertEqual(git(self.clone, "status", "--porcelain"), "")

    def test_scan_aborts_on_secret_in_published_tree(self):
        before = self.remote_head()
        write(self.home / ".claude/hooks/leak.py", f"key = '{FAKE_SECRET}'\n")
        result = self.publish()
        self.assertEqual(result.returncode, 1)
        self.assertIn("leak.py", result.stderr)
        self.assertEqual(self.remote_head(), before)
        self.assertEqual(git(self.clone, "rev-parse", "HEAD"), before)
        self.assertFalse((self.clone / "claude").exists())

    def test_scan_aborts_on_stray_file_in_clone(self):
        before = self.remote_head()
        write(self.clone / "notes.txt", FAKE_SECRET)
        result = self.publish()
        self.assertEqual(result.returncode, 1)
        self.assertIn("notes.txt", result.stderr)
        self.assertEqual(self.remote_head(), before)
        self.assertEqual(git(self.clone, "diff", "--cached", "--name-only"), "")

    def test_rebases_when_remote_is_ahead(self):
        self.other_clone_pushes("remote.txt", "from elsewhere\n")
        result = self.publish()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.clone / "remote.txt").exists())
        self.assertEqual(self.remote_head(), git(self.clone, "rev-parse", "HEAD"))
        self.assertEqual(git(self.clone, "log", "--merges", "--oneline"), "")

    def test_conflict_stops_without_pushing(self):
        self.assertEqual(self.publish().returncode, 0)
        self.other_clone_pushes("claude/CLAUDE.md", "remote rules\n")
        before = self.remote_head()
        write(self.home / ".claude/CLAUDE.md", "local rules\n")
        result = self.publish()
        self.assertEqual(result.returncode, 1)
        self.assertIn("Conflito", result.stderr)
        self.assertIn("claude/CLAUDE.md", result.stderr)
        self.assertEqual(self.remote_head(), before)
        self.assertEqual(git(self.clone, "symbolic-ref", "--short", "HEAD"), "main")


if __name__ == "__main__":
    unittest.main()
