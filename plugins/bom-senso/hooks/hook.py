#!/usr/bin/env python3
"""Hook entry point for SessionStart, SubagentStart and UserPromptSubmit.

Never fails: any error results in silence and exit code 0.
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import detect  # noqa: E402
import store  # noqa: E402

EVENTS = {"session": "SessionStart", "subagent": "SubagentStart", "prompt": "UserPromptSubmit"}
USER_RULES_LIMIT = 8
CLI = f'python3 "{ROOT}/scripts/store.py"'

ASK = """bom-senso: this prompt may be a correction (signal: "{signal}"). If the user is correcting something the agent got wrong, skipped or should have noticed unprompted, call AskUserQuestion once, in pt-BR, before any other step (including a split), then carry on with the work. If it is a new request, or the same situation was already asked in this session, ignore this note silently. If AskUserQuestion is unavailable, skip it.
Question: one line naming the situation, asking whether to record it as a Bom senso example. Header: "Bom senso". Options:
- "Registrar global": applies to every project.
- "So neste projeto": applies only here.
- "Nao registrar": this one is not a lapse of common sense.
- "Nao perguntar mais": silence this for the session.
On the first two, follow the bom-senso `registrar` skill (use --project "{cwd}" for the second). On the last, run: {cli} mute {session_id}"""


def checklist(name):
    return (ROOT / "data" / name).read_text(encoding="utf-8").strip()


def rules_block(title, examples):
    if not examples:
        return ""
    return f"\n{title}\n" + "\n".join(f"- {e['rule']}" for e in examples)


def context_for(event, data):
    cwd = data.get("cwd") or os.getcwd()
    if event == "session":
        rules = store.relevant_user_rules(cwd, USER_RULES_LIMIT)
        return checklist("brain.md") + rules_block("Examples the user recorded:", rules)
    if event == "subagent":
        rules = store.relevant_user_rules(cwd, USER_RULES_LIMIT)
        return checklist("operator.md") + rules_block("Examples the user recorded:", rules)
    prompt = data.get("prompt") or ""
    if not detect.is_user_text(prompt):
        return ""
    parts = []
    examples = store.seeds() + store.user_examples()
    related = detect.related_examples(prompt, examples)
    if related:
        parts.append(rules_block("bom-senso, related past lapses:", related).strip())
    signal = detect.correction_signal(prompt)
    session_id = data.get("session_id") or ""
    if signal and os.environ.get("CLAUDE_SPLIT_CHILD") != "1" and not store.is_muted(session_id):
        parts.append(ASK.format(signal=signal, cwd=cwd, cli=CLI, session_id=session_id))
    return "\n".join(parts)


def main():
    event = EVENTS[sys.argv[1]]
    context = context_for(sys.argv[1], json.loads(sys.stdin.read() or "{}"))
    if context:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": context}}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
