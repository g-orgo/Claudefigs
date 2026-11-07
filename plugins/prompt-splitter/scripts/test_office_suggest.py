"""Composer suggestions: sources, dedupe, ranking, trigger rules and the keys that drive the popup."""

import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

import claude_office
from office import suggest
from office.composer import POPUP_ROWS, Composer
from test_office_composer import SCRATCH, make_office


def write(path: str, text: str = "x\n") -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def write_json(path: str, data: dict) -> None:
    write(path, json.dumps(data))


class SourceTests(unittest.TestCase):
    def setUp(self):
        os.makedirs(SCRATCH, exist_ok=True)
        self.root = tempfile.mkdtemp(dir=SCRATCH)
        self.home = os.path.join(self.root, "home")
        self.cwd = os.path.join(self.root, "project")
        write(os.path.join(self.cwd, ".claude", "commands", "deploy.md"), "# Deploy the project\n")
        write(os.path.join(self.home, ".claude", "commands", "deploy.md"), "# Global deploy\n")
        write(os.path.join(self.home, ".claude", "commands", "sub", "notes.md"), "Write notes\n")
        write(os.path.join(self.home, ".claude", "skills", "review", "SKILL.md"),
              "---\nname: review\ndescription: Reviews the diff\n---\nbody\n")
        write(os.path.join(self.cwd, "src", "app.py"))
        write(os.path.join(self.cwd, "docs", "app_notes.md"))
        write(os.path.join(self.cwd, "node_modules", "junk.js"))
        write(os.path.join(self.cwd, ".hidden", "secret.txt"))
        self.env = mock.patch.dict(os.environ, {"HOME": self.home})
        self.env.start()
        suggest.clear_cache()

    def tearDown(self):
        self.env.stop()
        suggest.clear_cache()
        shutil.rmtree(self.root, ignore_errors=True)

    def test_commands_come_from_all_sources_and_project_wins_on_a_name(self):
        found = dict(suggest.commands(self.cwd))
        self.assertEqual(sorted(found), ["deploy", "review", "sub:notes"])
        self.assertEqual(found["deploy"], "Deploy the project")
        self.assertEqual(found["review"], "Reviews the diff")
        self.assertEqual(found["sub:notes"], "Write notes")

    def test_enabled_plugins_add_commands_and_skills_under_their_name(self):
        plugin = os.path.join(self.root, "cache", "prompt-splitter")
        write(os.path.join(plugin, "commands", "split.md"), "# Split a prompt\n")
        write(os.path.join(plugin, "skills", "guide", "SKILL.md"),
              "---\nname: howto\ndescription: How to use it\n---\nbody\n")
        self.write_plugins({"prompt-splitter@local": True}, {
            "prompt-splitter@local": [{"scope": "user", "installPath": plugin}],
        })
        found = dict(suggest.commands(self.cwd))
        self.assertEqual(found["prompt-splitter:split"], "Split a prompt")
        self.assertEqual(found["prompt-splitter:howto"], "How to use it")
        self.assertNotIn("prompt-splitter:guide", found)

    def test_disabled_plugins_and_missing_installs_are_skipped(self):
        plugin = os.path.join(self.root, "cache", "off")
        write(os.path.join(plugin, "commands", "hidden.md"), "# Hidden\n")
        self.write_plugins({"off@local": False, "gone@local": True}, {
            "off@local": [{"scope": "user", "installPath": plugin}],
            "gone@local": [{"scope": "user", "installPath": os.path.join(self.root, "missing")}],
        })
        found = dict(suggest.commands(self.cwd))
        self.assertFalse([name for name in found if name.startswith(("off:", "gone:"))])

    def test_project_scope_plugin_applies_only_inside_its_project(self):
        plugin = os.path.join(self.root, "cache", "local-tool")
        write(os.path.join(plugin, "commands", "tool.md"), "# Tool\n")
        entry = {"scope": "project", "projectPath": self.cwd, "installPath": plugin}
        self.write_plugins({"local-tool@proj": True}, {"local-tool@proj": [entry]})
        self.assertIn("local-tool:tool", dict(suggest.commands(self.cwd)))
        suggest.clear_cache()
        self.assertNotIn("local-tool:tool", dict(suggest.commands(os.path.join(self.root, "elsewhere"))))

    def write_plugins(self, enabled: dict, installed: dict) -> None:
        write_json(os.path.join(self.home, ".claude", "settings.json"), {"enabledPlugins": enabled})
        write_json(os.path.join(self.home, ".claude", "plugins", "installed_plugins.json"), {"version": 2, "plugins": installed})
        suggest.clear_cache()

    def test_files_skip_hidden_and_dependency_folders_and_rank_names_first(self):
        self.assertEqual(suggest.files(self.cwd, "app"), ["src/app.py", "docs/app_notes.md"])
        self.assertEqual(suggest.files(self.cwd, "junk"), [])
        self.assertEqual(suggest.files(self.cwd, "secret"), [])

    def test_files_limit_and_cache_hold_for_the_window(self):
        suggest.files(self.cwd, "")
        write(os.path.join(self.cwd, "late.txt"))
        self.assertEqual(suggest.files(self.cwd, "late"), [])  # served from the 30 s cache.
        suggest.clear_cache()
        self.assertEqual(suggest.files(self.cwd, "late"), ["late.txt"])
        self.assertLessEqual(len(suggest.files(self.cwd, "", limit=2)), 2)

    def test_matches_rank_prefix_first_and_respect_limit(self):
        all_commands = [("redeploy", ""), ("help", ""), ("deploy", "")]
        self.assertEqual([n for n, _ in suggest.matches(all_commands, "dep")], ["deploy", "redeploy"])
        self.assertEqual(len(suggest.matches(all_commands, "", limit=1)), 1)


