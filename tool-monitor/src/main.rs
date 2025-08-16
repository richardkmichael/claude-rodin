//! Tool monitoring capture utility.
//!
//! This binary reads JSON tool event data from stdin and stores it in a SQLite database
//! optimized for analysis by separate tools. Uses WAL mode for concurrent access.
//!
//! # Usage
//!
//! ```bash
//! echo '{"session_id":"test","tool_name":"Bash"}' | tool-monitor /path/to/db
//! ```

mod db;

use clap::Parser;
use db::create_production_database;
use std::error::Error;
use std::io::{self, Read};

#[derive(Parser)]
#[command(name = "tool-monitor")]
#[command(version = env!("CARGO_PKG_VERSION"))]
#[command(about = "Tool monitoring capture utility")]
#[command(long_about = "Reads JSON tool event data from stdin and stores it in a SQLite database optimized for analysis by separate tools. Uses WAL mode for concurrent access.")]
struct Args {
    /// Path to SQLite database file
    database_path: String,
}

fn main() -> Result<(), Box<dyn Error>> {
    let args = Args::parse();
    let db_path = &args.database_path;

    let mut input = String::new();
    io::stdin().read_to_string(&mut input)?;

    // Trim any trailing whitespace/newlines
    let input = input.trim();

    if input.is_empty() {
        return Ok(());
    }

    let database = create_production_database(db_path)?;
    database.insert_event(input)?;

    Ok(())
}
