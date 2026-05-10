#!/usr/bin/env bash
set -euo pipefail

# PermissionRequest hook for the tmux skill.
# Auto-permits tmux commands and tmux skill scripts that target claude/* sockets.
#
# The allowed-tools patterns in the skill frontmatter don't match when:
# - Variable preambles precede the script call (SOCKET=... && .../send-and-wait.sh ...)
# - Quoted arguments change the glob shape (tmux -L "claude/..." vs tmux -L claude/...)
#
# This hook inspects the full command text and permits anything that looks like
# a tmux skill operation targeting a claude session.

INPUT=$(cat)
TOOL=$(printf '%s' "$INPUT" | jq -r '.tool_name // ""')
COMMAND=$(printf '%s' "$INPUT" | jq -r '.tool_input.command // ""')

allow() {
  cat <<'EOF'
{"hookSpecificOutput":{"hookEventName":"PermissionRequest","decision":{"behavior":"allow"}}}
EOF
  exit 0
}

[[ "$TOOL" == "Bash" ]] || exit 0

# Permit tmux skill scripts targeting a claude session
if [[ "$COMMAND" == *"/scripts/send-and-wait.sh"* || \
      "$COMMAND" == *"/scripts/wait-for-text.sh"* || \
      "$COMMAND" == *"/scripts/start-session.sh"* || \
      "$COMMAND" == *"/scripts/stop-session.sh"* || \
      "$COMMAND" == *"/scripts/find-sessions.sh"* ]] &&
   [[ "$COMMAND" == *"claude/"* ]]; then
  allow
fi

# Permit raw tmux commands targeting a claude session socket
if [[ "$COMMAND" == *"tmux -L"* && "$COMMAND" == *"claude/"* ]]; then
  allow
fi

# Not our concern
exit 0