class TriggerTests(unittest.TestCase):
    def trig(self, text):
        draft = Composer()
        draft.text = text
        return draft.trigger()

    def test_slash_opens_commands_only_at_the_start_without_a_space(self):
        self.assertEqual(self.trig("/"), ("command", "", 0))
        self.assertEqual(self.trig("/dep"), ("command", "dep", 0))
        self.assertIsNone(self.trig("/dep now"))
        self.assertIsNone(self.trig("olá /dep"))

    def test_at_opens_files_after_a_space_or_at_the_start(self):
        self.assertEqual(self.trig("@"), ("file", "", 0))
        self.assertEqual(self.trig("veja @src/a"), ("file", "src/a", 5))
        self.assertIsNone(self.trig("email@host"))
        self.assertIsNone(self.trig("veja @src/a "))


class PopupKeyTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(dir=SCRATCH)
        self.home = os.path.join(self.root, "home")
        self.cwd = os.path.join(self.root, "project")
        write(os.path.join(self.cwd, ".claude", "commands", "deploy.md"))
        write(os.path.join(self.cwd, ".claude", "commands", "redeploy.md"))
        write(os.path.join(self.cwd, "src", "app.py"))
        self.env = mock.patch.dict(os.environ, {"HOME": self.home})
        self.env.start()
        self.old = os.getcwd()
        os.chdir(self.cwd)
        suggest.clear_cache()
        self.office = make_office(rows=50)
        self.office.render()
        claude_office.handle_key(self.office, "\t")  # focuses the field.

    def tearDown(self):
        os.chdir(self.old)
        self.env.stop()
        suggest.clear_cache()
        shutil.rmtree(self.root, ignore_errors=True)

    def type_text(self, text):
        for ch in text:
            claude_office.handle_key(self.office, ch)

    def test_popup_opens_and_up_down_never_scroll_the_chat(self):
        self.type_text("/dep")
        self.assertEqual([i[0] for i in self.office.popup_items()], ["/deploy", "/redeploy"])
        with mock.patch.object(self.office, "chat") as chat:
            claude_office.handle_key(self.office, "\x1b[B")
            self.assertEqual(self.office.composer.highlight, 1)
            claude_office.handle_key(self.office, "\x1b[A")
            self.assertEqual(self.office.composer.highlight, 0)
            chat.assert_not_called()

    def test_tab_accepts_the_highlighted_suggestion(self):
        self.type_text("/dep")
        claude_office.handle_key(self.office, "\x1b[B")
        claude_office.handle_key(self.office, "\t")
        self.assertEqual(self.office.composer.text, "/redeploy ")
        self.assertEqual(self.office.popup_items(), [])

    def test_enter_accepts_with_popup_and_submits_without(self):
        self.type_text("/dep")
        with mock.patch.object(self.office, "submit") as submit:
            claude_office.handle_key(self.office, "\r")
            submit.assert_not_called()
        self.assertEqual(self.office.composer.text, "/deploy ")
        with mock.patch.object(self.office, "submit") as submit:
            claude_office.handle_key(self.office, "\r")
            submit.assert_called_once()

    def test_file_suggestion_replaces_the_token_with_an_at_path(self):
        self.type_text("veja @app")
        self.assertEqual(self.office.popup_items()[0][1], "@src/app.py ")
        claude_office.handle_key(self.office, "\t")
        self.assertEqual(self.office.composer.text, "veja @src/app.py ")

    def test_esc_closes_popup_then_leaves_the_field(self):
        self.type_text("/dep")
        claude_office.handle_key(self.office, "\x1b")
        self.assertTrue(self.office.composer.focused)
        self.assertEqual(self.office.composer.text, "/dep")
        self.assertEqual(self.office.popup_items(), [])
        self.type_text("x")
        self.assertEqual(len(self.office.popup_items()), 0)  # "/depx" matches nothing.
        claude_office.handle_key(self.office, "\x1b")
        self.assertFalse(self.office.composer.focused)

    def test_click_on_a_row_accepts_that_suggestion(self):
        self.type_text("/dep")
        left, top, _, rows = self.office.popup_rect(len(self.office.popup_items()))
        self.assertLessEqual(rows, POPUP_ROWS)
        claude_office.handle_key(self.office, f"\x1b[<0;{left + 2};{top + 3}M")  # second item: the top border is row 0.
        claude_office.handle_key(self.office, f"\x1b[<0;{left + 2};{top + 3}m")
        self.assertEqual(self.office.composer.text, "/redeploy ")

    def test_no_popup_outside_a_slash_or_at_token(self):
        self.type_text("oi")
        self.assertEqual(self.office.popup_items(), [])


if __name__ == "__main__":
    unittest.main()
