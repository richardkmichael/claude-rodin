#!/usr/bin/env bash
# Show structural info for a session and its chain (parent/child sessions).
# Detects compaction boundaries, clear-context terminations, and cross-session
# links.  Follows the chain recursively and outputs JSON.
#
# Usage: session-info.sh <session.jsonl>
#
# parentUuid in JSONL entries is intra-session threading only — it never
# crosses session boundaries.  Cross-session links exist only as text
# pointers: "read the full transcript at: <path>" in entry [1] of a
# clear-context child session.

set -euo pipefail
FILE="${1:?Usage: $0 <session.jsonl>}"

# Resolve to absolute path
FILE="$(cd "$(dirname "$FILE")" && pwd)/$(basename "$FILE")"

# Track visited sessions to avoid cycles
declare -A VISITED

# Analyze a single session file (no recursion into parent/children)
analyze_session() {
  local file="$1"
  local session_id
  session_id="$(basename "$file" .jsonl)"

  local dir
  dir="$(dirname "$file")"

  # Single jq pass to extract all structural info
  jq -c -s --arg session_id "$session_id" --arg file "$file" '
    # Compaction boundaries: user entries containing the continuation marker
    def is_compaction_marker:
      (.message.content // "") |
      if type == "string" then
        test("This session is being continued from a previous conversation")
      elif type == "array" then
        any(.[]; .text? // "" | test("This session is being continued from a previous conversation"))
      else false
      end;

    # Clear-context termination: ExitPlanMode tool_use
    def is_exit_plan_mode:
      (.message.content // []) |
      if type == "array" then
        any(.[]; .type == "tool_use" and .name == "ExitPlanMode")
      else false
      end;

    # Parent pointer: "read the full transcript at:" in first 5 entries
    def extract_parent_path:
      [
        .[0:5][]
        | (.message.content // "") |
          if type == "string" then .
          elif type == "array" then map(.text? // "") | join(" ")
          else ""
          end
      ] | join(" ")
      | capture("read the full transcript at: (?<path>[^\\s]+\\.jsonl)").path
      // null;

    # Find compaction boundary indices
    (
      [ to_entries[] | select(.value.type == "user" and (.value | is_compaction_marker)) | .key ]
    ) as $compaction_indices |

    # Find clear-context termination index
    (
      [ to_entries[] | select(.value.type == "assistant" and (.value | is_exit_plan_mode)) | .key ]
      | last // null
    ) as $clear_context_idx |

    # Build compaction entries with segment size (entries after boundary)
    (
      [ $compaction_indices | to_entries[] |
        . as $entry |
        {
          index: $entry.value,
          entries_after: (
            # Next boundary or end of file
            (if ($entry.key + 1) < ($compaction_indices | length)
             then $compaction_indices[$entry.key + 1]
             else (if $clear_context_idx then $clear_context_idx else length end)
             end) - $entry.value - 1
          )
        }
      ]
    ) as $compactions |

    {
      session_id: $session_id,
      file: $file,
      entry_count: length,
      date_range: [
        (map(.timestamp // empty) | first // null),
        (map(.timestamp // empty) | last // null)
      ],
      compactions: $compactions,
      clear_context_end: (if $clear_context_idx then {index: $clear_context_idx} else null end),
      parent_path: extract_parent_path
    }
  ' "$file"
}

# Find compaction subagent files for a session
find_compact_subagents() {
  local file="$1"
  local session_id
  session_id="$(basename "$file" .jsonl)"
  local dir
  dir="$(dirname "$file")"

  local subagent_dir="$dir/$session_id/subagents"
  if [[ -d "$subagent_dir" ]]; then
    find "$subagent_dir" -name "agent-acompact-*.jsonl" -type f 2>/dev/null | sort
  fi
}

# Resolve the full chain starting from a session
# Direction: "both" (default), "up" (parent only), "down" (children only)
resolve_session() {
  local file="$1"
  local direction="${2:-both}"
  local depth="${3:-0}"

  # Guard against cycles, missing files, and excessive depth
  if [[ -n "${VISITED[$file]:-}" ]] || [[ ! -f "$file" ]] || (( depth > 10 )); then
    echo "null"
    return
  fi
  VISITED["$file"]=1

  local info
  info="$(analyze_session "$file")"

  local session_id
  session_id="$(echo "$info" | jq -r '.session_id')"

  # Add compaction subagent paths
  local compact_files=()
  while IFS= read -r cf; do
    [[ -n "$cf" ]] && compact_files+=("$cf")
  done < <(find_compact_subagents "$file")

  if (( ${#compact_files[@]} > 0 )); then
    # Merge subagent paths into compaction entries (by order)
    local compact_json
    compact_json="$(printf '%s\n' "${compact_files[@]}" | jq -R -s 'split("\n") | map(select(. != ""))')"
    info="$(echo "$info" | jq --argjson subagents "$compact_json" '
      .compactions |= [
        to_entries[] |
        .value + (if .key < ($subagents | length) then {summary_file: $subagents[.key]} else {} end)
      ]
    ')"
  fi

  # Resolve parent (only if going up or both)
  local parent_json="null"
  if [[ "$direction" == "both" || "$direction" == "up" ]]; then
    local parent_path
    parent_path="$(echo "$info" | jq -r '.parent_path // empty')"
    if [[ -n "$parent_path" && -f "$parent_path" ]]; then
      parent_json="$(resolve_session "$parent_path" "up" $((depth + 1)))"
    fi
  fi

  # Resolve children (only if going down or both)
  local children_json="[]"
  if [[ "$direction" == "both" || "$direction" == "down" ]]; then
    local dir
    dir="$(dirname "$file")"
    local child_files=()

    # Scan sibling JSONL files for references to this session
    if (( depth < 3 )); then
      while IFS= read -r sibling; do
        [[ "$sibling" == "$file" ]] && continue
        # Check first 5 lines for a reference to our session file
        if head -5 "$sibling" 2>/dev/null | grep -q "$session_id"; then
          child_files+=("$sibling")
        fi
      done < <(find "$dir" -maxdepth 1 -name "*.jsonl" -type f 2>/dev/null)
    fi

    if (( ${#child_files[@]} > 0 )); then
      local child_parts=()
      for child_file in "${child_files[@]}"; do
        local child_info
        child_info="$(resolve_session "$child_file" "down" $((depth + 1)))"
        child_parts+=("$child_info")
      done
      children_json="$(printf '%s\n' "${child_parts[@]}" | jq -s '.')"
    fi
  fi

  # Assemble final JSON, removing the internal parent_path field
  echo "$info" | jq \
    --argjson parent "$parent_json" \
    --argjson children "$children_json" \
    'del(.parent_path) | . + {parent: $parent, children: $children}'
}

resolve_session "$FILE" "both" 0 | jq .
