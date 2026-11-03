#!/usr/bin/env python3
"""UserPromptSubmit hook: deterministic tier hint for each prompt. Never crashes."""
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone

STATE_FILE = "/home/Orgo/.claude/state/router.jsonl"

T4 = ["auth", "autenticacao", "autorizacao", "login", "senha", "password", "jwt",
      "oauth", "sessao", "permiss", "seguranca", "security", "criptograf", "secret", "pagamento",
      "payment", "migration", "migracao", "schema", "banco de dados", "database", "arquitetura",
      "architecture", "lgpd", "api publica", "breaking"]
T3 = ["feature", "funcionalidade", "implementar", "implement", "nova tela", "new page", "fluxo",
      "flow", "refator", "refactor"]
ENDPOINT = ["endpoint"]
FRONT_WORDS = ["tela", "componente", "component", "ui", "page", "pagina"]
LAYER_FRONT = ["frontend", "front", "ui", "tela", "componente"]
LAYER_BACK = ["backend", "back", "api", "servico", "service"]
LAYER_DATA = ["banco", "database", "db", "tabela", "table"]
T1 = ["typo", "erro de digitacao", "texto", "copy", "css", "cor", "color", "margem", "margin",
      "padding", "espacamento", "fonte", "font", "renomear", "rename", "icone", "icon",
      "alinhamento", "align"]
QUESTION_START = ("como", "por que", "porque", "o que", "qual", "quais", "onde", "quando",
                  "explique", "explica", "what", "why", "how", "which", "explain")
ACTION = ["crie", "criar", "adicione", "adicionar", "implemente", "corrija", "corrigir", "altere",
          "alterar", "mude", "mudar", "remova", "remover", "faca", "fazer", "create", "add", "fix",
          "change", "remove", "update", "atualize"]

MESSAGES = {
    "T0": "Router: T0 (question). Answer directly; no operators, no plan.",
    "T1": "Router: T1 (trivial). Minimal reasoning: one short contract to one operator, or do it directly. No plan, no validator.",
    "T2": "Router: T2 (bounded). Brief reasoning, one operator with a full contract, review diff stat + test evidence.",
    "T3": "Router: T3 (multi-layer). Think deeply before planning (ultrathink). One contract per layer, validator at the end.",
    "T4": "Router: T4 (high risk). Think as deeply as possible (ultrathink). Plan before executing, validator, read risky hunks yourself.",
}


def norm(text):
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.lower()


def has_word(text, term):
    return re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", text) is not None


def find(text, terms):
    return [t for t in terms if has_word(text, t)]


def classify(prompt):
    forced = re.search(r"\[T([0-4])\]", prompt)
    if forced:
        return "T" + forced.group(1), True, []
    text = norm(prompt)
    length = len(prompt)
    t4 = find(text, T4)
    t3 = find(text, T3)
    if find(text, ENDPOINT) and find(text, FRONT_WORDS):
        t3 += ["endpoint+frontend"]
    layers = [bool(find(text, g)) for g in (LAYER_FRONT, LAYER_BACK, LAYER_DATA)]
    if sum(layers) >= 2:
        t3 += ["multi-layer"]
    if length > 1200:
        t3 += ["long prompt"]
    t1 = find(text, T1)
    if t4:
        return "T4", False, t4[:3]
    if t3:
        return "T3", False, t3[:3]
    if t1 and length < 300:
        return "T1", False, t1[:3]
    stripped = text.strip()
    is_question = stripped.endswith("?") or stripped.startswith(QUESTION_START)
    if length < 400 and is_question and not find(text, ACTION):
        return "T0", False, ["question"]
    return "T2", False, []


def main():
    try:
        data = json.loads(sys.stdin.read() or "{}")
        prompt = data.get("prompt") or ""
        if not isinstance(prompt, str) or not prompt.strip() or prompt.lstrip().startswith("/"):
            return 0
        tier, forced, cues = classify(prompt)
        msg = MESSAGES[tier]
        if cues:
            msg += " Matched: " + ", ".join(cues) + "."
        print(msg)
        try:
            os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
            record = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "session_id": data.get("session_id"),
                "cwd": data.get("cwd"),
                "tier": tier,
                "forced": forced,
                "cues": cues,
                "len": len(prompt),
            }
            with open(STATE_FILE, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record) + "\n")
        except Exception:
            pass
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
