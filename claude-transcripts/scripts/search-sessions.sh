#!/usr/bin/env bash
# Search for a keyword across Claude Code session JSONL files.
# Outputs matching entries with session file, entry index, and context.
#
# Usage: search-sessions.sh <pattern> <session.jsonl> [session.jsonl ...]
# Example: search-sessions.sh "REVIEW_PROMPT" ~/.claude/projects/my-project/*.jsonl
#
# To search a project directory recursively:
#   search-sessions.sh "pattern" ~/.claude/projects/my-project/**/*.jsonl

set -euo pipefail
PATTERN="${1:?Usage: $0 <pattern> <file> [file ...]}"
shift
FILES=("$@")
[[ ${#FILES[@]} -gt 0 ]] || { echo "Usage: $0 <pattern> <file> [file ...]" >&2; exit 1; }

for FILE in "${FILES[@]}"; do
  jq -rn --arg pat "$PATTERN" --arg file "$FILE" '
  def extract_text:
    if type == "string" then .
    elif type == "array" then
      map(select(.type == "text") | .text) | join("\n")
    else ""
    end;

  [inputs |
    .message.content | extract_text |
    select(test($pat; "i")) |
    {idx: (input_line_number - 1), text: .}
  ] | if length > 0 then
    "=== \($file) ===",
    (.[] | "  [\(.idx)] \(.text)")
  else empty end
  ' "$FILE"
done
