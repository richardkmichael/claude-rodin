#!/usr/bin/env bash
set -euo pipefail

# PermissionRequest hook for the git-interactive skill.
# Auto-permits Bash commands that target claude-git-editor-* temp files.
# The allowed-tools globs can't cover shell redirections (cat > ...)
# because the > is parsed out before glob matching.

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

if [[ "$COMMAND" == *"claude-git-editor-"* ]]; then
  allow
fi

exit 0
