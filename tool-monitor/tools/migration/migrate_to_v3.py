#!/usr/bin/env python
"""
Migrate tool-monitor database from Schema V2 to Schema V3.

V3 adds:
  - Expression indexes on tool_input fields for fast equality lookups
  - FTS5 trigram virtual tables for fast wildcard/substring search
  - schema_info.contract_fields: documents fields present in all hook payloads
  - tool_schemas.common_fields: repopulated with per-tool analysis fields
  - PostToolUseFailure and PermissionRequest schemas derived into tool_schemas
  - tool_schemas.file_name generated column dropped (was broken for new hook events)
  - Schema version bumped to 3.0.0

Usage:
    python tools/migration/migrate_to_v3.py /path/to/database.db
"""

import copy
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


# Fields present in all hook payloads (the stable contract).
# These match the generated columns extracted in tool_events.
CONTRACT_FIELDS = ["session_id", "hook_event_name", "tool_name", "cwd", "transcript_path"]

# Per-tool analysis fields indexed by FTS5 or expression indexes.
# Keys use tool_schemas.tool_name capitalisation (derived from filenames, not payload).
TOOL_COMMON_FIELDS = {
    "Bash":      ["$.tool_input.command"],
    "Read":      ["$.tool_input.file_path"],
    "Write":     ["$.tool_input.file_path"],
    "Edit":      ["$.tool_input.file_path"],
    "Grep":      ["$.tool_input.pattern"],
    "Glob":      ["$.tool_input.pattern"],
    "Webfetch":  ["$.tool_input.url"],
    "Websearch": ["$.tool_input.query"],
}


def backup_database(db_path: str) -> str:
    """Create a timestamped backup before migration."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{db_path}.v2_backup_{timestamp}"
    print(f"Creating backup: {backup_path}")
    shutil.copy2(db_path, backup_path)
    return backup_path


def detect_schema_version(db_path: str) -> Optional[str]:
    """Return schema version string, or None if schema_info is absent."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='schema_info'
        """)
        if cursor.fetchone():
            cursor.execute("SELECT value FROM schema_info WHERE key='version'")
            row = cursor.fetchone()
            conn.close()
            return row[0] if row else "2.0.0"
        conn.close()
        return None
    except sqlite3.Error as e:
        print(f"Error detecting schema: {e}")
        return None


# ---------------------------------------------------------------------------
# Step 1: Expression indexes
# ---------------------------------------------------------------------------

def add_expression_indexes(cursor: sqlite3.Cursor):
    """Add partial expression indexes for fast equality lookups on tool_input fields."""
    indexes = [
        ("idx_bash_command",
         "tool_events(json_extract(payload, '$.tool_input.command'))",
         "tool_name = 'Bash'"),
        ("idx_file_path",
         "tool_events(json_extract(payload, '$.tool_input.file_path'))",
         "tool_name IN ('Read', 'Write', 'Edit')"),
        ("idx_grep_pattern",
         "tool_events(json_extract(payload, '$.tool_input.pattern'))",
         "tool_name = 'Grep'"),
        ("idx_glob_pattern",
         "tool_events(json_extract(payload, '$.tool_input.pattern'))",
         "tool_name = 'Glob'"),
    ]
    for name, on_clause, where_clause in indexes:
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS {name}
            ON {on_clause}
            WHERE {where_clause}
        """)
    print(f"   Created/verified {len(indexes)} expression indexes")


# ---------------------------------------------------------------------------
# Step 2: FTS5 tables, backfill, triggers
# ---------------------------------------------------------------------------

