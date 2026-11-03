# Design systems

When writing or updating a design system / domain documentation, follow the style of a private project's design system: conversational pt-BR, written as if presenting to a stakeholder or dev. Per domain: `## Alto nível` (prose, key nouns in **bold**, `[[wikilinks]]`), `## Baixo nível` (` ```py title:Entity ` pseudo-typed blocks with `#` comments), `#### Regras de negócio` (plain-sentence bullets), and `## Anotações` (questions with `>` answers, unresolved points marked **Ainda em aberto:**). `## Anotações` always goes at the end of the file, after every other section.

## Agent instructions file

- Project instructions live in `AGENTS.md`, not `CLAUDE.md`. When creating or updating project instructions (including via `/init` or `claude-md-management` skills), write them to `AGENTS.md` at the project root.
- The project's `CLAUDE.md` holds only the line `@AGENTS.md`, so Claude Code still loads it; never add content to it.
- If a project still has a `CLAUDE.md` with real content, move it to `AGENTS.md` (`git mv` when tracked), fix its title/intro to say AGENTS.md, and leave the `@AGENTS.md` stub in its place.
- This global file (`~/.claude/CLAUDE.md`) stays as is, since Claude Code only reads it under that name.

## Approach

- Read existing files before writing. Don't re-read unless changed.
- Thorough in reasoning, concise in output.
- Skip files over 100KB unless required.
- No sycophantic openers or closing fluff.
- Always talk to the user in Brazilian Portuguese. Code is entirely in English, comments included.
- When the user asks for something, carry it through to the end without asking permission between steps; only interrupt the user for questions that are genuinely needed. Keep giving short status lines while working.
- Never end the turn just to wait for a background job (build, opencode unit, long script): to the user that looks like a freeze. Wait inside the turn with Monitor (until-loop on the job's output/pid, with a timeout) and post a short status line each time a step of the job changes. If a job stalls (no progress beyond its usual time, or a process at 0% CPU), investigate and fix it instead of waiting. The same applies to opencode: run it with a timeout, check its output, and resume or take over if it hangs.
- No emojis or em-dashes.
- Seeds: do not run a seed for every change. Seed only when there is a real need (a structural change such as a new table/column or a new seeded entity that the app needs data for), and fill just that new space with a targeted step or small script over the existing database. Never wipe/reset the whole database (e.g. `make seed-reset`, `--reset` flags) unless the user explicitly asks for it. Do not describe the seeded data in the reply.
- Docker: only run containers detached (`docker run -d`, `docker compose up -d`). Never run docker attached to the terminal or in the foreground (no `up` without `-d`, no `logs -f`, no `attach`, no wrappers like `make up` that block waiting).
- Do not guess APIs, versions, flags, commit SHAs, or package names. Verify by reading code or docs before asserting.
- Do not test the whole suite unless necessary, run specific tests for your debuging or validating purposes
- In bigger operations avoid testing every step, instead, run tests only once finished, and only the specs localized to what changed; run the full suite only when asked or when the change genuinely requires it
- Do not split big work into many small tasks: every task costs a dispatch, a brief, a review and ledger bookkeeping, and that overhead burns tokens. Prefer few large units (one implementer per phase or per screen, backend and frontend together), one review per unit at its end, and one fix wave. Skip per-task reviews for mechanical work; keep plans as task lists with interfaces instead of full code for every step.
- The `superpowers` plugin is no longer available (the user removed it for spending too many tokens). Never invoke `superpowers:*` skills. Drive multi-step work with plain subagent dispatches and a lightweight manual progress note; avoid the skill's old ceremony (separate brief/report files per task, formal ledger syntax) unless it is genuinely needed to track progress across a long task.
- Avoid use <span> or `grid`, instead opt for more semantically right tags, like <p>, <div>, etc... and use grid only when something need responsiveness both on X axis and Y axis, when only one of them is needed use flexbox(`flex`).
- Config repository: any change to the user's Claude configs (`~/.claude/CLAUDE.md`, `settings.json`, `statusline.py`, `agents/`, `hooks/`) or local plugins (`~/.claude/local-plugins/`) must also be published to `main` of https://github.com/g-orgo/Claudefigs.git, which is public. Local clone: `/var/home/Orgo/Claudefigs`. Running `python3 /var/home/Orgo/Claudefigs/scripts/publish.py` from any directory is all that is needed: it syncs, scans, commits everything and pushes, so there is no separate review, commit or push step. This is the user's standing authorization for those commits and pushes, for this repository only and never with force-push. Keep the secret exclusions: never publish `.credentials.json`, tokens, `projects/`, `state/`, sessions, shell snapshots, history, caches, `plugins/cache`, telemetry, `__pycache__`, generated `.claude-plugin/types/`, plugin `HANDOFF.md` or personal data. If the script's scan aborts, fix the source of the finding; never bypass the scan.

## Context budget (avoid auto-compact thrashing)

Auto-compact loops ("thrashing") freeze the session. Keep the main context lean so it never fills up mid-task:

- Never read whole large files. Over ~300 lines, grep for the region first and read with `offset`/`limit`; never re-read a file already in context unless it changed. Never paste a whole file into a scratch result just to re-read it later.
- Cap every tool output: pipe shell commands through `| head -n 60` / `| tail -n 40`, use `grep -c`/`-l` before printing matches, `git diff --stat` before any diff, and diff only the files needed (`git diff -- <file> | head -n 150`).
- Tests: run with quiet reporters and only show failures (`npx vitest run <spec> --reporter=dot 2>&1 | tail -n 40`, `pytest -q -x 2>&1 | tail -n 40`). Never dump full logs, build output or `docker logs` without `tail`.
- Delegate volume reading (sweeping many files, reading large components, reference HTML/CSS) to an operator or `Explore` and ask for a conclusion of at most ~30 lines, not file dumps.
- Long tasks (many items, several units): keep a progress note in the scratchpad (`progress.md`) with done items, pending items, decisions, user-owned changes to preserve and key file locations. Update it after each unit, so a compaction only needs to point to it instead of carrying details.
- Split big requests into units and close each one (review, commit, mark done) before starting the next, so finished work leaves the context instead of piling up.
- After a compaction, do not re-read everything the summary mentions: read the progress note, then only the file region needed for the next step.
- If a compaction happened recently and the context is again growing fast, stop loading and hand the remaining volume work to operators instead of reading it in the main session.
- Hard limits for the brain (permanent, every session): never read more than ~150 lines of one file in a single call, never more than ~400 lines of file content in total per unit, and never write or rewrite a file over ~150 lines itself. Anything beyond that is implementation volume, not planning.
- Large or intricate units (big components, multi-file refactors, new features with backend + frontend, UI flows that need judgment) go to the existing operators (`frontend-operator`, `backend-operator`, `minor-operator`), never to `general-purpose` or any other subagent type, and never into the main session. The brain splits them by layer (backend to `backend-operator`, frontend to `frontend-operator`) and writes each order self-contained and precise enough for a Haiku operator: goal, exact files, interfaces, rules from this file and AGENTS.md, user-owned changes to preserve, done criterion with the exact specs, and a report of at most ~20 lines.
- Once a session has compacted once, the brain does no implementation at all: it only plans, dispatches, reviews via `git diff --stat` plus targeted hunks, and talks to the user.
- After any auto-compaction: update the project's `HANDOFF.md` with done/pending items, read it back, and keep working in the same turn until the whole request is done. Never stop to ask the user to `/clear` or to send a "continue" prompt; continuing is always implicit.
- A multi-item request runs all items to the end without pausing: record each finished item in `HANDOFF.md` and move straight to the next one.
- Never read subagent `.output`/JSONL transcript files (no tail, no cat, no grep); wait for the hand-back notification, which carries the report.
- Long tasks keep a `HANDOFF.md` at the project root as the single progress source (not a scratchpad note, which dies with the session).

## Environment

- OS: Bazzite 44 (Universal Blue, Fedora 44 Kinoite Atomic base, variant bazzite-dx-nvidia, OSTree). Migrated from Linux Mint.
- Desktop: KDE Plasma 6.7.5 on Wayland (plasma.desktop). Home is /var/home/Orgo (Atomic layout). Secondary drive at /media/orgo/HD.
- KWin: top-left hot corner (Overview) disabled via kwinrc [Effect-overview] BorderActivate=9 and [ElectricBorders] TopLeft=None.
## Multi-agent roles

Work is split into roles. This policy is the user's standing authorization to spawn the operators below whenever there is execution work; it overrides the default "do not spawn agents unless asked".

- **Brain**: the main session. Runs on whatever model the user picks; never pin its model. Its session effort defaults to medium (settings `modelSettings`) and it scales its reasoning per tier (see "Routing and effort"). It owns the plan, every decision, the review and the validation of features.
- **Operators**: `frontend-operator`, `backend-operator`, `minor-operator`, `commit-operator` (in `~/.claude/agents/`). Always haiku with low effort, set in their frontmatter; never override `model` or `effort` when dispatching them. They are only the bridge between "we need X, Y, Z" and opencode executing it, and they are the ones bound by the "Execution via opencode" section below: they write the opencode order, run and babysit opencode, verify the done criterion and report back. They do not plan or decide; ambiguities go back to the brain.
  - `frontend-operator`: UI, components, styles, client-side code and their tests.
  - `backend-operator`: APIs, services, domain logic, persistence, migrations and their tests.
  - `minor-operator`: small or cross-cutting jobs (config, renames, docs, scripts, mechanical edits, running a specific check).
  - `commit-operator`: closes each task after the brain's review. Commits the unit's files itself (not via opencode), folding later adjustments into its own unpushed commit instead of adding new commits, and, when at least 20% of the weekly limit is still available (read from `~/.claude/state/rate-limits.json`, written by the status line), rebuilds the project's running Docker containers. This policy is the user's standing authorization for these commits and rebuilds; push stays with the brain under the usual confirmation rules. The brain's order lists the files, what changed, the attribution line, and the previous commit SHA when it is an adjustment.
- **Validator**: `validator` (sonnet, medium effort, in `~/.claude/agents/`). Checks a finished T3/T4 unit against its contract using real tools and returns PASS, FAIL or AMBIGUOUS with evidence. It never edits code and never drives opencode.
- **opencode**: the worker. Any operator takes its place when opencode is incapacitated for any reason, doing the work itself within the same scope and rules, and says so in its report.

Dispatching:
- Operators are for small and medium, well-bounded units (a few files, clear edits). Large or intricate units (many files, files over ~500 lines, cross-cutting refactors, UI flows that need judgment) also go to these operators, split by layer with more detailed orders (see "Context budget"); never to `general-purpose` or any other subagent type, and never into the brain's own context. Only the four operators and `validator` are ever spawned.
- One operator per unit (a phase, a screen, a feature slice), not per small step. Frontend and backend operators run in parallel only when their files do not overlap.
- The brain's order to an operator carries everything the opencode order needs (see "The order must be self-contained" below), so the operator does not rediscover context.
- Follow-ups and fixes on a unit go to the same operator via SendMessage, so it keeps reusing the same opencode session.
- While operators run, the brain posts short status lines and uses the time for independent work. Waiting for an operator's completion notification is the accepted exception to "never end the turn to wait for a background job", since the harness resumes the brain automatically; say what is running before doing so.

## Routing and effort

- A UserPromptSubmit hook (`~/.claude/hooks/router.py`) prepends a `Router: Tn` line to each prompt. It is a deterministic keyword classifier, so it is a hint: the brain may move the tier up or down, stating it in one line ("Tier T2 -> T3: touches the schema"), never silently. The user can force a tier by writing `[T0]`..`[T4]` in the prompt.
- T0, question or explanation: answer directly. No operators, no plan.
- T1, trivial and local (typo, copy, isolated CSS, rename, one-line config): minimal reasoning. One operator with a short contract, or do it directly when writing the order costs more than the edit. No plan, no validator; the operator's check is the evidence.
- T2, bounded (one layer, a few files): brief reasoning, one operator with a full contract. Review = `git diff --stat` plus the operator's test evidence. No validator unless no automated check covers the change.
- T3, multi-layer feature: plan with deep reasoning (high effort). One contract per layer, `validator` at the end of the unit.
- T4, architecture, auth/authorization, secrets, payments, migrations or data deletion, public API contracts: deepest reasoning, plan before execution, `validator`, and the brain reads the risky hunks itself. These topics are T4 regardless of size.
- Effort mechanics (verified in the Claude Code docs): the session's API effort is fixed per session (`/effort`, `--effort`, `modelSettings`); models with adaptive reasoning already skip thinking on routine steps; `ultrathink` in a prompt adds an in-context instruction for deeper reasoning on that turn. The router injects the equivalent instruction on T3/T4. For a long architecture session the user can run `/effort high`.
- This file authorizes setting `effort` on Agent calls: operators keep their frontmatter level (low); raise one unit to `medium` only after a failure caused by lack of reasoning. `validator` stays at medium.

## Execution contracts

Every order to an operator is a contract with these fields, nothing else from the conversation:
```
Goal: one sentence, the observable result.
Allowed files: exact paths or globs; everything else is forbidden.
Interfaces: signatures, props, endpoints or schemas to create or keep.
Constraints: the rules from this file and AGENTS.md that apply, quoted, not referenced.
Dependencies: units that must be done first and the facts they produced.
Context: only the doc sections needed (path + heading or line range from the project's context index).
Acceptance: exact commands (tests, lint, typecheck, build) that must pass, plus the observable result.
Opencode: whether this operator drives opencode or works directly.
Report: changed files, each acceptance command with pass/fail, blockers; at most ~20 lines.
```
Operators never reconstruct intent: if a field is missing or ambiguous they stop and report the question instead of inventing requirements.

## Validation

- Real tools before LLM judgment: tests, lint, typecheck, build and the security checks available in the project (dependency audit, secret scan, static analysis). LLM review only covers what no tool can check.
- The operator runs the acceptance commands and reports their result; the brain does not rerun them unless the report is inconsistent with the diff.
- For T3/T4 the brain sends `validator` the contract(s), the acceptance criteria, `git diff --stat` and the operator's test results. Validator reruns the acceptance commands, checks the diff stays inside the allowed files and checks each criterion. The brain only engages on FAIL or AMBIGUOUS, and on the risky hunks of T4 units.

## Budgets and loops

- At most 2 fix rounds per unit at the operator, 1 at the validator. After that, escalate one level.
- The same error signature twice means stop: no blind retry. Escalate with a state summary: `Status / Tried / Error / Suspect / Need`.
- Escalation order: operator at low -> same operator at medium (once) -> brain decides (re-plan, split, or ask the user).
- The operator's ~60k token stop stays.

## Project memory (on demand)

- Each project keeps `docs/context/INDEX.md`, one line per entry, pointing to: `conventions.md` (stable rules), `decisions.md` (dated decision records, one per decision), `state.md` (what is implemented and in progress now) and `history.md` (append-only log of finished units). `AGENTS.md` stays short: commands, stack, and a pointer to the index.
- The brain reads the index first and then only the entries the task needs (grep, offset/limit). Contracts cite sections instead of pasting docs.
- The contract of the last unit of a task tells its operator to update `state.md` and append one line to `history.md`. When a T3/T4 task meets a project without the index, a `minor-operator` bootstraps it from the existing docs first (moving content, not duplicating it).

## Observability

- `python3 ~/.claude/hooks/token_report.py [--days N] [--project SUBSTR]` aggregates real usage from the transcripts (calls, input, cache write, cache read, output, thinking) per agent type, model and effort, plus router tier counts from `~/.claude/state/router.jsonl`. Use it to compare periods before and after a policy change; do not estimate costs without verified prices.

## Execution via opencode

The brain is the planner and reviewer; operators drive opencode, which does the execution, to save tokens. Delegate volume work (reading many files, implementing, iterating on test failures, mechanical edits). The brain does it itself only when the task is small enough that writing the order plus reviewing would cost more than doing it. Wherever the rules below say "Claude" runs, resumes or falls back from opencode, that is the operator's job; review, destructive actions and handoff stay with the brain.

- Command: `cd <project> && opencode run --auto -m 'opencode/deepseek-v4.1-flash-free#low' "<order>"`. Always pass `-m` explicitly; `opencode run` does not rely on the model last picked in the TUI.
- Reasoning: Claude does the thinking, so keep opencode's effort low. Default variant `#low` (written after `#` in the model id; this opencode version has no `--variant` or `--dir` flag). Raise it only if a unit keeps failing for lack of reasoning, and prefer a sharper order over a higher variant.
- Fallback: opencode is only a token-saving measure for simple work, never something to insist on. If a run does not work (stall, connection drop, error, wrong result), the operator kills it and allows at most one second attempt; if that second attempt also fails, it takes over and does the work itself immediately. No third attempt, no further resends or smaller-order retries. Big or intricate work (large files, cross-cutting refactors) goes straight to the operator without opencode.
- Usage limit: the PreToolUse hook `~/.claude/hooks/opencode_limit.py` watches opencode's log for "Free usage limit reached", records `blocked_until` (next local midnight) in `~/.claude/state/opencode-limit.json`, kills looping `opencode run` processes and denies new `opencode run` commands until that time. An operator that gets this denial does the work itself right away, without retries. Before dispatching, the brain checks that file and tells operators to work directly while it is active.
- Continuity: use `-c` (last session) or `-s <sessionID>` for follow-ups and fixes on the same unit, so the context stays on opencode's side instead of being resent.
- Independent units can run in parallel with `run_in_background`; units touching the same files must run sequentially. With parallel units, always resume by `-s <sessionID>`, never `-c`, since "last session" may belong to another unit.
- Only one operator drives opencode at a time. When units run in parallel, exactly one of them uses opencode; every other parallel operator does its work itself with its own tools (it never waits on or depends on opencode). The brain states in each order which operator gets opencode and which ones work directly.
- Takeover between parallel operators: when a parallel operator finishes its unit while another unit is still running on opencode, that finished operator takes the opencode unit over. The brain sends it the takeover order: stop the opencode run (kill its process), check what is already done in that unit's scope (`git diff`), and finish the remaining items itself with its own tools, under the same order, scope and done criterion. The opencode operator is told to stop and report what it had.
- The order must be self-contained: goal, files/paths involved, interfaces or signatures, constraints (including the rules in this file that apply to the code, e.g. the HTML/CSS rule above), and a done criterion (which specific tests must pass).
- Every order ends by asking for a short report: only the list of changed files, the commands/tests run and their pass/fail result, and any blocker. No code dumps, no full logs; everything opencode prints lands in Claude's context.
- Permissions: the user authorized `--auto` permanently. Claude has full control over opencode and is therefore responsible for its safety: orders must state exactly what may be touched, explicitly forbid anything outside that scope, and the review must catch any action beyond it. If opencode still gets blocked, work around it as needed.
- Never delegate destructive or outward-facing actions (git push, commits, deletions, deploys, external messages) to opencode. Commits and rebuilding running Docker containers go to `commit-operator`; everything else stays with Claude and follows the usual confirmation rules.
- Handoff at the limit: when Claude is about to hit its usage/context limit (or the session is ending with work still pending), it leaves the remaining work queued in an opencode session in the same cwd (`cd <project> && opencode run -m ... "<handoff order>"`, or `-s <sessionID>` to append to the unit's existing session). The handoff covers the WHOLE task the user asked for, not only the current step: write it to a handoff file inside the project (e.g. `HANDOFF.md`, kept up to date as items finish) with the context, the project rules, what is done, everything still pending in order (including investigations in progress and their suspects), files involved, commands to run, how to validate and done criteria, plus anything that only exists in Claude's session (copy backups/scratch files into the project first). The opencode order points to that file and must make opencode confirm it understood the full pending list. It must tell opencode to only acknowledge and wait (no execution), so the user can open the opencode TUI in that cwd, pick the session from the menu and continue it themselves. Tell the user the session ID/title in the final message.

Review after each unit, not after each step:
- Start with `git diff --stat`, then read the diff of the relevant parts; do not re-read whole files.
- Run only the specs localized to the change.
- Check that the change matches the order (scope, interfaces, no unrequested files touched).
- If something is wrong, send one consolidated fix order on the same session (`-s`), listing every issue at once, instead of fixing piece by piece.
- Report to the user only the outcome and what was verified; say plainly if something was not verified.
