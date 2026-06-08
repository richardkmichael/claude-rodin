#!/usr/bin/env bash
# PostToolUse hook: surface session info to the user after start-session.sh runs.
#
# Reads PostToolUse JSON from stdin. If the Bash tool response contains
# start-session.sh JSON (keyed on .socket starting with "claude/"), returns a
# systemMessage with the log path and optionally the monitor command.

set -euo pipefail

input=$(cat)

# Only handle Bash tool calls
tool_name=$(printf '%s' "$input" | jq -r '.tool_name // empty')
[[ "$tool_name" == "Bash" ]] || exit 0

# For Bash tools, tool_response is an object with a .stdout field.
# The stdout contains start-session.sh JSON as a string.
response=$(printf '%s' "$input" | jq -r '.tool_response.stdout // empty')
socket=$(printf '%s' "$response" | jq -r '.socket // empty' 2>/dev/null) || exit 0
[[ "$socket" == claude/* ]] || exit 0

log=$(printf '%s' "$response" | jq -r '.log // empty')
[[ -n "$log" ]] || exit 0

# Check if --monitor was used in the command
command=$(printf '%s' "$input" | jq -r '.tool_input.command // empty')
msg="To follow the log: less +F ${log}"
if [[ ! "$command" =~ --monitor ]] && [[ ! "$command" =~ (^|[[:space:]])-m($|[[:space:]]) ]]; then
  msg="${msg}
To monitor: tmux -L ${socket} attach"
fi

jq -n --arg msg "$msg" '{systemMessage: $msg}'
