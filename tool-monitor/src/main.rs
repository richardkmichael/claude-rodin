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

use db::create_production_database;
use std::env;
use std::error::Error;
use std::io::{self, Read};

fn main() -> Result<(), Box<dyn Error>> {
    let args: Vec<String> = env::args().collect();

    if args.len() != 2 {
        eprintln!("Usage: {} <database_path>", args[0]);
        std::process::exit(1);
    }

    let db_path = &args[1];

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
