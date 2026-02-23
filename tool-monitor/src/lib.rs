//! Tool monitoring capture library.
//!
//! This library provides SQLite-based storage for tool usage events with
//! generated columns optimized for analysis by separate tools.
//!
//! # Example
//!
//! ```rust,no_run
//! use tool_monitor::db::{create_database, DatabaseError};
//!
//! fn main() -> Result<(), DatabaseError> {
//!     let db = create_database("monitor.db")?;
//!     
//!     let event = r#"{
//!         "session_id": "abc-123",
//!         "tool_name": "Bash",
//!         "tool_input": {
//!             "command": "ls -la",
//!             "description": "List files"
//!         }
//!     }"#;
//!     
//!     db.insert_event(event)?;
//!     Ok(())
//! }
//! ```

pub mod db;