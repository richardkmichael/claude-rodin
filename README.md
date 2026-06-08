# claude-transcripts

A Claude Code skill for reading, searching, and navigating session transcript
JSONL files. Provides four bash scripts built on `jq`.

## Installation

Package the skill and install the resulting `.skill` file into Claude Code:

```
python scripts/package_skill.py claude-transcripts/
```

The skill activates automatically when Claude is asked to look at past
conversations, extract user questions, search session history, or recover
pre-compaction content.

---

## Session file locations

Claude Code stores transcripts under:

```
~/.claude/projects/<url-encoded-project-path>/
  <session-id>.jsonl                  main transcript
  <session-id>/subagents/
    agent-<id>.jsonl                  Task tool subagents (Explore, Plan, etc.)
    agent-acompact-<id>.jsonl         compaction summaries
```

The project directory name is the filesystem path with `/` replaced by `-`. For
example, `/Users/alice/src/myproject` becomes
`-Users-alice-src-myproject`.

Compaction occurs when a session approaches the context limit. It only affects
the model's active context — all original entries remain in the main JSONL at
their original indices and are fully searchable. The scripts scan the full file,
so pre-compaction entries are automatically included with no special handling.

`agent-acompact-*.jsonl` files contain the compaction agent's own transcript:
the summary it generated for the model going forward. They are useful for reading
what the model was told happened, but not needed to access the original content.

---

## Scripts

All scripts use **0-based indices**. An index shown by `user-messages.sh` or
`search-sessions.sh` is always the correct index to pass to `get-entry.sh`.

### inspect-schema.sh

```
bash inspect-schema.sh <session.jsonl>
```

Shows:
- Top-level keys of the first entry
- Count of each entry type (`user`, `assistant`, `progress`, etc.)
- Distribution of user content formats (`string`, `["text"]`, `["tool_result"]`)

Run this first on any unfamiliar file. If the schema has changed (unexpected
top-level keys or content types), use this output to adapt jq queries before
running the other scripts.

### user-messages.sh

```
bash user-messages.sh <session.jsonl>
```

Lists human-typed messages with their 0-based index and the first 200 characters
of text. Filters out:
- Tool result entries (`["tool_result"]` content)
- Teammate messages (`<teammate-message>` XML)
- Slash-command entries (`<command-name>`, `<local-command-*>`)
- Context compaction summaries (`This session is being continued from...`)
- Interrupt notices (`[Request interrupted...]`)
- Skill invocation headers (`Base directory for this skill:`)

Use this to get a quick map of what questions were asked. For the full text of
any entry, pass its index to `get-entry.sh`.

### get-entry.sh

```
bash get-entry.sh <session.jsonl> <index> [index ...]
```

Fetches the full content of one or more entries by 0-based index. Works on any
entry type (user, assistant, system, progress). Non-text content (tool results,
tool use calls, thinking blocks) is summarised as `(tool_result id=...)` etc.
rather than omitted, so the output still conveys what happened at that point in
the conversation.

### search-sessions.sh

```
bash search-sessions.sh <pattern> <session.jsonl> [session.jsonl ...]
```

Searches all entry content across one or more session files for a jq regex
(case-insensitive). Outputs full untruncated matching content grouped by file.

To search a whole project:

```
bash search-sessions.sh "keyword" ~/.claude/projects/<dir>/*.jsonl
```

---

## Design decisions

### jq over Python

All scripts use `jq` with no Python dependency. This means:
- No interpreter startup overhead on large files
- `jq --slurp` (`-s`) loads a JSONL file as an array and enables O(1) index
  access (`.[N]`) without scanning the whole file per lookup
- `jq -n '[inputs | ...]'` streams entries for listing and search, keeping
  memory usage bounded

The earlier prototype (`claude_exp-extract-conversation.py`) was rewritten in
jq precisely because permissions had to be granted per invocation in Claude Code.
Shell scripts can be pre-authorised once.

### No environment variables for data

All data is passed as positional arguments, never via environment variables.
Claude Code's `allowedTools` permission patterns match on command strings; env
var prefixes (`FOO=bar script.sh`) make those patterns harder to specify and
review.

### Schema detection, not hardcoded field paths

`inspect-schema.sh` exists so the agent can verify the schema before relying on
the other scripts. The SKILL.md instructs Claude to run it first on unfamiliar
files and adapt if the structure differs. Known assumptions: `.type`,
`.message.role`, `.message.content`. If these change, the scripts need updating
but the agent will detect the mismatch rather than silently producing empty
output.

### Content format duality

`user` entries can have either a plain string or an array of typed blocks as
`.message.content`. The array form is used for tool results, text blocks, images,
etc. Every script that extracts text uses the same `extract_text` helper:

