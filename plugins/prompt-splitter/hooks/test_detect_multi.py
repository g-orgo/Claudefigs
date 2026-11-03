"""Tests for the UserPromptSubmit detector, focused on unnumbered requests.

Run with: python3 hooks/test_detect_multi.py  (or python3 -m pytest -q hooks/test_detect_multi.py)
"""

import contextlib
import io
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import detect_multi  # noqa: E402


def run_hook(prompt: str) -> str:
    out = io.StringIO()
    stdin = io.StringIO(json.dumps({"prompt": prompt, "cwd": os.path.dirname(os.path.abspath(__file__))}))
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_SPLIT_CHILD"}
    with mock.patch.object(sys, "stdin", stdin), mock.patch.dict(os.environ, env, clear=True), \
            contextlib.redirect_stdout(out):
        detect_multi.main()
    return out.getvalue()


class UnnumberedPositiveTest(unittest.TestCase):
    def assertCount(self, prompt: str, expected: int):
        self.assertEqual(detect_multi.count_unnumbered(prompt), expected, prompt)

    def test_separate_lines_pt(self):
        self.assertCount("Corrija o header do site no mobile\nAdicione dark mode nas configuracoes", 2)

    def test_connector_e_tambem_on_one_line(self):
        self.assertCount("Muda a cor do botão de login e também atualiza o texto do rodapé", 2)

    def test_alem_disso_and_outra_coisa(self):
        self.assertCount(
            "Refatore o serviço de pagamentos. Além disso, crie um endpoint de reembolso. "
            "Outra coisa: o export de CSV está quebrado.",
            3,
        )

    def test_english_connectors(self):
        self.assertCount(
            "Fix the navbar overflow on mobile. Also, add a loading spinner to the dashboard. "
            "Another thing: the export button does nothing.",
            3,
        )

    def test_dash_bullets_without_lead(self):
        self.assertCount("- corrigir o cache do Redis\n- adicionar paginação na API\n- atualizar o README da raiz", 3)

    def test_bullets_under_collection_lead(self):
        self.assertCount("Faz essas coisas:\n* corrige o login com Google\n* muda o favicon do site", 2)

    def test_desire_phrases_on_lines(self):
        self.assertCount("Quero que o header fique fixo no topo.\nPreciso que o login lembre o usuário.", 2)

    def test_three_sentences_on_one_line(self):
        self.assertCount("Corrija o login. Mude a cor do botão principal. Atualize o README com o deploy.", 3)

    def test_unaccented_input(self):
        self.assertCount("arruma o modal de cadastro e tambem remove o banner antigo da home", 2)

    def test_bare_and_between_two_requests(self):
        self.assertCount("Fix the header and update the footer links", 2)

    def test_two_sentences_one_line(self):
        self.assertCount("Corrija o login. Mude a cor do botão principal.", 2)

    def test_desire_after_topic_and_missing_verbs(self):
        self.assertCount(
            'Remova da navbar: "patinhas"; nos posts eu queria que só os ícones tivessem cor e não o fundo '
            "do botão; também reduz ainda mais a opacidade da vinheta",
            3,
        )

    def test_problem_reports_count_as_requests(self):
        self.assertCount(
            "As notificações devem ficar no menu superior junto do avatar e o botão de sair "
            "não está no padrão do de voltar para o menu",
            2,
        )
        self.assertCount(
            "Parece que as caixinhas não carregam junto do login; queria umas folhas fakes no mesmo esquema",
            2,
        )

    def test_main_prints_unnumbered_hint(self):
        out = run_hook("Fix the login redirect\nUpdate the pricing page copy")
        self.assertIn("2 separate unnumbered requests", out)
        self.assertIn("without asking", out)


class UnnumberedNegativeTest(unittest.TestCase):
    def assertNone(self, prompt: str):
        self.assertEqual(detect_multi.count_unnumbered(prompt), 0, prompt)

    def test_single_long_request_with_context(self):
        self.assertNone(
            "Implemente a tela de perfil do usuário.\nEla deve mostrar avatar, nome e email.\n"
            "Use o componente Card existente e mantenha o estilo atual."
        )

    def test_request_plus_tests_followup(self):
        self.assertNone(
            "Corrija o bug de login que acontece quando o token expira. Quando isso acontece, o usuário "
            "fica preso numa tela branca. Adicione um teste cobrindo esse caso."
        )

    def test_lead_with_detail_bullets(self):
        self.assertNone(
            "Crie a página de perfil:\n- mostre o avatar do usuário\n- mostre o nome completo\n"
            "- adicione um botão de editar"
        )

    def test_verb_pair_on_one_object_is_not_split(self):
        self.assertNone("Investigue e corrija o erro 500 no endpoint de pedidos")

    def test_adverb_tambem_and_constraints(self):
        self.assertNone("Adicione o filtro de datas no relatório; o filtro também deve aceitar intervalos.")
        self.assertNone("Add retry logic to the uploader. Also make sure the old behavior stays the default.")

    def test_reading_verbs_do_not_count(self):
        self.assertNone(
            "Leia o HANDOFF.md e o README antes.\nFaça o hook detectar pedidos não numerados e sugerir o split.\n"
            "Adicione testes para casos positivos e negativos. Código e comentários em inglês."
        )

    def test_code_fence_and_quotes_ignored(self):
        self.assertNone(
            "Corrija este script de deploy:\n```\nadd the user to the group\nremove the old build folder\n"
            "update the symlink target\n```\n> fix the cache first\n> update the docs too"
        )

    def test_main_silent_for_single_request(self):
        self.assertEqual(run_hook("Please fix the flaky upload test in the CI pipeline"), "")


class NumberedStillWorksTest(unittest.TestCase):
    def test_numbered_hint_wins(self):
        out = run_hook("1) fix the login\n2) update the docs")
        self.assertIn("2 numbered requests", out)

    def test_opt_out_and_slash(self):
        self.assertEqual(run_hook("Fix the login redirect\nUpdate the pricing page copy [nosplit]"), "")
        self.assertEqual(run_hook("/split Fix the login\nUpdate the docs"), "")


if __name__ == "__main__":
    unittest.main()
