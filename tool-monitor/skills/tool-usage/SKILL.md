---
name: tool-usage
description: Query the tool-monitor database to look up and analyze Claude tool usage.
  Use when asked about tool usage statistics, which tools have been used most, recent
  tool activity, bash commands run, files read or edited, grep patterns searched,
  session analysis, or any question about how Claude has been using its tools.
allowed-tools: Bash(sqlite3 *)
---

# Tool Usage

The tool-monitor database records every Claude Code tool invocation.

Database: `~/.claude/tool-monitor.sqlite`

## tool_events table

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER | Primary key |
| `session_id` | TEXT | Groups events by conversation session |
| `hook_event_name` | TEXT | `PreToolUse` or `PostToolUse` |
| `tool_name` | TEXT | e.g. `Bash`, `Read`, `Grep`, `Edit`, `Write`, `Glob`, `Task` |
| `cwd` | TEXT | Working directory at time of invocation |
| `transcript_path` | TEXT | Path to the session transcript file |
| `created_at` | DATETIME | Timestamp |
| `payload` | TEXT | Full JSON payload (all fields above, plus `tool_input` and more) |

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
