---
name: history
description: >
  Read and search Claude Code session transcripts (JSONL files). Use when asked
  to look at past conversations, find something said in a previous session, extract
  user questions from a session, recover content from before a context compaction,
  or search across sessions for a topic or keyword.
references:
  - references/claude-code-session-transcript.schema.json
---

# Session History

## Invocation

- `/history [query]` — search pre-compaction content in the current session,
  plus any parent/child sessions linked by clear-context transitions. This
  searches content that is no longer in the model's active context.
- `/history all [query]` — search every session in the current project directory.

## Finding the current session file

The current session's JSONL file path is available as `transcript_path` in the
hook payload, or can be found as the most recently modified `.jsonl` file in the
project directory matching the current session ID.

Session transcripts live in `~/.claude/projects/<url-encoded-project-path>/`:

```
<session-id>.jsonl                 — main transcript
<session-id>/subagents/
  agent-<id>.jsonl                 — Task tool subagents (Explore, Plan, etc.)
  agent-acompact-<id>.jsonl        — compaction summaries
```

## Determining search scope

### `/history [query]` (current session)

The goal is to search content that has been compacted away — content the model
can no longer see. Post-compaction content is already in the active context,
so searching it would be redundant.

1. Find the current session's JSONL file.
2. Find the last compaction boundary using `scope.py`:
   ```
   BOUNDARY=$(python3 scripts/scope.py <session.jsonl>)
   ```
   This prints the 0-based line index of the last `compact_boundary` record,
   or exits with code 1 if no boundary exists.
3. If a boundary exists: search only lines before that index using `--before`:
   ```
   python3 scripts/search.py --before $BOUNDARY "keyword" <session.jsonl>
   ```
   These are the entries that were summarized away from the model's context.
4. If no boundary exists: the entire conversation is still in context.
   Fall back to the clear-context parent chain — run
   `scripts/session-info.sh <session.jsonl>` and follow `parent.file` paths
   to find prior sessions whose content is no longer visible.
5. Also follow the clear-context parent chain if it exists — parent sessions
   are always out of context. Collect `parent.file` paths from session-info
   output and search those files entirely.

### `/history all [query]`

Search every session in the project directory:

```
python3 scripts/search.py "query" ~/.claude/projects/<dir>/*.jsonl
```

## Schema reference

A JSON Schema for the JSONL format is included as a reference file
(`references/claude-code-session-transcript.schema.json`). It documents all
record types, their fields, and enum values. Consult it to understand what
fields are available before constructing searches.

If a file contains records that don't match the schema (e.g. a newer Claude
Code version added fields), run the inspector to see what changed:

```
scripts/inspect-schema.sh <session.jsonl>
```

This shows: top-level keys, entry type distribution, and user content formats.

## Interpreting the query

The user's query may be a simple keyword, or it may reference specific record
types or schema fields. Parse the query to decide the search strategy:

- Plain text query (e.g. "find where I mentioned caching"):
  ```
  python3 scripts/search.py "caching" <session.jsonl>
  ```
  Searches across all record types: message content, tool inputs, attachments,
  and system content.

- Record type filter (e.g. "my messages about X", "what did I ask about X"):
  ```
  python3 scripts/search.py --type user "caching" <session.jsonl>
  ```

- Tool-specific query (e.g. "Bash commands that ran git", "which tools were used"):
  ```
  # Find all Bash tool invocations containing "git"
  python3 scripts/search.py --tool Bash "git" <session.jsonl>

  # List all tools the assistant invoked (with frequency)
  python3 scripts/search.py --tool '*' --field _tool_names <session.jsonl>
  ```

- Attachment/system subtype query (e.g. "find the plan_mode_exit attachment"):
  ```
  python3 scripts/search.py --subtype plan_mode_exit <session.jsonl>
  python3 scripts/search.py --subtype api_error <session.jsonl>
  ```

- Token usage query (e.g. "how many tokens were used"):
  ```
  python3 scripts/search.py --type assistant --field message.usage <session.jsonl>
  ```

