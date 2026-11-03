import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import detect  # noqa: E402
import store  # noqa: E402

CORRECTIONS = [
    "Testando ainda não foi alterado",
    "Você não marcou os itens do 14 que foram feitos como pedi",
    "Sobre o item 1, você alucinou. Pedi para que ela acompanhasse a hora",
    "Item 28 das correções 15 não foi feito",
    "O fundo não era para ser estrelado e nem escuro",
    "Continua ruim... o fogo melhorou",
    "Esqueceu de alguns teas e juices",
    "Só faltou aplicar a visão para quando está em horizontal",
    "Quando volto ao menu desencadeia de novo sua animação, não deveria",
]
NOT_CORRECTIONS = [
    "Adicione um novo botão de exportar na tela de relatórios",
    "Perdão, falei errado... a mudança está correta",
    "Sobre o item 2, escrevi errado, era o título",
    "/bom-senso:estado off",
    "Resultados do split: ainda não testado",
    "The prompt-splitter plugin sent a message: Resultados: ainda não testado",
    "Pedido original do usuario: deveria ter um botão",
    "",
]


def run_hook(event, payload, state, **env):
    return subprocess.run(
        [sys.executable, str(ROOT / "hooks/hook.py"), event], input=json.dumps(payload),
        capture_output=True, text=True, env=dict(os.environ, BOM_SENSO_STATE=state, **env))


def context(result):
    return json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]


class DetectTest(unittest.TestCase):
    def test_corrections_are_flagged(self):
        for prompt in CORRECTIONS:
            self.assertTrue(detect.correction_signal(prompt), prompt)

    def test_other_prompts_are_not(self):
        for prompt in NOT_CORRECTIONS:
            self.assertIsNone(detect.correction_signal(prompt), prompt)

    def test_related_needs_three_keywords(self):
        example = {"keywords": ["blueprints", "modpack", "construcoes"], "rule": "r"}
        self.assertEqual(detect.related_examples("os blueprints do modpack", [example]), [])
        self.assertEqual(detect.related_examples("Construções e blueprints do modpack", [example]), [example])


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        os.environ["BOM_SENSO_STATE"] = self.tmp.name
        self.addCleanup(os.environ.pop, "BOM_SENSO_STATE")

    def test_add_bump_remove(self):
        entry = store.add("consistencia", "s", "e", "r")
        store.bump(entry["id"])
        self.assertEqual(store.user_examples()[0]["count"], 2)
        store.remove(entry["id"])
        self.assertEqual(store.user_examples(), [])

    def test_unknown_id_and_category_fail(self):
        with self.assertRaises(KeyError):
            store.remove("nope")
        with self.assertRaises(ValueError):
            store.add("nope", "s", "e", "r")

    def test_project_rules_stay_in_their_project_and_come_first(self):
        store.add("consistencia", "s", "e", "global")
        store.add("consistencia", "s", "e", "here", project="/a")
        store.add("consistencia", "s", "e", "there", project="/b")
        self.assertEqual([r["rule"] for r in store.relevant_user_rules("/a", 8)], ["here", "global"])

    def test_cli_switch_and_remove(self):
        store.main(["status", "off"])
        self.assertFalse(store.is_enabled())
        store.main(["status", "on"])
        self.assertTrue(store.is_enabled())
        entry = store.add("consistencia", "s", "e", "r")
        store.main(["list", "--remove", entry["id"]])
        self.assertEqual(store.user_examples(), [])

    def test_seeds_are_valid(self):
        for seed in store.seeds():
            self.assertIn(seed["category"], store.CATEGORIES)
            self.assertTrue(seed["rule"] and seed["keywords"], seed["id"])


class HookTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.payload = {"prompt": "Item 5 não foi feito", "session_id": "abc", "cwd": "/p"}

    def test_correction_asks(self):
        text = context(run_hook("prompt", self.payload, self.tmp.name))
        self.assertIn("AskUserQuestion", text)
        self.assertIn("mute abc", text)

    def test_split_child_is_not_asked(self):
        result = run_hook("prompt", self.payload, self.tmp.name, CLAUDE_SPLIT_CHILD="1")
        self.assertNotIn("AskUserQuestion", result.stdout)

    def test_muted_session_is_not_asked(self):
        subprocess.run([sys.executable, str(ROOT / "scripts/store.py"), "mute", "abc"],
                       env=dict(os.environ, BOM_SENSO_STATE=self.tmp.name), capture_output=True)
        self.assertNotIn("AskUserQuestion", run_hook("prompt", self.payload, self.tmp.name).stdout)

    def test_session_and_subagent_get_their_checklists(self):
        self.assertIn("Before planning", context(run_hook("session", {"cwd": "/p"}, self.tmp.name)))
        self.assertIn("Bom senso:", context(run_hook("subagent", {"cwd": "/p"}, self.tmp.name)))

    def test_disabled_is_silent(self):
        Path(self.tmp.name, "disabled").touch()
        self.assertEqual(run_hook("session", {"cwd": "/p"}, self.tmp.name).stdout, "")

    def test_bad_input_never_fails(self):
        result = subprocess.run([sys.executable, str(ROOT / "hooks/hook.py"), "prompt"], input="{not json",
                                capture_output=True, text=True, env=dict(os.environ, BOM_SENSO_STATE=self.tmp.name))
        self.assertEqual((result.returncode, result.stdout), (0, ""))


if __name__ == "__main__":
    unittest.main()
