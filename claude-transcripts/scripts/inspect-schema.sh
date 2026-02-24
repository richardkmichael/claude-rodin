#!/usr/bin/env bash
# Show the schema of a Claude Code session JSONL file:
# top-level entry types, user content formats, and field names.
# Run this first on an unfamiliar file to validate assumptions.
#
# Usage: inspect-schema.sh <session.jsonl>

set -euo pipefail
FILE="${1:?Usage: $0 <session.jsonl>}"

echo "=== Top-level keys (first entry) ==="
head -1 "$FILE" | jq 'keys'

echo ""
echo "=== Entry types and counts ==="
jq -r '.type // "(no type field)"' "$FILE" | sort | uniq -c | sort -rn

echo ""
echo "=== User entry content formats ==="
jq -r 'select(.type == "user") | .message.content |
  if type == "string" then "string"
  elif type == "array" then map(.type) | @json
  else "unknown: \(type)"
  end' "$FILE" | sort | uniq -c | sort -rn | head -20
