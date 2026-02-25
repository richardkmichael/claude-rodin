---
name: claude-transcripts
description: >
  Read and search Claude Code session transcripts (JSONL files). Use when asked
  to look at past conversations, find something said in a previous session, extract
  user questions from a session, recover content from before a context compaction,
  or search across sessions for a topic or keyword. Session files are in
  ~/.claude/projects/ under a URL-encoded project directory. Each session may also
  have a subdirectory with subagent transcripts and compaction summaries.
---

# Claude Transcripts

Session transcripts are JSONL files. Each line is a JSON object with at minimum
a `type` field. User messages and assistant messages are in `type=user` and
`type=assistant` entries with a `message` field following the Anthropic API
message format. Other types include `progress`, `queue-operation`,
`file-history-snapshot`, `system`, and `agent-name`.

## Session structure

Sessions live in `~/.claude/projects/<url-encoded-project-path>/`:

```
<session-id>.jsonl                 — main transcript
<session-id>/subagents/
  agent-<id>.jsonl                 — Task tool subagents (Explore, Plan, etc.)
  agent-acompact-<id>.jsonl        — compaction summaries (pre-compaction content)
```

Compaction summaries contain the assistant's analysis of the conversation before
the context was compacted. They are the primary source for recovering content
from sessions that ran out of context multiple times.

## Schema check first

Before using helper scripts on an unfamiliar file, run:

```
scripts/inspect-schema.sh <session.jsonl>
```

This shows: top-level keys, entry type distribution, and user content formats.
If the schema has changed (different top-level keys, unexpected content types),
adapt the jq queries accordingly. The helper scripts assume `.type`, `.message.role`,
and `.message.content` — verify these exist before relying on the other scripts.

## Extracting user messages

List all human-typed messages with their 0-based indices:

```
scripts/user-messages.sh <session.jsonl>
```

Output: `[INDEX] first 200 chars of message`. Filters out tool results, teammate
messages, compaction summaries, slash-command entries, and interrupts.

## Fetching full entry text

After identifying entries of interest from `user-messages.sh` or `search-sessions.sh`,
fetch the full text using the 0-based index:

```
scripts/get-entry.sh <session.jsonl> <index> [index ...]
```

Works on any entry type (user, assistant, system). Shows type, role, and full
content. For non-text content (tool results, tool use calls), shows a summary.

## Searching across sessions

Search for a keyword or pattern across one or more session files:

```
scripts/search-sessions.sh <pattern> <session.jsonl> [session.jsonl ...]
```

Pattern is a jq regex (case-insensitive by default). Searches all entry content,
not just user messages. Outputs matching entries with 0-based index and first
300 chars.

To search all sessions in a project:

```
scripts/search-sessions.sh "keyword" ~/.claude/projects/<dir>/*.jsonl
```

## Pre-compaction content

Compaction only affects the model's active context — all original entries remain
in the main session JSONL at their original indices. The helper scripts scan the
full file, so pre-compaction entries are automatically included in search and
listing results with no special handling needed.

What compaction adds to the JSONL is a `user` entry containing "This session is
being continued from a previous conversation..." — this is the summary the model
sees going forward. `user-messages.sh` filters this out, but the original entries
before it are still present and searchable.

The `agent-acompact-*.jsonl` files in `<session-id>/subagents/` contain the
compaction agent's own transcript — useful if you want to read the summary the
model was given (rather than the original content). To read one:

```
scripts/search-sessions.sh "." <session-id>/subagents/agent-acompact-<id>.jsonl
```

## Session structure and chain info

When asked about what happened in a session, or when you need to find content
that spans multiple sessions (e.g., a plan was made in one session and
implemented after a clear-context transition in another), start here:

```
scripts/session-info.sh <session.jsonl>
```

Outputs JSON with:
- `entry_count`, `date_range` — session size and timespan
- `compactions` — array of compaction boundaries, each with `index` (the JSONL
  line), `entries_after` (work done in that segment), and `summary_file` (the
  `agent-acompact-*.jsonl` subagent path, if found)
- `clear_context_end` — index of the ExitPlanMode tool_use that terminated the
  session via "clear context and auto-accept edits" (null if session ended
  normally)
- `parent` — nested info for the parent session if this session was created by
  a clear-context transition (detected via "read the full transcript at:" in
  early entries)
- `children` — nested info for sessions spawned from this one (detected by
  scanning sibling JSONL files for back-references)

This is useful for orienting before deeper investigation: knowing where the
compaction boundaries are tells you which segments to search, and knowing the
session chain lets you follow a conversation that was split across files by
a clear-context transition.

Two mechanisms interrupt a session's context:
- `/compact` creates a boundary within the same JSONL file.  All original
  entries remain at their original indices; only the model's active context
  is replaced with a summary.
- "Clear context" (ExitPlanMode) creates a new JSONL file.  The old session
  gets a synthetic interrupt; the new session's entry [1] contains the plan
  text and a pointer to the old session's transcript path.

## Index convention

All scripts use 0-based indices. The index shown by `user-messages.sh` and
`search-sessions.sh` is the correct index to pass to `get-entry.sh`.
