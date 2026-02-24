#!/usr/bin/env bash
# Get the full content of entries from a session JSONL by 0-based index.
# Indices come from user-messages.sh output (which outputs 0-based indices).
# Uses jq --slurp to load the file as an array and index directly.
#
# Usage: get-entry.sh <session.jsonl> <index> [index ...]
# Example: get-entry.sh session.jsonl 228 469 652

set -euo pipefail
FILE="${1:?Usage: $0 <session.jsonl> <index> [index ...]}"
shift
[[ $# -gt 0 ]] || { echo "Usage: $0 <session.jsonl> <index> [index ...]" >&2; exit 1; }

# Build jq array literal from arguments: [228, 469, 652]
IDX_ARRAY="[$(printf '%s,' "$@" | sed 's/,$//')]"

jq -rs --argjson idxs "$IDX_ARRAY" '
def extract_content:
  if type == "string" then .
  elif type == "array" then
    map(
      if .type == "text" then .text
      elif .type == "tool_result" then "(tool_result id=\(.tool_use_id // "?"))"
      elif .type == "tool_use" then "(tool_use name=\(.name // "?"))"
      elif .type == "thinking" then "(thinking)"
      else "(\(.type))"
      end
    ) | join("\n")
  else "(content type: \(type))"
  end;

$idxs[] as $i |
"=== [\($i)] type=\(.[$i].type) role=\(.[$i].message.role // "-") ===\n" +
(.[$i].message.content | extract_content)
' "$FILE"