```jq
def extract_text:
  if type == "string" and length > 0 then .
  elif type == "array" then
    map(select(.type == "text") | .text) | select(length > 0) | join("\n")
  else empty
  end;
```

This is the most likely place to need updating if the API adds new content block
types that should be treated as text.

### 0-based indices everywhere

`user-messages.sh` uses `input_line_number - 1` (jq's `input_line_number` is
1-based) so the displayed index is always the correct 0-based array index for
`jq -s '.[N]'`. This makes the `user-messages.sh` → `get-entry.sh` workflow
unambiguous: copy the `[N]` index directly.

### Truncation policy

`user-messages.sh` truncates to 200 characters — it is a listing/index tool,
not a content viewer. `get-entry.sh` provides full text.

`search-sessions.sh` does not truncate — truncating search results risks hiding
the relevant portion of a match. If output volume is a concern, the caller can
pipe through `head`.

---

## What may need updating

- `is_human` filter in `user-messages.sh`: add new prefixes if Claude Code
  introduces new system message formats that appear as user entries.
- `extract_text` in all scripts: extend if new text-bearing content block types
  are added to the Anthropic API.
- Top-level field paths (`.type`, `.message`): if the JSONL wrapper format
  changes, `inspect-schema.sh` will surface the discrepancy immediately.

---

# tool-monitor

A Rust binary that captures every Claude Code tool invocation into a SQLite
database via Claude Code's hook system. Pairs with a `tool-usage` skill that
lets Claude query the database mid-session to answer questions about past tool
activity.

## How it works

Claude Code fires four hook events around each tool call:

- PreToolUse — before the tool executes (captures tool name + input)
- PostToolUse — after success (captures input + response)
- PostToolUseFailure — after failure (captures input + error)
- PermissionRequest — when Claude requests permission (captures input +
  permission_suggestions)

The hook command reads the JSON payload from stdin and appends a row to
`tool_events`. It always exits 0 so it never interrupts Claude's workflow.

## Installation

Build and install the binary:

```
cargo install --path tool-monitor/ --root ~
# installs to ~/bin/claude-tool-monitor
```

Add hooks to `.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse":          [{"matcher": "*", "hooks": [{"type": "command", "command": "claude-tool-monitor ~/.claude/tool-monitor.sqlite"}]}],
    "PostToolUse":         [{"matcher": "*", "hooks": [{"type": "command", "command": "claude-tool-monitor ~/.claude/tool-monitor.sqlite"}]}],
    "PostToolUseFailure":  [{"matcher": "*", "hooks": [{"type": "command", "command": "claude-tool-monitor ~/.claude/tool-monitor.sqlite"}]}],
    "PermissionRequest":   [{"matcher": "*", "hooks": [{"type": "command", "command": "claude-tool-monitor ~/.claude/tool-monitor.sqlite"}]}]
  }
}
```

The database is created automatically on first run.

## Database schema (V3)

The `tool_events` table stores the raw payload JSON plus generated columns
that extract the stable top-level fields (session_id, hook_event_name,
tool_name, cwd, transcript_path) so they can be indexed without duplication.

Six FTS5 virtual tables (fts_bash_command, fts_file_path, fts_grep_pattern,
fts_glob_pattern, fts_url, fts_search_query) are populated by INSERT triggers
and support fast substring/wildcard search. Expression indexes cover the same
fields for exact-match lookups.

A `tool_schemas` table stores the JSON Schema for each tool's inputs and
outputs, making the database self-describing.

## Skill: tool-usage

`skills/tool-usage/` is a Claude Code skill that allows Claude to run
`sqlite3` against the database. Install it like the claude-transcripts skill:

```
python scripts/package_skill.py skills/tool-usage/
```

The skill activates when asked about tool usage statistics, recent commands,
files accessed, session activity, or any analysis of past tool behaviour.

Example queries the skill supports:

```sql
-- Most-used tools
SELECT tool_name, COUNT(*) AS uses
FROM tool_events WHERE hook_event_name = 'PreToolUse'
GROUP BY tool_name ORDER BY uses DESC;

-- Recent git commands (FTS search)
SELECT created_at, json_extract(payload, '$.tool_input.command')
FROM tool_events e
JOIN fts_bash_command f ON f.event_id = e.id
WHERE f.command MATCH '"git"' ORDER BY created_at DESC LIMIT 20;

-- Files read or written today
SELECT tool_name, json_extract(payload, '$.tool_input.file_path')
FROM tool_events
WHERE tool_name IN ('Read', 'Write', 'Edit')
  AND date(created_at) = date('now');
```

## Migration

If upgrading from an earlier schema version:

```
python tools/migration/migrate_to_v2.py <db>   # V1 → V2
python tools/migration/migrate_to_v3.py <db>   # V2 → V3
```

Both scripts create a timestamped backup before migrating.
