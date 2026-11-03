#!/usr/bin/env bash
# Opens the read-only animated office of the prompt-splitter sessions (`claude split`, `claude --splits`).
set -euo pipefail
exec python3 "$(dirname "$(readlink -f "$0")")/claude_office.py" "$@"
