---
name: split
description: Split a prompt, or a file with a numbered list of requests, corrections or orders, into parallel background Claude sessions. Use when the user sends a prompt with several numbered or unrelated requests, points to a file with a numbered list of corrections/orders, when the prompt-splitter hook hints it, or as soon as you yourself identify several independent activities (from feedback, screenshots, logs or test results), even mid-task.
---

# Split a prompt into background sessions

## Protocol: split the moment you find multiple activities

The trigger is the work, not the prompt's shape. Whenever you identify two or more independent activities, split right then, before planning, dispatching an operator or starting any of them. This includes:
- a prompt with several asks, numbered or not;
- a single message of feedback, screenshots, logs or test results that your own analysis breaks into several problems (example: "camera is wrong", "storage list is gone", "new hover UI" from one in-game report);
- new independent problems discovered in the middle of a task.

The moment you list the activities to the user (or would list them), that list is the cue: go straight to step 0 with that list as the N requests. Do not first dispatch or start one of them and split afterwards. Do not wait for the hook hint: count the activities yourself. Activities that only make sense together (same files and same outcome, or one is a step of the other) count as one group and do not trigger a split.

0. Split by default. Do not ask whether to split: the user's standing choice is to always split multi-activity work. Keep the work in this session only when the prompt carries `[nosplit]` or step 1 finds a single group. Add `--view konsole` in step 5 only when the user asks for Konsole tabs.
1. Parse the requests. Requests may come from the prompt or from a file: read the file, and use each numbered item as a request. Keep the file's header or general context as shared context in every child prompt. Each numbered item is its own group. Then find the chains: items that share context (same files, module, screen or feature) or where one is a consequence of another (needs its result, builds on it, "depois de X") form a sync chain that runs in sequence (step 4); independent items stay async and run in parallel, which is the default. Do not merge chained items into one group. Unnumbered prompts are grouped by context: requests on the same location or shared responsibility form one group. The hook also flags unnumbered prompts (separate lines, `-`/`*` bullets, sentences, or connectors such as "e tambem", "alem disso", "outra coisa", "also", "another thing"); treat each such line, bullet or connector-led sentence as a candidate request, and when they turn out to be details of a single request, treat the prompt as one group without asking in step 0.
2. If only one group results, do the work in this session normally and stop here.
3. For each group write a self-contained prompt containing:
   - the original request text verbatim (for file items, the item text plus the file path and item number, so the child can reread the file);
   - any shared context from the original prompt or the file header (project, constraints);
   - this line: "You were started by prompt-splitter as one of N parallel sessions; other sessions handle: <one-line list>. Do not touch files outside your request; do not commit or push."
4. Ordering: detect ordering instructions in pt-BR or English ("Item 2 deve esperar o item 3", "depois que X terminar", "em sequencia", "sincrono", "um de cada vez", "so faca um item quando o anterior acabar", "run one at a time"). Express them as `"after": ["<name>", ...]` on the waiting groups, naming the groups they wait for. If the user asks for sync or one at a time, chain every group to the previous one in plan order. Groups linked by `after` form a chain: its items run in sequence and are numbered K.S (chain K, step S). Groups with no links are independent, run at once, and are numbered K.
5. Warn in the plan if groups may edit the same files or the same git repository.
6. Write the plan JSON to the scratchpad as `{"cwd": "<absolute project dir>", "groups": [{"name": "short-kebab", "title": "...", "prompt": "...", "after": ["..."]}]}` (`after` optional) and run:
   `title` is required: pt-BR, 4 to 10 words, saying concretely what the item does (example: "Corrigir precos e qualidade dos itens da loja"), with no ids or numbering. `name` stays a short kebab-case slug for the CLI.
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/dispatch.py" <plan.json>`
   Add `--view konsole` if the user chose the Konsole option.
7. Reply to the user only with the table printed by dispatch, plus how to watch: `claude agents`, `claude attach <id>`, `/prompt-splitter:sessions`. Do not start doing the requests in this session. In the dispatch table, `○` marks an item still running or waiting and `✓` marks a completed one. When presenting the plan before dispatch, list one line per group in execution order, chain items together, as "<mark> <label> <title>" (example: "○ 1 ...", "○ 2.1 ...", "○ 2.2 ..."), followed by the legend "✓ completo   ○ em andamento ou aguardando"; sync chain items appear in gray in the Splits pane. Never number them "Item X de Y".

State records now carry `parent` (the parent session id) and `group` (one id per split run), and the split-pane mode delivers aggregated results back to the parent session when every child of a group ends.
