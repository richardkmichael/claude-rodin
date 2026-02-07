---
name: tmux
description: "Use interactive CLIs (git, python, gdb, etc.) with tmux by sending keystrokes and scraping pane output."
allowed-tools: Read(//tmp/claude-edit-*/**), Edit(//tmp/claude-edit-*/**), Bash(tmux:*)
---

# tmux Skill

Use tmux as a programmable terminal multiplexer for interactive work.

## Quickstart

```bash
# Start a session (returns JSON with socket/session/target)
./scripts/start-session.sh -s python
# {"socket": "claude-a1b2c3d4", "session": "python", "target": "python:1.1"}

# Use the returned values for commands
tmux -L claude-a1b2c3d4 send-keys -t python:1.1 -- 'python3 -q' Enter
tmux -L claude-a1b2c3d4 capture-pane -p -J -t python:1.1 -S -200

# Additional session on same socket
./scripts/start-session.sh -L claude-a1b2c3d4 -s git

# Cleanup
tmux -L claude-a1b2c3d4 kill-server
```

After starting, tell the user:
```
To monitor: tmux -L claude-a1b2c3d4 attach
```

## Architecture

Each Claude instance gets an isolated socket (`claude-<random>`):
- Safe to `kill-server` (only affects your socket)
- Multiple sessions per socket if needed
- User can discover all sockets via `find-sessions.sh`

## Scripts

Run with `-h` for help.

| Script | Purpose |
|--------|---------|
| `start-session.sh` | Start session, returns JSON `{socket, session, target}` |
| `find-sessions.sh` | List all claude-* sessions across sockets |
| `wait-for-text.sh` | Poll pane for pattern with timeout |
| `send-and-wait.sh` | Send command and wait for output |
| `git-editor-claude.sh` | Blocking editor for git (READY/DONE marker protocol) |

## Sending input

```bash
# Literal send (avoids shell expansion)
tmux -L $SOCKET send-keys -t $TARGET -l -- "$text"
tmux -L $SOCKET send-keys -t $TARGET Enter

# Control keys
tmux -L $SOCKET send-keys -t $TARGET C-c   # interrupt
tmux -L $SOCKET send-keys -t $TARGET C-d   # EOF
```

## Watching output

```bash
tmux -L $SOCKET capture-pane -p -J -t $TARGET -S -200
```

## Waiting for prompts

```bash
./scripts/wait-for-text.sh -L $SOCKET -t $TARGET -p '^>>>' -T 15
```

## Interactive tool recipes

- Python REPL: Start with `PYTHON_BASIC_REPL=1 python3 -q`, wait for `^>>>`
- lldb/gdb: Disable paging with `set pagination off`, break with `C-c`
- Git with editor: See [interactive-git.md](interactive-git.md)
  Common cases: `rebase -i`, `commit` without `-m`, pressing `e` in patch mode.
  If git appears to wait for an editor, read the instructions and retry with GIT_EDITOR.

## Cleanup

```bash
# Kill entire socket (safe - only affects your instance)
tmux -L $SOCKET kill-server

# Or kill one session
tmux -L $SOCKET kill-session -t $SESSION
```
