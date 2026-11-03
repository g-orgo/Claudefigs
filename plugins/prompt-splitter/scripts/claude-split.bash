# Sourced from ~/.bashrc: `claude split` and `claude --splits` open the prompt-splitter office, anything else runs the real claude.
claude() {
  if [ "${1:-}" = split ] || [ "${1:-}" = --splits ]; then
    shift
    "$HOME/.claude/local-plugins/plugins/prompt-splitter/scripts/claude-split.sh" "$@"
  else
    command claude "$@"
  fi
}
