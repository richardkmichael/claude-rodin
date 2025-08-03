# tool-monitor

A SQLite-powered logger for analyzing how Claude uses command line tools.

## What it does

Captures tool usage events from Claude sessions and stores them for analysis. Because understanding AI tool patterns is more interesting than watching paint dry.

## Usage

```bash
# Hook it up to Claude's tool events
echo '{"session_id":"abc","tool_name":"Bash","tool_input":{"command":"ls"}}' | tool-monitor claude-tools.db

# Now analyze Claude's command line habits
```

## Architecture

- **This tool**: Captures everything, asks no questions
- **Your analysis tool**: Connects to same DB, creates views, discovers Claude's favorite commands
- **SQLite WAL mode**: Because concurrent access shouldn't require a PhD

## What gets stored

JSON blobs with auto-generated columns for:
- `session_id`, `tool_name`, `command`, `timestamp`
- `command_word` (first word of bash commands)
- Whatever else your JSON contains

## Size

1.9MB of pure, uncompressed efficiency. SQLite doesn't diet.

## Dependencies

None. SQLite is bundled because managing external dependencies is like herding cats.

## Tests

27 tests. They all pass. We checked.

```bash
cargo test
```

## Building

```bash
cargo build --release
```

Gets you a fast binary that strips debug symbols but keeps your dignity intact.