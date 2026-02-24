---
name: tool-usage
description: >
  Query the tool-monitor database to look up and analyze Claude tool usage.
  Use when asked about tool usage statistics, which tools have been used most, recent
  tool activity, bash commands run, files read or edited, grep patterns searched,
  session analysis, or any question about how Claude has been using its tools.
allowed-tools: Bash(sqlite3 *)
---

# Tool Usage

The tool-monitor database records every Claude Code tool invocation.

Database: `~/.claude/tool-monitor.sqlite`

## tool_events table

| Column            | Type     | Notes                                                                     |
|-------------------|----------|---------------------------------------------------------------------------|
| `id`              | INTEGER  | Primary key                                                               |
| `session_id`      | TEXT     | Groups events by conversation session                                     |
| `hook_event_name` | TEXT     | `PreToolUse`, `PostToolUse`, `PostToolUseFailure`, or `PermissionRequest` |
| `tool_name`       | TEXT     | e.g. `Bash`, `Read`, `Grep`, `Edit`, `Write`, `Glob`, `Task`              |
| `cwd`             | TEXT     | Working directory at time of invocation                                   |
| `transcript_path` | TEXT     | Path to the session transcript file                                       |
| `created_at`      | DATETIME | Timestamp                                                                 |
| `payload`         | TEXT     | Full JSON payload (all fields above, plus `tool_input` and more)          |

Tool-specific input fields live inside `payload` and are accessed with `json_extract`:

```sql
json_extract(payload, '$.tool_input.command')    -- Bash: the shell command
json_extract(payload, '$.tool_input.file_path')  -- Read/Write: file path
json_extract(payload, '$.tool_input.pattern')    -- Grep: search pattern
json_extract(payload, '$.tool_input.old_string') -- Edit: text being replaced
```

## Discovering fields for any tool

To see what `tool_input` fields are available for a specific tool, query `tool_schemas`:

```sql
SELECT json_extract(schema_json, '$.properties.tool_input.properties')
  FROM tool_schemas
 WHERE tool_name = 'Bash' AND hook_event = 'PreToolUse';
```

To list all tracked tools and their categories:

```sql
SELECT DISTINCT tool_name, category FROM tool_schemas WHERE hook_event = 'PreToolUse' ORDER BY tool_name;
```

## FTS5 wildcard and substring search

For substring and wildcard searches, FTS5 virtual tables are far faster than
`LIKE '%term%'` on large databases (typically 100-700x).

The database is self-describing: query `tool_schemas.indexed_fields` to discover
which tools have FTS coverage and which tables and columns to use:

```sql
SELECT tool_name,
       indexed_fields
  FROM tool_schemas
 WHERE hook_event = 'PreToolUse'
   AND indexed_fields != '[]'
 ORDER BY tool_name;
```

Each `indexed_fields` value is a JSON array of `{"path", "fts_table", "fts_column"}` objects.
Use `fts_table` and `fts_column` from those results to build the JOIN:

```sql
SELECT e.created_at, json_extract(e.payload, '$.tool_input.command')
  FROM tool_events e
  JOIN fts_bash_command f ON f.event_id = e.id
 WHERE f.command MATCH '"git commit"'
 ORDER BY e.created_at DESC;
```

Special characters (`.`, `-`, `/`) require phrase quoting: `MATCH '"CLAUDE.md"'` not `MATCH 'CLAUDE.md'`

Use `json_extract` with `=` for exact equality (hits expression indexes). Use FTS5 `MATCH`
for substring or wildcard search.

## Running queries

Before querying, verify the database exists:

```bash
test -f ~/.claude/tool-monitor.sqlite || echo "Database not found — is tool-monitor installed and running?"
```

```bash
sqlite3 ~/.claude/tool-monitor.sqlite "<SQL>"
```

Use `.mode column` and `.headers on` for readable tabular output:

```bash
sqlite3 -column -header ~/.claude/tool-monitor.sqlite "<SQL>"
```

## Two-step workflow for tool-specific queries

When the user asks about a specific tool's inputs (e.g. "which files have I read?",
"what bash commands containing git?"), first look up the field names, then query:

1. Look up fields: `SELECT json_extract(schema_json, '$.properties.tool_input.properties') FROM tool_schemas WHERE tool_name = 'Read' AND hook_event = 'PreToolUse';`
2. Query events: `SELECT json_extract(payload, '$.tool_input.file_path'), created_at FROM tool_events WHERE tool_name = 'Read' ORDER BY created_at DESC LIMIT 20;`

## Common patterns

Filter by text pattern:

```sql
WHERE json_extract(payload, '$.tool_input.command') LIKE '%git%'
```

Scope to a directory:

```sql
WHERE cwd LIKE '/path/to/my-project%'
```

Scope to current session:

```sql
WHERE session_id = (SELECT session_id FROM tool_events ORDER BY created_at DESC LIMIT 1)
```

Activity today:

```sql
WHERE date(created_at) = date('now')
```

Tool frequency summary:

```sql
SELECT tool_name, COUNT(*) AS uses
  FROM tool_events
 WHERE hook_event_name = 'PreToolUse'
 GROUP BY tool_name
 ORDER BY uses DESC;
```
