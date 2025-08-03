//! Database module for tool monitoring capture system.
//!
//! This module provides a SQLite-based storage system optimized for capturing
//! tool usage events with generated columns for efficient analysis by separate tools.

use rusqlite::{Connection, Result as SqliteResult};
use serde_json::Value;
use std::error::Error;
use std::fmt;

/// Errors that can occur during database operations.
#[derive(Debug)]
pub enum DatabaseError {
    /// SQLite database error.
    Sqlite(rusqlite::Error),
    /// JSON parsing error.
    Json(serde_json::Error),
    /// Invalid data provided to database operations.
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

/// Database handle for tool monitoring events.
///
/// Provides storage for tool usage events with automatically generated columns
/// optimized for analysis by separate tools. Uses SQLite with WAL mode for
/// concurrent access support.
#[derive(Debug)]
pub struct Database {
    conn: Connection,
}

impl Database {
    /// Create a new database instance with the given connection.
    ///
    /// This will automatically create the required tables and indexes if they don't exist.
    /// Prefer using `create_production_database()` or the test helper functions instead
    /// of calling this directly.
    pub fn new(conn: Connection) -> Result<Self, DatabaseError> {
        let db = Database { conn };
        db.create_tables()?;
        Ok(db)
    }

    fn create_tables(&self) -> SqliteResult<()> {
        // Create schema_info table for version tracking
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_info (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )",
            [],
        )?;

        // Insert schema version (ignore if already exists)
        self.conn.execute(
            "INSERT OR IGNORE INTO schema_info (key, value) VALUES ('version', '2.0.0')",
            [],
        )?;
        self.conn.execute(
            "INSERT OR IGNORE INTO schema_info (key, value) VALUES ('description', 'Minimal schema with schema-as-data design')",
            [],
        )?;

        // Create tool_events table with minimal V2 schema (only stable hook contract fields)
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS tool_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                payload TEXT NOT NULL,
                
                -- Stable hook contract fields only (guaranteed by Claude Code)
                hook_event_name TEXT GENERATED ALWAYS AS (json_extract(payload, '$.hook_event_name')) STORED,
                tool_name TEXT GENERATED ALWAYS AS (json_extract(payload, '$.tool_name')) STORED,
                cwd TEXT GENERATED ALWAYS AS (json_extract(payload, '$.cwd')) STORED,
                transcript_path TEXT GENERATED ALWAYS AS (json_extract(payload, '$.transcript_path')) STORED,
                
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
            "CREATE INDEX IF NOT EXISTS idx_tool_name ON tool_events(tool_name)",
            [],
        )?;

        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_hook_event_name ON tool_events(hook_event_name)",
            [],
        )?;

        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_created_at ON tool_events(created_at)",
            [],
        )?;

        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_cwd ON tool_events(cwd)",
            [],
        )?;

        // Create schema-as-data tables
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS tool_schemas (
                tool_name TEXT NOT NULL,
                hook_event TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                schema_json TEXT NOT NULL,
                category TEXT,
                description TEXT,
                common_fields TEXT,
                
                -- Generated filename using our naming convention
                file_name TEXT GENERATED ALWAYS AS (
                    lower(tool_name) || '-' || lower(replace(hook_event, 'ToolUse', '_tool_use')) || '.json'
                ) STORED,
                
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (tool_name, hook_event, schema_version)
            )",
            [],
        )?;

        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_versions (
                tool_name TEXT NOT NULL,
                hook_event TEXT NOT NULL,
                version TEXT NOT NULL,
                active_from DATE NOT NULL,
                active_to DATE,
                notes TEXT,
                PRIMARY KEY (tool_name, hook_event, version),
                FOREIGN KEY (tool_name, hook_event, version) REFERENCES tool_schemas(tool_name, hook_event, schema_version)
            )",
            [],
        )?;

        // Create index for schema lookups
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_schema_active ON schema_versions(tool_name, hook_event, active_from, active_to)",
            [],
        )?;

        Ok(())
    }

    /// Insert a tool event from a JSON payload.
    ///
    /// # Arguments
    ///
    /// * `json_payload` - A JSON string containing the tool event data. Must include
    ///   a `session_id` field as a string.
    ///
    /// # Returns
    ///
    /// Returns `Ok(())` on successful insertion, or a `DatabaseError` if:
    /// - The JSON is malformed
    /// - The `session_id` field is missing or not a string
    /// - A database error occurs
    ///
    /// # Example
    ///
    /// ```rust,no_run
    /// # use tool_monitor::db::{create_production_database, DatabaseError};
    /// # fn example() -> Result<(), DatabaseError> {
    /// let db = create_production_database("monitor.db")?;
    /// let event = r#"{
    ///     "session_id": "abc-123",
    ///     "tool_name": "Bash",
    ///     "tool_input": {
    ///         "command": "ls -la",
    ///         "description": "List files"
    ///     }
    /// }"#;
    /// db.insert_event(event)?;
    /// # Ok(())
    /// # }
    /// ```
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