# (table_name, fts_column, json_path, filter_condition_using_tool_name)
# filter_condition must use 'tool_name' (not 'NEW.tool_name') — triggers replace below.
_FTS_TABLES = [
    ("fts_bash_command",  "command",    "$.tool_input.command",    "tool_name = 'Bash'"),
    ("fts_file_path",     "file_path",  "$.tool_input.file_path",  "tool_name IN ('Read', 'Write', 'Edit')"),
    ("fts_grep_pattern",  "pattern",    "$.tool_input.pattern",    "tool_name = 'Grep'"),
    ("fts_glob_pattern",  "pattern",    "$.tool_input.pattern",    "tool_name = 'Glob'"),
    ("fts_url",           "url",        "$.tool_input.url",        "tool_name = 'WebFetch'"),
    ("fts_search_query",  "query",      "$.tool_input.query",      "tool_name = 'WebSearch'"),
]


def create_fts_tables_triggers_and_backfill(cursor: sqlite3.Cursor):
    """Create FTS5 virtual tables, backfill from existing events, add AFTER INSERT triggers."""
    for table_name, field_col, json_path, filter_cond in _FTS_TABLES:
        cursor.execute(f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS {table_name} USING fts5(
                {field_col},
                event_id UNINDEXED,
                tokenize='trigram'
            )
        """)

        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        if cursor.fetchone()[0] == 0:
            cursor.execute(f"""
                INSERT INTO {table_name}({field_col}, event_id)
                SELECT json_extract(payload, '{json_path}'), id
                  FROM tool_events
                 WHERE {filter_cond}
                   AND json_extract(payload, '{json_path}') IS NOT NULL
            """)
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cursor.fetchone()[0]
            print(f"   {table_name}: backfilled {count} rows")
        else:
            print(f"   {table_name}: already populated, skipping backfill")

        when_clause = filter_cond.replace("tool_name", "NEW.tool_name")
        cursor.execute(f"""
            CREATE TRIGGER IF NOT EXISTS trg_{table_name}
            AFTER INSERT ON tool_events
            WHEN {when_clause}
            BEGIN
                INSERT INTO {table_name}({field_col}, event_id)
                VALUES (json_extract(NEW.payload, '{json_path}'), NEW.id);
            END
        """)

    print(f"   Created/verified {len(_FTS_TABLES)} FTS5 tables and triggers")


# ---------------------------------------------------------------------------
# Step 3: schema_info.contract_fields
# ---------------------------------------------------------------------------

def add_contract_fields(cursor: sqlite3.Cursor):
    """Insert contract_fields entry into schema_info."""
    cursor.execute("""
        INSERT OR IGNORE INTO schema_info (key, value)
        VALUES ('contract_fields', ?)
    """, (json.dumps(CONTRACT_FIELDS),))
    print("   Added schema_info.contract_fields")


# ---------------------------------------------------------------------------
# Step 4: tool_schemas.common_fields
# ---------------------------------------------------------------------------

def update_common_fields(cursor: sqlite3.Cursor):
    """Replace contract-field lists in common_fields with per-tool analysis fields."""
    cursor.execute("SELECT DISTINCT tool_name FROM tool_schemas")
    all_tools = [row[0] for row in cursor.fetchall()]

    updated = 0
    for tool_name in all_tools:
        fields = TOOL_COMMON_FIELDS.get(tool_name, [])
        cursor.execute("""
            UPDATE tool_schemas SET common_fields = ? WHERE tool_name = ?
        """, (json.dumps(fields), tool_name))
        updated += cursor.rowcount

    print(f"   Updated common_fields for {updated} tool_schemas rows")


# ---------------------------------------------------------------------------
# Step 5: Drop file_name generated column (table recreate)
# ---------------------------------------------------------------------------

def recreate_tool_schemas_without_file_name(cursor: sqlite3.Cursor):
    """Recreate tool_schemas without the broken file_name generated column."""
    cursor.execute("PRAGMA table_info(tool_schemas)")
    columns = [row[1] for row in cursor.fetchall()]

    if "file_name" not in columns:
        print("   file_name column already absent, skipping recreate")
        return

    cursor.execute("""
        CREATE TABLE tool_schemas_v3 (
            tool_name TEXT NOT NULL,
            hook_event TEXT NOT NULL,
            schema_version TEXT NOT NULL,
            schema_json TEXT NOT NULL,
            category TEXT,
            description TEXT,
            common_fields TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (tool_name, hook_event, schema_version)
        )
    """)

    cursor.execute("""
        INSERT INTO tool_schemas_v3
            (tool_name, hook_event, schema_version, schema_json,
             category, description, common_fields, created_at)
        SELECT tool_name, hook_event, schema_version, schema_json,
               category, description, common_fields, created_at
          FROM tool_schemas
    """)

    cursor.execute("DROP TABLE tool_schemas")
    cursor.execute("ALTER TABLE tool_schemas_v3 RENAME TO tool_schemas")

    print("   Recreated tool_schemas without file_name column")


# ---------------------------------------------------------------------------
# Step 6: Seed PostToolUseFailure and PermissionRequest schemas
# ---------------------------------------------------------------------------

_PERMISSION_SUGGESTIONS_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "type": {"type": "string"},
            "rules": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "toolName": {"type": "string"},
                        "ruleContent": {"type": "string"}
                    }
                }
            },
            "behavior": {"type": "string"},
            "destination": {"type": "string"}
        }
    }
}


def _derive_post_tool_use_failure_schema(pre_schema: dict, tool_name: str) -> dict:
    schema = copy.deepcopy(pre_schema)
    schema["title"] = f"{tool_name} PostToolUseFailure Schema"
    schema["description"] = f"JSON Schema for {tool_name} tool PostToolUseFailure events"
    schema["properties"]["hook_event_name"] = {"const": "PostToolUseFailure"}
    schema["properties"]["tool_use_id"] = {"type": "string"}
    schema["properties"]["error"] = {"type": "string"}
    schema["properties"]["is_interrupt"] = {"type": "boolean"}
    required = list(schema.get("required", []))
    if "error" not in required:
        required.append("error")
    schema["required"] = required
    return schema


def _derive_permission_request_schema(pre_schema: dict, tool_name: str) -> dict:
    schema = copy.deepcopy(pre_schema)
    schema["title"] = f"{tool_name} PermissionRequest Schema"
    schema["description"] = f"JSON Schema for {tool_name} tool PermissionRequest events"
    schema["properties"]["hook_event_name"] = {"const": "PermissionRequest"}
    schema["properties"]["permission_suggestions"] = _PERMISSION_SUGGESTIONS_SCHEMA
    # permission_suggestions is optional; not added to required
    return schema


def seed_new_hook_schemas(cursor: sqlite3.Cursor):
    """Derive and insert PostToolUseFailure/PermissionRequest schemas from PreToolUse schemas."""
    migration_date = datetime.now().date().isoformat()
    schema_version = "1.0.0"

    cursor.execute("""
        SELECT tool_name, schema_json, category, common_fields
          FROM tool_schemas
         WHERE hook_event = 'PreToolUse'
    """)
    source_rows = cursor.fetchall()

    seeded = 0
    for tool_name, schema_json_str, category, common_fields in source_rows:
        try:
            pre_schema = json.loads(schema_json_str)
        except json.JSONDecodeError:
            print(f"   Warning: failed to parse schema for {tool_name}, skipping")
            continue

        for hook_event, derive_fn in [
            ("PostToolUseFailure", _derive_post_tool_use_failure_schema),
            ("PermissionRequest",  _derive_permission_request_schema),
        ]:
            new_schema = derive_fn(pre_schema, tool_name)
            new_schema_json = json.dumps(new_schema, indent=2)
            description = new_schema.get("description", f"JSON Schema for {tool_name} {hook_event}")

            cursor.execute("""
                INSERT OR IGNORE INTO tool_schemas
                    (tool_name, hook_event, schema_version, schema_json,
                     category, description, common_fields)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (tool_name, hook_event, schema_version, new_schema_json,
                  category, description, common_fields))

            if cursor.rowcount > 0:
                cursor.execute("""
                    INSERT OR IGNORE INTO schema_versions
                        (tool_name, hook_event, version, active_from, notes)
                    VALUES (?, ?, ?, ?, ?)
                """, (tool_name, hook_event, schema_version, migration_date,
                      "Derived from PreToolUse schema during V3 migration"))
                seeded += 1

    print(f"   Seeded {seeded} new hook schemas (PostToolUseFailure + PermissionRequest)")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def migrate_to_v3(db_path: str) -> bool:
    """Migrate database from V2 to V3. Returns True on success."""
    current_version = detect_schema_version(db_path)

    if current_version is None:
        print("❌ No schema_info table found. Database must be at V2 before migrating to V3.")
        print(f"   Run: python tools/migration/migrate_to_v2.py {db_path}")
        return False

    if current_version.startswith("3."):
        print(f"✅ Database is already V3 (version {current_version})")
        return True

    if not current_version.startswith("2."):
        print(f"❌ Expected V2 schema, found version: {current_version}")
        if current_version == "1.x":
            print(f"   Run: python tools/migration/migrate_to_v2.py {db_path}")
        return False

    print(f"Migrating from V2 ({current_version}) to V3...\n")

    backup_path = backup_database(db_path)

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("BEGIN TRANSACTION")

        print("Step 1: Expression indexes...")
        add_expression_indexes(cursor)

        print("\nStep 2: FTS5 tables, backfill, and triggers...")
        create_fts_tables_triggers_and_backfill(cursor)

        print("\nStep 3: schema_info.contract_fields...")
        add_contract_fields(cursor)

        print("\nStep 4: tool_schemas.common_fields (per-tool analysis fields)...")
        update_common_fields(cursor)

        print("\nStep 5: Drop file_name generated column (table recreate)...")
        recreate_tool_schemas_without_file_name(cursor)

        print("\nStep 6: Seed PostToolUseFailure and PermissionRequest schemas...")
        seed_new_hook_schemas(cursor)

        print("\nStep 7: Bump schema version to 3.0.0...")
        cursor.execute("""
            UPDATE schema_info
               SET value = '3.0.0', updated_at = CURRENT_TIMESTAMP
             WHERE key = 'version'
        """)
        cursor.execute("""
            UPDATE schema_info
               SET value = 'V3: FTS5 trigram indexes, expression indexes, expanded hook coverage'
             WHERE key = 'description'
        """)
        cursor.execute("""
            INSERT OR REPLACE INTO schema_info (key, value)
            VALUES ('migrated_from', ?)
        """, (current_version,))
        cursor.execute("""
            INSERT OR REPLACE INTO schema_info (key, value)
            VALUES ('migration_date', ?)
        """, (datetime.now().isoformat(),))

        # Verify
        cursor.execute("SELECT COUNT(*) FROM tool_events")
        event_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM tool_schemas")
        schema_count = cursor.fetchone()[0]

        cursor.execute("COMMIT")
        conn.close()

        print(f"\n✅ Migration completed successfully!")
        print(f"   Events in database: {event_count}")
        print(f"   Schemas in tool_schemas: {schema_count}")
        print(f"   Backup created: {backup_path}")
        print(f"   Schema version: 3.0.0")
        return True

    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        print("Rolling back...")
        try:
            cursor.execute("ROLLBACK")
            conn.close()
        except Exception:
            pass
        print(f"Restoring from backup: {backup_path}")
        shutil.copy2(backup_path, db_path)
        return False


def main():
    if len(sys.argv) < 2:
        print("Usage: python migrate_to_v3.py <database.db>")
        print()
        print("Migrates a tool-monitor database from V2 to V3 schema.")
        print("A backup is automatically created before migration.")
        sys.exit(1)

    db_path = sys.argv[1]

    if not os.path.exists(db_path):
        print(f"❌ Database file not found: {db_path}")
        sys.exit(1)

    print(f"=== MIGRATING TO SCHEMA V3: {db_path} ===\n")
    success = migrate_to_v3(db_path)

    if success:
        print()
        print("🎉 Migration complete!")
        print(f"   python tools/validation/check_schema_version.py {db_path}")
    else:
        print()
        print("💥 Migration failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
