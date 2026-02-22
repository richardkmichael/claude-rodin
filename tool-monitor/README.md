# Tool Monitor

This project implements two Claude Code hooks `PreToolUse` and `PostToolUse` to store hook payloads
in SQLite for future analysis of Claude's tool usage.

The hooks implemented do not *alter* tool calls, they simply return exit code 0 (success) to be
transparent and only capture the hook payload.  In this hook usage, `stdout` is shown to the user in
Claude Code "transcript mode" (CTRL-R).

## Quick Start

### New Installations

Install to `~/bin/claude-tool-monitor`:

```bash
cargo install --path . --root ~
```

Run `claude` and configure `/hooks`, or directly edit `.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "claude-tool-monitor ~/.claude/tool-monitor.sqlite"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "claude-tool-monitor ~/.claude/tool-monitor.sqlite"
          }
        ]
      }
    ]
  }
}
```

### Update Installations
```bash
# Migrate the schema (creates automatic backup)
python tools/migration/migrate_to_v2.py your_existing_monitor.db

# Validate schemas work correctly
python tools/validation/validate_against_schemas.py your_existing_monitor.db
```

## Features

- **Schema V2**: Minimal, future-proof database schema with JSON Schema validation
- **Fast Rust binary**: Processes tool events with excellent performance
- **SQLite storage**: WAL mode for concurrent access, generated columns for stable fields
- **JSON Schema validation**: Industry-standard validation using `uvx check-jsonschema`
- **Migration tools**: Safe migration from V1 to V2 with automatic backups


## Database Schema

### Schema V2 Design
- **`schema_info`**: Database schema version and metadata
- **`tool_events`**: Minimal table with stable hook fields + full JSON payload
- **`tool_schemas`**: 28 complete JSON Schema documents (one for each tool/hook combination)
- **`schema_versions`**: Tool schema evolution tracking

### Generated Columns (Stable Fields Only)
- `hook_event_name` - PreToolUse/PostToolUse
- `tool_name` - Name of the tool (Bash, Edit, etc.)
- `cwd` - Current working directory
- `transcript_path` - Path to session transcript

## JSON Schema Files

The `schemas/` directory contains 28 validated JSON Schema files:
- **Naming**: `{toolname}-{hook_event}.json` (e.g., `bash-pre_tool_use.json`)
- **Validation**: All schemas tested against real Claude Code data
- **Coverage**: 14 tools × 2 hook events (PreToolUse + PostToolUse)

## Tools

### `tools/migration/migrate_to_v2.py`
Migrates existing V1 databases to V2 schema. Creates backups automatically.

```bash
python tools/migration/migrate_to_v2.py monitor.db
```

### `tools/validation/validate_against_schemas.py`
Validates database payloads against JSON schemas using `uvx check-jsonschema`.

```bash
# Validate all tools
python tools/validation/validate_against_schemas.py monitor.db

# Validate specific tool
python tools/validation/validate_against_schemas.py monitor.db Bash PreToolUse
```

### `tools/validation/derive_schemas_from_payloads.py`
Analyzes actual payloads to derive JSON schema structures. Useful when Claude Code tools change or for documenting new tools.

```bash
# Analyze all tools and show derived structures
python tools/validation/derive_schemas_from_payloads.py monitor.db

# Analyze specific tool
python tools/validation/derive_schemas_from_payloads.py monitor.db --tool Bash

# Compare derived schemas with existing schema files
python tools/validation/derive_schemas_from_payloads.py monitor.db --compare
```

### `tools/validation/check_schema_version.py`
Checks database schema version and compatibility with current tools.

```bash
# Check schema version and compatibility
python tools/validation/check_schema_version.py monitor.db
```

## Building

```bash
# Development
cargo build

# Optimized release
cargo build --release

# Run tests
cargo test
```

## Example Queries

```sql
-- Tool usage statistics
SELECT tool_name, COUNT(*) 
FROM tool_events 
GROUP BY tool_name 
ORDER BY COUNT(*) DESC;

-- Extract bash commands (runtime JSON extraction)
SELECT json_extract(payload, '$.tool_input.command') as command
FROM tool_events 
WHERE tool_name = 'Bash';

-- Available schemas
SELECT tool_name, hook_event, file_name, category
FROM tool_schemas 
ORDER BY category, tool_name;
```

## Dependencies

- **Runtime**: None (SQLite bundled)
- **Validation**: `uvx` (for JSON Schema validation)
- **Migration**: Python 3.7+