- Counting (e.g. "how many user messages"):
  ```
  python3 scripts/search.py --type user --count <session.jsonl>
  ```

- Full record inspection (when summaries aren't enough):
  ```
  python3 scripts/search.py --type user --full "keyword" <session.jsonl>
  ```

When the user's intent is ambiguous, default to searching all record types
with a text pattern. When they reference specific schema concepts (record types,
field names, attachment subtypes), use the appropriate filters.

## Helper scripts

### Structured search (Python)

The primary search tool. Supports structured filters and multiple output modes:

```
python3 scripts/search.py [OPTIONS] [PATTERN] FILE [FILE...]
```

Filters:
- `--type TYPE` — record type: user, assistant, system, attachment, progress
- `--subtype SUB` — system subtype or attachment.type
- `--tool TOOL` — tool name (matches tool_use blocks), `'*'` for any tool
- `--before N` — only lines with index < N (use with scope.py)
- `--after N` — only lines with index > N

Output:
- (default) — one-line summary per match: `[INDEX] type role: first 300 chars`
- `--field PATH` — extract a dotted field path (e.g. `message.usage`, `_tool_names`)
- `--full` — full JSON record
- `--count` — just the count of matching records

PATTERN is a regex (case-insensitive). If omitted, all records matching the
filters are returned.

### Compaction boundary (Python)

Find where the model's active context begins:

```
python3 scripts/scope.py <session.jsonl>
```

Prints the 0-based index of the last `compact_boundary` record. Exits with
code 1 if no boundary exists (entire session is in context).

### Extracting user messages

List all human-typed messages with their 0-based indices:

```
scripts/user-messages.sh <session.jsonl>
```

Output: `[INDEX] first 200 chars of message`. Filters out tool results, teammate
messages, compaction summaries, slash-command entries, and interrupts.

### Fetching full entry text

After identifying entries of interest, fetch the full text using the 0-based index:

```
scripts/get-entry.sh <session.jsonl> <index> [index ...]
```

Works on any entry type (user, assistant, system). Shows type, role, and full
content. For non-text content (tool results, tool use calls), shows a summary.

### Session chain info

When asked about what happened in a session, or when you need to find content
that spans multiple sessions:

```
scripts/session-info.sh <session.jsonl>
```

Outputs JSON with:
- `entry_count`, `date_range` — session size and timespan
- `compactions` — array of compaction boundaries with index, entries_after,
  and summary_file
- `clear_context_end` — index where session ended via clear-context
- `parent` — info for the parent session (clear-context chain)
- `children` — info for sessions spawned from this one

## How compaction works in the JSONL

Compaction only affects the model's active context — all original entries remain
in the main session JSONL at their original indices. The JSONL file contains
the full history regardless of how many times the context was compacted.

When compaction occurs, two records are added:
1. A `system` record with `"subtype": "compact_boundary"` — this marks the
   boundary. Everything before it was summarized away from the model's context.
2. A `user` record with `isCompactSummary: true` containing "This session is
   being continued from a previous conversation..." — this is the summary the
   model sees going forward.

If a session was compacted multiple times, there are multiple boundaries. The
last one marks where the current active context begins. Everything before it
is the "lost" history that `/history` should search.

The `agent-acompact-*.jsonl` files in `<session-id>/subagents/` contain the
compaction agent's own transcript — useful for reading the summary the model
was given (rather than the original content).

## Context interruption mechanisms

Two mechanisms interrupt a session's context:
- `/compact` creates a boundary within the same JSONL file. All original
  entries remain at their original indices; only the model's active context
  is replaced with a summary.
- "Clear context" (ExitPlanMode) creates a new JSONL file. The old session
  gets a synthetic interrupt; the new session's early entries contain "read
  the full transcript at: <path>" pointing to the parent session.

## Index convention

All scripts use 0-based indices. The index shown by `search.py` and
`user-messages.sh` is the correct index to pass to `get-entry.sh`.
