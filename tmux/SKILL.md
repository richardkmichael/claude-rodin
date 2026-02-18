---
name: tmux
description: "Use interactive CLIs (git, python, gdb, etc.) with tmux by sending keystrokes and scraping pane output."
allowed-tools: "Read(//tmp/claude-edit-*/**), Edit(//tmp/claude-edit-*/**), Bash(tmux *), Bash(*/scripts/start-session.sh *), Bash(*/scripts/stop-session.sh *), Bash(*/scripts/send-and-wait.sh *), Bash(*/scripts/wait-for-text.sh *), Bash(*/scripts/find-sessions.sh *)"
hooks:
  PostToolUse:
    - matcher: "*"
      hooks:
        - type: command
          command: "/path/to/.claude/skills/tmux/scripts/post-start-session-hook.sh"
---

# tmux Skill

Use tmux as a programmable terminal multiplexer for interactive work.

The "Base directory for this skill" path (shown at load time) is needed to run
scripts. Use it to construct absolute paths for all script calls.

## Quickstart

Always pass `-i ${CLAUDE_SESSION_ID}` when starting sessions.

```bash
# Start a server for a purpose (returns JSON with socket/session/target/log)
$SKILL_DIR/scripts/start-session.sh -i ${CLAUDE_SESSION_ID} -s python
# {"socket": "claude/<id>/python", "session": "claude-python-<id>", "target": "...", "log": "..."}

# Send a command and wait for expected output
$SKILL_DIR/scripts/send-and-wait.sh -L $SOCKET -t $TARGET -c 'python -q' -p '>>>' -l

# Each purpose gets its own server
$SKILL_DIR/scripts/start-session.sh -i ${CLAUDE_SESSION_ID} -s git
```

A PostToolUse hook automatically shows the user the log path (and monitor
command if `--monitor` was not used) after `start-session.sh` runs.

Pass `--monitor` to open an Alacritty window attached to the server.
Use `--monitor` when the user asks to watch or says "show me".
Do not use it by default.

## Architecture

Each `-s` call creates an isolated tmux server via `-L claude/<session-id>/<name>`.
Sockets are stored in tmux's default directory (usually `/tmp/tmux-<uid>/`).

- Pass `--monitor` to open an Alacritty monitoring window for the server
- Stopping a server closes its Alacritty window naturally
- All pane output is automatically logged to `${TMPDIR:-/tmp}/claude-tmux-logs/`
- User can discover all sockets via `find-sessions.sh`

## Scripts

Run with `-h` for help.

| Script | Purpose |
|--------|---------|
| `start-session.sh` | Start server, returns JSON `{socket, session, target, log}` |
| `stop-session.sh` | Stop a server (`-s name`) or all servers (no `-s`) |
| `find-sessions.sh` | List all claude-* sessions across sockets |
| `wait-for-text.sh` | Poll pane for pattern with timeout |
| `send-and-wait.sh` | Send command and wait for output |

## Sending commands

Prefer `send-and-wait.sh` — it sends the command and polls for expected output:
```bash
$SKILL_DIR/scripts/send-and-wait.sh -L $SOCKET -t $TARGET -c 'print("hello")' -p 'hello' -l
```
`-l` sends literally (avoids shell expansion). Omit for key sequences.

For commands with no predictable output, use raw send-keys + capture:
```bash
tmux -L $SOCKET send-keys -t $TARGET -l -- "$text"
tmux -L $SOCKET send-keys -t $TARGET Enter
tmux -L $SOCKET capture-pane -p -J -t $TARGET -S -200
```

Control keys (no `-l`):
```bash
tmux -L $SOCKET send-keys -t $TARGET C-c   # interrupt
tmux -L $SOCKET send-keys -t $TARGET C-d   # EOF
```

## Interactive tool recipes

- Python REPL:
  ```bash
  $SKILL_DIR/scripts/send-and-wait.sh -L $SOCKET -t $TARGET -c 'PYTHON_BASIC_REPL=1 python -q' -p '>>>'
  $SKILL_DIR/scripts/send-and-wait.sh -L $SOCKET -t $TARGET -c 'print(42)' -p '>>>' -l
  ```
- lldb/gdb: Disable paging with `set pagination off`, break with `C-c`
- Git interactive operations: Use the `/git-interactive` skill, which builds on this one.

## Cleanup

Kill your server when done. All pane output is preserved in the log file.

```bash
# Kill one server
$SKILL_DIR/scripts/stop-session.sh -i ${CLAUDE_SESSION_ID} -s python

# Kill all servers for this session
$SKILL_DIR/scripts/stop-session.sh -i ${CLAUDE_SESSION_ID}
```

Never use tmux `kill-server` directly.