/// Create a production database with optimal configuration for concurrent access.
///
/// This function opens a SQLite database at the specified path and configures it
/// with settings optimized for production use, including WAL mode for concurrent
/// access by multiple processes.
///
/// # Arguments
///
/// * `db_path` - Path to the SQLite database file. Will be created if it doesn't exist.
///
/// # Returns
///
/// Returns a configured `Database` instance ready for production use.
///
/// # Configuration Applied
///
/// - **WAL mode**: Allows concurrent readers with a single writer
/// - **Busy timeout**: 5 seconds to handle concurrent access conflicts
/// - **Synchronous NORMAL**: Balance between safety and performance
/// - **Cache size**: 10,000 pages for better performance
///
/// # Example
///
/// ```rust,no_run
/// # use tool_monitor::db::{create_production_database, DatabaseError};
/// # fn example() -> Result<(), DatabaseError> {
/// let db = create_production_database("/path/to/monitor.db")?;
/// 
/// let event = r#"{
///     "session_id": "session-123",
///     "hook_event_name": "PreToolUse",
///     "tool_name": "Bash",
///     "tool_input": {
///         "command": "cargo test",
///         "description": "Run tests"
///     }
/// }"#;
/// 
/// db.insert_event(event)?;
/// # Ok(())
/// # }
/// ```
pub fn create_production_database(db_path: &str) -> Result<Database, DatabaseError> {
    let conn = Connection::open(db_path)?;
    
    // Configure for production with concurrency support
    // These PRAGMAs return values, so use query_row
    let _: String = conn.query_row("PRAGMA journal_mode=WAL", [], |row| row.get(0))?;
    let _: i32 = conn.query_row("PRAGMA busy_timeout=5000", [], |row| row.get(0))?;
    
    // These PRAGMAs don't return values, so use execute
    conn.execute("PRAGMA synchronous=NORMAL", [])?;
    conn.execute("PRAGMA cache_size=10000", [])?;
    
    Database::new(conn)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn create_test_database() -> Result<Database, DatabaseError> {
        let conn = Connection::open(":memory:")?;
        // Skip pragma configuration for tests - keep it simple
        Database::new(conn)
    }

    fn create_test_db() -> Database {
        create_test_database().unwrap()
    }

    #[test]
    fn test_database_creation() {
        let _db = create_test_db();
        // Database creation should succeed without panic
        assert!(true);
    }

    #[test]
    fn test_production_database_factory() {
        // Test production database creation with temporary file
        let temp_path = "/tmp/test_production.db";
        std::fs::remove_file(temp_path).ok(); // Clean up if exists
        
        let db = create_production_database(temp_path).unwrap();
        
        // Verify WAL mode is enabled
        let journal_mode: String = db.conn.query_row("PRAGMA journal_mode", [], |row| row.get(0)).unwrap();
        assert_eq!(journal_mode, "wal");
        
        // Verify other settings
        let busy_timeout: i32 = db.conn.query_row("PRAGMA busy_timeout", [], |row| row.get(0)).unwrap();
        assert_eq!(busy_timeout, 5000);
        
        // Clean up
        std::fs::remove_file(temp_path).ok();
        std::fs::remove_file(format!("{}-wal", temp_path)).ok();
        std::fs::remove_file(format!("{}-shm", temp_path)).ok();
    }

    #[test]
    fn test_factories_create_different_configurations() {
        let temp_path = "/tmp/test_factory_diff.db";
        std::fs::remove_file(temp_path).ok();
        
        let prod_db = create_production_database(temp_path).unwrap();
        let test_db = create_test_database().unwrap();
        
        // Production should have WAL mode
        let prod_journal: String = prod_db.conn.query_row("PRAGMA journal_mode", [], |row| row.get(0)).unwrap();
        assert_eq!(prod_journal, "wal");
        
        // Test DB should have memory mode (default for :memory:)
        let test_journal: String = test_db.conn.query_row("PRAGMA journal_mode", [], |row| row.get(0)).unwrap();
        assert_eq!(test_journal, "memory");
        
        // Clean up
        std::fs::remove_file(temp_path).ok();
        std::fs::remove_file(format!("{}-wal", temp_path)).ok();
        std::fs::remove_file(format!("{}-shm", temp_path)).ok();
    }

    #[test]
    fn test_insert_valid_json() {
        let db = create_test_db();
        let json_payload = r#"{"session_id":"test123","hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"ls","description":"test command"}}"#;

        let result = db.insert_event(json_payload);
        assert!(result.is_ok());
    }

    #[test]
    fn test_insert_invalid_json() {
        let db = create_test_db();
        let invalid_json = r#"{"invalid": json}"#;

        let result = db.insert_event(invalid_json);
        assert!(result.is_err());
        match result.unwrap_err() {
            DatabaseError::Json(_) => assert!(true),
            _ => panic!("Expected JSON error"),
        }
    }

    #[test]
    fn test_missing_session_id() {
        let db = create_test_db();
        let json_without_session = r#"{"hook_event_name":"PreToolUse","tool_name":"Bash"}"#;

        let result = db.insert_event(json_without_session);
        assert!(result.is_err());
        match result.unwrap_err() {
            DatabaseError::InvalidData(msg) => assert_eq!(msg, "Missing session_id"),
            _ => panic!("Expected InvalidData error"),
        }
    }

    #[test]
    fn test_generated_columns() {
        let db = create_test_db();
        let json_payload = r#"{"session_id":"test123","hook_event_name":"PostToolUse","tool_name":"Bash","cwd":"/home/user","transcript_path":"/path/to/transcript.jsonl","tool_input":{"command":"ls -la","description":"list files"}}"#;

        db.insert_event(json_payload).unwrap();

        // Query the V2 generated columns (only stable hook contract fields)
        let mut stmt = db.conn.prepare("SELECT hook_event_name, tool_name, cwd, transcript_path FROM tool_events WHERE session_id = ?1").unwrap();
        let row = stmt
            .query_row(["test123"], |row| {
                Ok((
                    row.get::<_, String>(0)?, // hook_event_name
                    row.get::<_, String>(1)?, // tool_name
                    row.get::<_, String>(2)?, // cwd
                    row.get::<_, String>(3)?, // transcript_path
                ))
            })
            .unwrap();

        assert_eq!(row.0, "PostToolUse");
        assert_eq!(row.1, "Bash");
        assert_eq!(row.2, "/home/user");
        assert_eq!(row.3, "/path/to/transcript.jsonl");
    }

    #[test]
    fn test_json_extraction_at_runtime() {
        let db = create_test_db();

        let test_cases = vec![
            (r#"{"session_id":"test1","tool_name":"Bash","hook_event_name":"PreToolUse","cwd":"/home","transcript_path":"/path","tool_input":{"command":"ls -la"}}"#, "ls -la"),
            (r#"{"session_id":"test2","tool_name":"Edit","hook_event_name":"PreToolUse","cwd":"/home","transcript_path":"/path","tool_input":{"file_path":"/test.txt"}}"#, "/test.txt"),
        ];

        for (payload, _expected_value) in test_cases.iter() {
            db.insert_event(payload).unwrap();
        }
        
        // Test runtime JSON extraction (how analysis is done in V2)
        let bash_command: String = db.conn.query_row(
            "SELECT json_extract(payload, '$.tool_input.command') FROM tool_events WHERE session_id = 'test1'",
            [],
            |row| row.get(0)
        ).unwrap();
        assert_eq!(bash_command, "ls -la");

        let file_path: String = db.conn.query_row(
            "SELECT json_extract(payload, '$.tool_input.file_path') FROM tool_events WHERE session_id = 'test2'", 
            [],
            |row| row.get(0)
        ).unwrap();
        assert_eq!(file_path, "/test.txt");
    }

    #[test]
    fn test_multiple_inserts() {
        let db = create_test_db();

        let payloads = vec![
            r#"{"session_id":"session1","hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"ls"}}"#,
            r#"{"session_id":"session1","hook_event_name":"PostToolUse","tool_name":"Bash","tool_response":{"stdout":"output","stderr":""}}"#,
            r#"{"session_id":"session2","hook_event_name":"PreToolUse","tool_name":"Read","tool_input":{"file_path":"/test"}}"#,
        ];

        for payload in payloads {
            db.insert_event(payload).unwrap();
        }

        // Verify count
        let count: i32 = db
            .conn
            .query_row("SELECT COUNT(*) FROM tool_events", [], |row| row.get(0))
            .unwrap();
        assert_eq!(count, 3);

        // Verify different sessions
        let session_count: i32 = db
            .conn
            .query_row(
                "SELECT COUNT(DISTINCT session_id) FROM tool_events",
                [],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(session_count, 2);
    }

    #[test]
    fn test_generated_columns_edge_cases() {
        let db = create_test_db();

        let test_cases = vec![
            // Missing optional fields (V2 focuses on stable hook contract fields)
            (r#"{"session_id":"test1","tool_name":"Read","hook_event_name":"PreToolUse","tool_input":{"file_path":"/test"}}"#, "Read", "PreToolUse"),
            // Empty cwd field
            (r#"{"session_id":"test2","tool_name":"Bash","hook_event_name":"PostToolUse","cwd":"","tool_input":{"command":"pwd"}}"#, "Bash", "PostToolUse"),
            // Missing transcript_path (optional in some contexts)
            (r#"{"session_id":"test3","tool_name":"Edit","hook_event_name":"PreToolUse","cwd":"/home","tool_input":{"file_path":"/test.txt"}}"#, "Edit", "PreToolUse"),
        ];

        for (i, (payload, expected_tool, expected_hook)) in test_cases.iter().enumerate() {
            db.insert_event(payload).unwrap();
            
            let session_id = format!("test{}", i + 1);
            
            // Test V2 generated columns (stable hook contract fields)
            let result = db.conn.query_row(
                "SELECT tool_name, hook_event_name FROM tool_events WHERE session_id = ?1",
                [&session_id],
                |row| Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?))
            ).unwrap();
            
            assert_eq!(result.0, *expected_tool);
            assert_eq!(result.1, *expected_hook);
            
            // Test runtime JSON extraction for tool-specific fields (V2 approach)
            if i == 1 { // Test Bash command extraction
                let command: String = db.conn.query_row(
                    "SELECT json_extract(payload, '$.tool_input.command') FROM tool_events WHERE session_id = ?1",
                    [&session_id],
                    |row| row.get(0)
                ).unwrap();
                assert_eq!(command, "pwd");
            }
        }
    }

    #[test]
    fn test_indexes_exist() {
        let db = create_test_db();
        
        // Query sqlite_master to verify indexes were created
        let mut stmt = db.conn.prepare("SELECT name FROM sqlite_master WHERE type = 'index' AND name LIKE 'idx_%'").unwrap();
        let index_names: Vec<String> = stmt.query_map([], |row| row.get(0)).unwrap()
            .collect::<Result<Vec<_>, _>>().unwrap();
        
        let expected_indexes = vec![
            "idx_session_id",
            "idx_tool_name",
            "idx_hook_event_name",
            "idx_created_at",
            "idx_cwd"
        ];
        
        for expected in &expected_indexes {
            assert!(index_names.contains(&expected.to_string()), 
                "Missing index: {}", expected);
        }
    }

    #[test] 
    fn test_real_monitoring_json_structure() {
        let db = create_test_db();
        
        // Test with actual structure from tool monitoring
        let real_json = r#"{
            "session_id":"c8f372b2-fe16-4f10-9247-05ff4f3d4c77",
            "transcript_path":"/Users/test/.claude/projects/test.jsonl",
            "cwd":"/Users/test/project",
            "hook_event_name":"PreToolUse",
            "tool_name":"Bash",
            "tool_input":{
                "command":"cargo test",
                "description":"Run unit tests"
            }
        }"#;
        
        db.insert_event(real_json).unwrap();
        
        // Test V2 generated columns (stable hook contract fields)
        let result = db.conn.query_row(
            "SELECT hook_event_name, tool_name, cwd, transcript_path FROM tool_events WHERE session_id = ?1",
            ["c8f372b2-fe16-4f10-9247-05ff4f3d4c77"],
            |row| Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?, 
                row.get::<_, String>(2)?,
                row.get::<_, String>(3)?,
            ))
        ).unwrap();
        
        assert_eq!(result.0, "PreToolUse");
        assert_eq!(result.1, "Bash");
        assert_eq!(result.2, "/Users/test/project");
        assert_eq!(result.3, "/Users/test/.claude/projects/test.jsonl");
        
        // Test runtime JSON extraction for tool-specific fields (V2 approach)
        let command: String = db.conn.query_row(
            "SELECT json_extract(payload, '$.tool_input.command') FROM tool_events WHERE session_id = ?1",
            ["c8f372b2-fe16-4f10-9247-05ff4f3d4c77"],
            |row| row.get(0)
        ).unwrap();
        assert_eq!(command, "cargo test");
        
        // Test extracting command word using SQLite substring functions (V2 approach)
        let command_word: String = db.conn.query_row(
            "SELECT CASE WHEN instr(json_extract(payload, '$.tool_input.command'), ' ') > 0 THEN substr(json_extract(payload, '$.tool_input.command'), 1, instr(json_extract(payload, '$.tool_input.command'), ' ') - 1) ELSE json_extract(payload, '$.tool_input.command') END FROM tool_events WHERE session_id = ?1",
            ["c8f372b2-fe16-4f10-9247-05ff4f3d4c77"],
            |row| row.get(0)
        ).unwrap();
        assert_eq!(command_word, "cargo");
    }

    #[test]
    fn test_concurrent_access_simulation() {
        use std::thread;
        
        let temp_path = "/tmp/test_concurrent.db";
        std::fs::remove_file(temp_path).ok();
        
        // Create initial database
        {
            let _db = create_production_database(temp_path).unwrap();
        } // Close connection
        
        let mut handles = vec![];
        
        // Simulate concurrent access from 3 processes (each opens own connection)
        for thread_id in 0..3 {
            let path = temp_path.to_string();
            let handle = thread::spawn(move || {
                // Each thread gets its own database connection (simulating separate processes)
                let db = create_production_database(&path).unwrap();
                for i in 0..5 {
                    let payload = format!(
                        r#"{{"session_id":"thread{}_event{}","tool_name":"Bash","tool_input":{{"command":"echo {}"}}}}"#,
                        thread_id, i, i
                    );
                    db.insert_event(&payload).unwrap();
                }
            });
            handles.push(handle);
        }
        
        // Wait for all threads to complete
        for handle in handles {
            handle.join().unwrap();
        }
        
        // Verify all events were inserted using a fresh connection
        let verification_db = create_production_database(temp_path).unwrap();
        let count: i32 = verification_db.conn.query_row("SELECT COUNT(*) FROM tool_events", [], |row| row.get(0)).unwrap();
        assert_eq!(count, 15); // 3 threads × 5 events each
        
        // Clean up
        std::fs::remove_file(temp_path).ok();
        std::fs::remove_file(format!("{}-wal", temp_path)).ok();
        std::fs::remove_file(format!("{}-shm", temp_path)).ok();
    }

    #[test]
    fn test_invalid_database_path() {
        // Test with invalid path (directory that doesn't exist)
        let invalid_path = "/nonexistent/directory/test.db";
        let result = create_production_database(invalid_path);
        assert!(result.is_err());
        match result.unwrap_err() {
            DatabaseError::Sqlite(_) => assert!(true),
            _ => panic!("Expected SQLite error for invalid path"),
        }
    }

    #[test]
    fn test_readonly_directory() {
        use std::fs;
        use std::os::unix::fs::PermissionsExt;
        
        // Create a readonly directory
        let readonly_dir = "/tmp/readonly_test_dir";
        fs::create_dir_all(readonly_dir).ok();
        
        // Set directory to readonly
        let mut perms = fs::metadata(readonly_dir).unwrap().permissions();
        perms.set_mode(0o444); // Read-only
        fs::set_permissions(readonly_dir, perms).ok();
        
        let db_path = format!("{}/test.db", readonly_dir);
        let result = create_production_database(&db_path);
        
        // Should fail to create database in readonly directory
        assert!(result.is_err());
        
        // Cleanup - restore permissions first
        let mut perms = fs::metadata(readonly_dir).unwrap().permissions();
        perms.set_mode(0o755);
        fs::set_permissions(readonly_dir, perms).ok();
        fs::remove_dir_all(readonly_dir).ok();
    }

    #[test]
    fn test_large_json_payload() {
        let db = create_test_db();
        
        // Create a large command string
        let large_command = "x".repeat(10000);
        let large_payload = format!(
            r#"{{"session_id":"large_test","tool_name":"Bash","hook_event_name":"PreToolUse","cwd":"/home","transcript_path":"/path/to/transcript.jsonl","tool_input":{{"command":"{}","description":"Large command test"}}}}"#,
            large_command
        );
        
        let result = db.insert_event(&large_payload);
        assert!(result.is_ok());
        
        // Verify V2 generated columns work with large payloads
        let tool_name: String = db.conn.query_row(
            "SELECT tool_name FROM tool_events WHERE session_id = 'large_test'",
            [],
            |row| row.get(0)
        ).unwrap();
        assert_eq!(tool_name, "Bash");
        
        // Verify large command was stored correctly using runtime JSON extraction (V2 approach)
        let stored_command: String = db.conn.query_row(
            "SELECT json_extract(payload, '$.tool_input.command') FROM tool_events WHERE session_id = 'large_test'",
            [],
            |row| row.get(0)
        ).unwrap();
        assert_eq!(stored_command, large_command);
    }

    #[test]
    fn test_unicode_json_payload() {
        let db = create_test_db();
        
        let unicode_payload = r#"{"session_id":"unicode_test","tool_name":"Bash","tool_input":{"command":"echo '你好世界 🌍'","description":"Unicode test with émojis and ñoñ-ASCII çhars"}}"#;
        
        let result = db.insert_event(unicode_payload);
        assert!(result.is_ok());
        
        // Verify Unicode was preserved using runtime JSON extraction (V2 approach)
        let command: String = db.conn.query_row(
            "SELECT json_extract(payload, '$.tool_input.command') FROM tool_events WHERE session_id = 'unicode_test'",
            [],
            |row| row.get(0)
        ).unwrap();
        
        let description: String = db.conn.query_row(
            "SELECT json_extract(payload, '$.tool_input.description') FROM tool_events WHERE session_id = 'unicode_test'",
            [],
            |row| row.get(0)
        ).unwrap();
        
        assert_eq!(command, "echo '你好世界 🌍'");
        assert_eq!(description, "Unicode test with émojis and ñoñ-ASCII çhars");
    }

    #[test]
    fn test_deeply_nested_json() {
        let db = create_test_db();
        
        let nested_payload = r#"{"session_id":"nested_test","tool_name":"CustomTool","tool_input":{"config":{"nested":{"deeply":{"very":{"much":"value","array":[1,2,3],"object":{"key":"value"}}}}}}}"#;
        
        let result = db.insert_event(nested_payload);
        assert!(result.is_ok());
        
        // Verify the full payload was stored
        let stored_payload: String = db.conn.query_row(
            "SELECT payload FROM tool_events WHERE session_id = 'nested_test'",
            [],
            |row| row.get(0)
        ).unwrap();
        
        // Parse both to verify they're equivalent JSON
        let original: serde_json::Value = serde_json::from_str(nested_payload).unwrap();
        let stored: serde_json::Value = serde_json::from_str(&stored_payload).unwrap();
        assert_eq!(original, stored);
    }

    #[test]
    fn test_schema_table_structure() {
        let db = create_test_db();
        
        // Check the actual CREATE TABLE statement to verify generated columns
        let create_sql: String = db.conn.query_row(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='tool_events'",
            [],
            |row| row.get(0)
        ).unwrap();
        
        // Verify the table contains V2 generated columns (stable hook contract fields only)
        assert!(create_sql.contains("hook_event_name TEXT GENERATED ALWAYS AS"));
        assert!(create_sql.contains("tool_name TEXT GENERATED ALWAYS AS"));
        assert!(create_sql.contains("cwd TEXT GENERATED ALWAYS AS"));
        assert!(create_sql.contains("transcript_path TEXT GENERATED ALWAYS AS"));
        
        // Verify V1 columns are NOT present in V2 schema
        assert!(!create_sql.contains("command TEXT GENERATED ALWAYS AS"));
        assert!(!create_sql.contains("description TEXT GENERATED ALWAYS AS"));
        assert!(!create_sql.contains("timestamp TEXT GENERATED ALWAYS AS"));
        assert!(!create_sql.contains("command_word TEXT GENERATED ALWAYS AS"));
        
        // Also verify basic columns exist
        let mut stmt = db.conn.prepare("PRAGMA table_info(tool_events)").unwrap();
        let columns: Vec<String> = stmt.query_map([], |row| {
            Ok(row.get::<_, String>(1)?) // Column name is at index 1
        }).unwrap().collect::<Result<Vec<_>, _>>().unwrap();
        
        let basic_columns = vec!["id", "session_id", "payload", "created_at"];
        for expected in &basic_columns {
            assert!(columns.contains(&expected.to_string()), 
                "Missing basic column: {}", expected);
        }
    }

    #[test]
    fn test_generated_column_expressions() {
        let db = create_test_db();
        
        // Test that V2 generated columns work correctly with various JSON structures
        let test_payload = r#"{"session_id":"expr_test","hook_event_name":"TestEvent","tool_name":"TestTool","cwd":"/test/path","transcript_path":"/path/to/transcript.jsonl","tool_input":{"command":"test command","description":"test desc"},"timestamp":"2025-08-02T12:00:00Z"}"#;
        
        db.insert_event(test_payload).unwrap();
        
        // Verify V2 generated columns (stable hook contract fields only)
        let result = db.conn.query_row(
            "SELECT hook_event_name, tool_name, cwd, transcript_path FROM tool_events WHERE session_id = 'expr_test'",
            [],
            |row| Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
                row.get::<_, String>(3)?,
            ))
        ).unwrap();
        
        assert_eq!(result.0, "TestEvent");
        assert_eq!(result.1, "TestTool");
        assert_eq!(result.2, "/test/path");
        assert_eq!(result.3, "/path/to/transcript.jsonl");
        
        // Test runtime JSON extraction for tool-specific fields (V2 approach)
        let command: String = db.conn.query_row(
            "SELECT json_extract(payload, '$.tool_input.command') FROM tool_events WHERE session_id = 'expr_test'",
            [],
            |row| row.get(0)
        ).unwrap();
        assert_eq!(command, "test command");
        
        let description: String = db.conn.query_row(
            "SELECT json_extract(payload, '$.tool_input.description') FROM tool_events WHERE session_id = 'expr_test'",
            [],
            |row| row.get(0)
        ).unwrap();
        assert_eq!(description, "test desc");
    }

    #[test]
    fn test_connection_recovery_after_error() {
        let db = create_test_db();
        
        // First, insert valid data
        let valid_payload = r#"{"session_id":"recovery_test","tool_name":"Bash","tool_input":{"command":"ls"}}"#;
        db.insert_event(valid_payload).unwrap();
        
        // Try to insert invalid data (should fail)
        let invalid_payload = "invalid json";
        let result = db.insert_event(invalid_payload);
        assert!(result.is_err());
        
        // Verify connection still works after error
        let another_valid_payload = r#"{"session_id":"recovery_test2","tool_name":"Bash","tool_input":{"command":"pwd"}}"#;
        let result = db.insert_event(another_valid_payload);
        assert!(result.is_ok());
        
        // Verify both valid entries were inserted
        let count: i32 = db.conn.query_row(
            "SELECT COUNT(*) FROM tool_events WHERE session_id LIKE 'recovery_test%'",
            [],
            |row| row.get(0)
        ).unwrap();
        assert_eq!(count, 2);
    }

    #[test]
    fn test_pragma_configuration_verification() {
        // Test that we can verify PRAGMA settings were applied correctly
        let temp_path = "/tmp/test_pragma_verification.db";
        std::fs::remove_file(temp_path).ok();
        
        let db = create_production_database(temp_path).unwrap();
        
        // Verify each PRAGMA setting individually
        let journal_mode: String = db.conn.query_row("PRAGMA journal_mode", [], |row| row.get(0)).unwrap();
        assert_eq!(journal_mode.to_lowercase(), "wal");
        
        let busy_timeout: i32 = db.conn.query_row("PRAGMA busy_timeout", [], |row| row.get(0)).unwrap();
        assert_eq!(busy_timeout, 5000);
        
        let synchronous: i32 = db.conn.query_row("PRAGMA synchronous", [], |row| row.get(0)).unwrap();
        assert_eq!(synchronous, 1); // NORMAL = 1
        
        let cache_size: i32 = db.conn.query_row("PRAGMA cache_size", [], |row| row.get(0)).unwrap();
        assert_eq!(cache_size, 10000);
        
        // Clean up
        std::fs::remove_file(temp_path).ok();
        std::fs::remove_file(format!("{}-wal", temp_path)).ok();
        std::fs::remove_file(format!("{}-shm", temp_path)).ok();
    }

    #[test]
    fn test_database_file_permissions() {
        let temp_path = "/tmp/test_permissions.db";
        std::fs::remove_file(temp_path).ok();
        
        // Create database
        let _db = create_production_database(temp_path).unwrap();
        
        // Verify the database file was created and is readable
        assert!(std::path::Path::new(temp_path).exists());
        
        // Verify we can read metadata (checks permissions)
        let metadata = std::fs::metadata(temp_path).unwrap();
        assert!(metadata.is_file());
        assert!(metadata.len() > 0); // Database should have some content
        
        // Clean up
        std::fs::remove_file(temp_path).ok();
        std::fs::remove_file(format!("{}-wal", temp_path)).ok();
        std::fs::remove_file(format!("{}-shm", temp_path)).ok();
    }

    #[test]
    fn test_session_id_validation_types() {
        let db = create_test_db();
        
        // Test different session_id types and edge cases
        let test_cases = vec![
            // Valid cases
            (r#"{"session_id":"normal-uuid","tool_name":"Test"}"#, true),
            (r#"{"session_id":"123","tool_name":"Test"}"#, true),
            (r#"{"session_id":"","tool_name":"Test"}"#, true), // Empty string is valid
            
            // Invalid cases
            (r#"{"session_id":123,"tool_name":"Test"}"#, false), // Number instead of string
            (r#"{"session_id":null,"tool_name":"Test"}"#, false), // Null
            (r#"{"tool_name":"Test"}"#, false), // Missing session_id
        ];
        
        for (payload, should_succeed) in test_cases {
            let result = db.insert_event(payload);
            if should_succeed {
                assert!(result.is_ok(), "Expected success for payload: {}", payload);
            } else {
                assert!(result.is_err(), "Expected failure for payload: {}", payload);
            }
        }
    }
}
