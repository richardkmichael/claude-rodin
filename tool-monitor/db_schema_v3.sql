-- Tool Monitor Database Schema V3
-- V3 additions over V2:
--   - Expression indexes on tool_input fields (fast equality lookups)
--   - FTS5 trigram virtual tables + triggers (fast wildcard/substring search)
--   - schema_info.contract_fields documents fields present in all hook payloads
--   - tool_schemas.common_fields stores per-tool analysis fields (not contract fields)
--   - tool_schemas.file_name generated column removed (was broken for new hook events)
--   - PostToolUseFailure and PermissionRequest hook coverage

-- Database schema version tracking
CREATE TABLE schema_info (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO schema_info (key, value) VALUES ('version', '3.0.0');
INSERT INTO schema_info (key, value) VALUES ('description', 'V3: FTS5 trigram indexes, expression indexes, expanded hook coverage');
INSERT INTO schema_info (key, value) VALUES (
    'contract_fields',
    '["session_id","hook_event_name","tool_name","cwd","transcript_path"]'
);

-- Main events table: only extract stable hook contract fields as generated columns
CREATE TABLE tool_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    payload TEXT NOT NULL,

    -- Stable hook contract fields (guaranteed by Claude Code across all hook events)
    hook_event_name TEXT GENERATED ALWAYS AS (json_extract(payload, '$.hook_event_name')) STORED,
    tool_name TEXT GENERATED ALWAYS AS (json_extract(payload, '$.tool_name')) STORED,
    cwd TEXT GENERATED ALWAYS AS (json_extract(payload, '$.cwd')) STORED,
    transcript_path TEXT GENERATED ALWAYS AS (json_extract(payload, '$.transcript_path')) STORED,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Basic indexes
CREATE INDEX idx_session_id ON tool_events(session_id);
CREATE INDEX idx_tool_name ON tool_events(tool_name);
CREATE INDEX idx_hook_event_name ON tool_events(hook_event_name);
CREATE INDEX idx_created_at ON tool_events(created_at);
CREATE INDEX idx_cwd ON tool_events(cwd);

-- Expression indexes: fast equality lookups on tool_input fields
-- These complement FTS5: use for exact matches, FTS5 for wildcard/substring.
CREATE INDEX idx_bash_command
    ON tool_events(json_extract(payload, '$.tool_input.command'))
    WHERE tool_name = 'Bash';

CREATE INDEX idx_file_path
    ON tool_events(json_extract(payload, '$.tool_input.file_path'))
    WHERE tool_name IN ('Read', 'Write', 'Edit');

CREATE INDEX idx_grep_pattern
    ON tool_events(json_extract(payload, '$.tool_input.pattern'))
    WHERE tool_name = 'Grep';

CREATE INDEX idx_glob_pattern
    ON tool_events(json_extract(payload, '$.tool_input.pattern'))
    WHERE tool_name = 'Glob';

-- Tool schema registry (no file_name generated column — naming convention in schema_info)
CREATE TABLE tool_schemas (
    tool_name TEXT NOT NULL,
    hook_event TEXT NOT NULL,   -- 'PreToolUse', 'PostToolUse', 'PostToolUseFailure', or 'PermissionRequest'
    schema_version TEXT NOT NULL,
    schema_json TEXT NOT NULL,  -- Complete JSON Schema document
    category TEXT,              -- File, Search, System, Web, Workflow
    description TEXT,
    common_fields TEXT,         -- JSON array of per-tool analysis field paths (e.g. ["$.tool_input.command"])

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tool_name, hook_event, schema_version)
);

-- Track which schema version was active at what time
CREATE TABLE schema_versions (
    tool_name TEXT NOT NULL,
    hook_event TEXT NOT NULL,
    version TEXT NOT NULL,
    active_from DATE NOT NULL,
    active_to DATE,
    notes TEXT,
    PRIMARY KEY (tool_name, hook_event, version),
    FOREIGN KEY (tool_name, hook_event, version) REFERENCES tool_schemas(tool_name, hook_event, schema_version)
);

CREATE INDEX idx_schema_active ON schema_versions(tool_name, hook_event, active_from, active_to);

-- FTS5 trigram tables: fast wildcard/substring search over tool_input fields.
-- Query pattern: JOIN fts_bash_command ON fts_bash_command.event_id = tool_events.id
--                WHERE fts_bash_command.command MATCH '"search-term"'
-- Note: special characters (., /, -) require phrase quoting: MATCH '"term"'

CREATE VIRTUAL TABLE fts_bash_command USING fts5(
    command,
    event_id UNINDEXED,
    tokenize='trigram'
);

CREATE VIRTUAL TABLE fts_file_path USING fts5(
    file_path,
    event_id UNINDEXED,
    tokenize='trigram'
);

CREATE VIRTUAL TABLE fts_grep_pattern USING fts5(
    pattern,
    event_id UNINDEXED,
    tokenize='trigram'
);

CREATE VIRTUAL TABLE fts_glob_pattern USING fts5(
    pattern,
    event_id UNINDEXED,
    tokenize='trigram'
);

CREATE VIRTUAL TABLE fts_url USING fts5(
    url,
    event_id UNINDEXED,
    tokenize='trigram'
);

CREATE VIRTUAL TABLE fts_search_query USING fts5(
    query,
    event_id UNINDEXED,
    tokenize='trigram'
);

-- AFTER INSERT triggers: keep FTS5 tables in sync with tool_events

CREATE TRIGGER trg_fts_bash_command
AFTER INSERT ON tool_events
WHEN NEW.tool_name = 'Bash'
BEGIN
    INSERT INTO fts_bash_command(command, event_id)
    VALUES (json_extract(NEW.payload, '$.tool_input.command'), NEW.id);
END;

CREATE TRIGGER trg_fts_file_path
AFTER INSERT ON tool_events
WHEN NEW.tool_name IN ('Read', 'Write', 'Edit')
BEGIN
    INSERT INTO fts_file_path(file_path, event_id)
    VALUES (json_extract(NEW.payload, '$.tool_input.file_path'), NEW.id);
END;

CREATE TRIGGER trg_fts_grep_pattern
AFTER INSERT ON tool_events
WHEN NEW.tool_name = 'Grep'
BEGIN
    INSERT INTO fts_grep_pattern(pattern, event_id)
    VALUES (json_extract(NEW.payload, '$.tool_input.pattern'), NEW.id);
END;

CREATE TRIGGER trg_fts_glob_pattern
AFTER INSERT ON tool_events
WHEN NEW.tool_name = 'Glob'
BEGIN
    INSERT INTO fts_glob_pattern(pattern, event_id)
    VALUES (json_extract(NEW.payload, '$.tool_input.pattern'), NEW.id);
END;

CREATE TRIGGER trg_fts_url
AFTER INSERT ON tool_events
WHEN NEW.tool_name = 'WebFetch'
BEGIN
    INSERT INTO fts_url(url, event_id)
    VALUES (json_extract(NEW.payload, '$.tool_input.url'), NEW.id);
END;

CREATE TRIGGER trg_fts_search_query
AFTER INSERT ON tool_events
WHEN NEW.tool_name = 'WebSearch'
BEGIN
    INSERT INTO fts_search_query(query, event_id)
    VALUES (json_extract(NEW.payload, '$.tool_input.query'), NEW.id);
END;
