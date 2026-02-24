#!/usr/bin/env bash
# List human-typed user messages from a session JSONL.
# Filters out: tool results, teammate messages, system commands,
# compaction summaries, and interrupt notices.
#
# Usage: user-messages.sh <session.jsonl>
# Output: [INDEX] first 200 chars of message text

set -euo pipefail
FILE="${1:?Usage: $0 <session.jsonl>}"

jq -rn '
def extract_text:
  if type == "string" and length > 0 then .
  elif type == "array" then
    map(select(.type == "text") | .text) | select(length > 0) | join("\n")
  else empty
  end;

def is_human:
  [startswith("[Request interrupted"),
   startswith("This session is being continued"),
   startswith("<teammate-message"),
   startswith("<local-command"),
   startswith("<command-name"),
   startswith("<command-message"),
   startswith("Base directory for this skill:")] | any | not;

[inputs |
  select(.type == "user") |
  .message.content | extract_text | select(. != null) | select(is_human) |
  {idx: (input_line_number - 1), text: .}
] | .[] | "[\(.idx)] \(.text[:200])"
' "$FILE"
