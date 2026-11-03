---
description: List the sessions dispatched by prompt-splitter and their state
allowed-tools: Bash(python3:*)
---

!`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/status.py" $ARGUMENTS`

Lists the sessions of the current directory; pass `--all` to list every directory.

Show the output above to the user as is, inside a code block. Do not add commentary beyond one line. Mention that `/splits` opens the navigable pane.
