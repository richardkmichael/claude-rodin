use rusqlite::{Connection, Result as SqliteResult};
use serde_json::Value;
use std::error::Error;
use std::fmt;

#[derive(Debug)]
pub enum DatabaseError {
    Sqlite(rusqlite::Error),
    Json(serde_json::Error),
    InvalidData(String),
}

impl fmt::Display for DatabaseError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            DatabaseError::Sqlite(e) => write!(f, "SQLite error: {}", e),
            DatabaseError::Json(e) => write!(f, "JSON error: {}", e),
            DatabaseError::InvalidData(msg) => write!(f, "Invalid data: {}", msg),
        }
    }
}

impl Error for DatabaseError {}

impl From<rusqlite::Error> for DatabaseError {
    fn from(error: rusqlite::Error) -> Self {
        DatabaseError::Sqlite(error)
    }
}

impl From<serde_json::Error> for DatabaseError {
    fn from(error: serde_json::Error) -> Self {
        DatabaseError::Json(error)
    }
}

pub struct Database {
    conn: Connection,
}

impl Database {
    pub fn new(db_path: &str) -> Result<Self, DatabaseError> {
        let conn = Connection::open(db_path)?;
        let db = Database { conn };
        db.create_tables()?;
        Ok(db)
    }

    fn create_tables(&self) -> SqliteResult<()> {
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS tool_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                payload TEXT NOT NULL,
                
                -- Generated columns from JSON
                hook_event_name TEXT GENERATED ALWAYS AS (json_extract(payload, '$.hook_event_name')) STORED,
                tool_name TEXT GENERATED ALWAYS AS (json_extract(payload, '$.tool_name')) STORED,
                cwd TEXT GENERATED ALWAYS AS (json_extract(payload, '$.cwd')) STORED,
                command TEXT GENERATED ALWAYS AS (json_extract(payload, '$.tool_input.command')) STORED,
                description TEXT GENERATED ALWAYS AS (json_extract(payload, '$.tool_input.description')) STORED,
                
                -- Failure analysis
                has_stderr INTEGER GENERATED ALWAYS AS (
                    CASE WHEN length(json_extract(payload, '$.tool_response.stderr')) > 0 THEN 1 ELSE 0 END
                ) STORED,
                interrupted INTEGER GENERATED ALWAYS AS (json_extract(payload, '$.tool_response.interrupted')) STORED,
                
                -- Output size analysis  
                stdout_length INTEGER GENERATED ALWAYS AS (length(json_extract(payload, '$.tool_response.stdout'))) STORED,
                stderr_length INTEGER GENERATED ALWAYS AS (length(json_extract(payload, '$.tool_response.stderr'))) STORED,
                
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )",
            [],
        )?;

        // Create indexes for analysis
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_session_id ON tool_events(session_id)",
            [],
        )?;

        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_command ON tool_events(command) WHERE tool_name = 'Bash'",
            [],
        )?;

        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_failures ON tool_events(has_stderr, interrupted) WHERE tool_name = 'Bash'",
            [],
        )?;

        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_output_size ON tool_events(stdout_length) WHERE tool_name = 'Bash'",
            [],
        )?;

        Ok(())
    }

    pub fn insert_event(&self, json_payload: &str) -> Result<(), DatabaseError> {
        // Validate JSON first
        let parsed: Value = serde_json::from_str(json_payload)?;

        // Check for required fields
        if parsed.get("session_id").is_none() {
            return Err(DatabaseError::InvalidData("Missing session_id".to_string()));
        }

        // Extract session_id for the query
        let session_id = parsed["session_id"]
            .as_str()
            .ok_or_else(|| DatabaseError::InvalidData("session_id must be a string".to_string()))?;

        self.conn.execute(
            "INSERT INTO tool_events (session_id, payload) VALUES (?1, ?2)",
            [session_id, json_payload],
        )?;

        Ok(())
    }
}
