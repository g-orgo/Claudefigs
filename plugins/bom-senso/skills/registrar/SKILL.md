---
name: registrar
description: Record a situation as a Bom senso example. Use when the user mentions a lapse of common sense (bom senso), chose to record one in the Bom senso question, or asks to save something as a common-sense example.
---

Record the situation with the store CLI. All text goes in pt-BR, short and generic enough to apply again.

1. Check for an existing entry in the same category:
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/store.py" list --category <category>`
   If a user entry already covers it, count one more occurrence with `bump <id>` and stop. Seed entries (`seed:` ids) cannot be bumped: record a new entry only if the situation adds something to the seed.
2. Otherwise add it:
   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/store.py" add --category <category> \
     --situation "what happened" --expected "what common sense called for" \
     --rule "an imperative rule for next time" --keywords "lowercase,accent-free,words"
   ```
   When the hook said the prompt may be a correction (no explicit "bom senso"), append `--timer 20 --session <session id>`: it opens a 20 s desktop notification where the user can decline; with no answer the example stays. Never ask with AskUserQuestion and never wait for the timer.
   Every example applies to every project, so write it without project-specific names. Give 4 to 10 keywords that a future prompt on this subject would contain.

Categories: `contexto-existente` (something existing was not surfaced), `consistencia` (siblings or variants left behind), `cobertura` (items skipped), `verificacao` (declared done without seeing it), `leitura-literal` (wrong referent, invented additions, missed purpose), `estados-obvios` (obvious states after an action), `regressao` (broke what was right), `referencia` (strayed from a given reference), `autonomia` (stopped or left work to the user), `pipeline` (agents and tools misused).

Then state in one line what was recorded (with `--timer`, add that it is auto-accepted in 20 s unless declined in the notification) and go back to the user's request. Do not mention the entry again.
