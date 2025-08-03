-- Tool Monitor Database Schema V2
-- Minimal schema with only stable hook contract fields + schema-as-data design

-- Database schema version tracking
CREATE TABLE schema_info (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Insert schema version
INSERT INTO schema_info (key, value) VALUES ('version', '2.0.0');
INSERT INTO schema_info (key, value) VALUES ('description', 'Minimal schema with schema-as-data design');

-- Main events table: Only extract stable hook contract fields
CREATE TABLE tool_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    payload TEXT NOT NULL,
    
    -- Stable hook contract fields (guaranteed by Claude Code)
    hook_event_name TEXT GENERATED ALWAYS AS (json_extract(payload, '$.hook_event_name')) STORED,
    tool_name TEXT GENERATED ALWAYS AS (json_extract(payload, '$.tool_name')) STORED,
    cwd TEXT GENERATED ALWAYS AS (json_extract(payload, '$.cwd')) STORED,
    transcript_path TEXT GENERATED ALWAYS AS (json_extract(payload, '$.transcript_path')) STORED,
    
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Store complete tool schemas as versioned data
CREATE TABLE tool_schemas (
    tool_name TEXT NOT NULL,
    hook_event TEXT NOT NULL,        -- 'PreToolUse' or 'PostToolUse'
    schema_version TEXT NOT NULL,
    schema_json TEXT NOT NULL,       -- Complete JSON Schema document
    category TEXT,                   -- File, Search, System, Web, Workflow
    description TEXT,                -- Human-readable description
    common_fields TEXT,              -- JSON array of frequently analyzed field paths
    
    -- Generated filename using our naming convention
    file_name TEXT GENERATED ALWAYS AS (
        lower(tool_name) || '-' || lower(replace(hook_event, 'ToolUse', '_tool_use')) || '.json'
    ) STORED,
    
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tool_name, hook_event, schema_version)
);

-- Track which schema version was active when (for handling schema evolution)
CREATE TABLE schema_versions (
    tool_name TEXT NOT NULL,
    hook_event TEXT NOT NULL,        -- 'PreToolUse' or 'PostToolUse'
    version TEXT NOT NULL,
    active_from DATE NOT NULL,       -- When this schema version became active
    active_to DATE,                  -- When it was superseded (NULL = current)
    notes TEXT,                      -- Migration notes, breaking changes, etc.
    PRIMARY KEY (tool_name, hook_event, version),
    FOREIGN KEY (tool_name, hook_event, version) REFERENCES tool_schemas(tool_name, hook_event, schema_version)
);

-- Indexes for performance
CREATE INDEX idx_session_id ON tool_events(session_id);
CREATE INDEX idx_tool_name ON tool_events(tool_name);
CREATE INDEX idx_hook_event_name ON tool_events(hook_event_name);
CREATE INDEX idx_created_at ON tool_events(created_at);
CREATE INDEX idx_cwd ON tool_events(cwd);

-- Index for schema lookups
CREATE INDEX idx_schema_active ON schema_versions(tool_name, hook_event, active_from, active_to);

-- Example view structure (will be generated dynamically)
-- This shows the pattern but won't be in the base schema
/*
CREATE VIEW bash_events AS
SELECT 
    e.*,
    json_extract(e.payload, '$.tool_input.command') as command,
    json_extract(e.payload, '$.tool_input.description') as description,
    json_extract(e.payload, '$.tool_input.timeout') as timeout,
    -- Extract first word of command for analysis
    CASE 
        WHEN json_extract(e.payload, '$.tool_input.command') IS NOT NULL
        THEN substr(json_extract(e.payload, '$.tool_input.command'), 1, 
             CASE WHEN instr(json_extract(e.payload, '$.tool_input.command'), ' ') > 0 
             THEN instr(json_extract(e.payload, '$.tool_input.command'), ' ') - 1 
             ELSE length(json_extract(e.payload, '$.tool_input.command')) END)
    END as command_word
FROM tool_events e
WHERE e.tool_name = 'Bash';
*/