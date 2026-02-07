#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: start-session.sh [-L socket] [-s session] [-n window] [-c dir]

Start a new tmux session on an isolated socket.

If no socket is specified, generates a unique one (claude-XXXXXXXX).
Use the same socket name for related sessions within one Claude instance.

Options:
  -L, --socket    socket name (default: generates claude-<random>)
  -s, --session   session name (default: main)
  -n, --window    initial window name (default: shell)
  -c, --dir       starting directory (default: current)
  -h, --help      show this help

Output (JSON to stdout):
  {"socket": "...", "session": "...", "target": "..."}

Example:
  # First session (auto-generates socket)
  ./start-session.sh -s python

  # Additional session on same socket
  ./start-session.sh -L claude-a1b2c3d4 -s git

Monitor your sessions:
  tmux -L <socket> attach
  (Ctrl-b s to list sessions, Ctrl-b d to detach)
USAGE
}

socket=""
session="main"
window="shell"
start_dir=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    -L|--socket)  socket="${2-}"; shift 2 ;;
    -s|--session) session="${2-}"; shift 2 ;;
    -n|--window)  window="${2-}"; shift 2 ;;
    -c|--dir)     start_dir="${2-}"; shift 2 ;;
    -h|--help)    usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

if ! command -v tmux >/dev/null 2>&1; then
  echo "tmux not found in PATH" >&2
  exit 1
fi

# Generate socket name if not provided
if [[ -z "$socket" ]]; then
  random_suffix=$(head -c 4 /dev/urandom | xxd -p)
  socket="claude-${random_suffix}"
fi

# Check if session already exists on this socket
if tmux -L "$socket" has-session -t "$session" 2>/dev/null; then
  echo "Session '$session' already exists on socket '$socket'" >&2
  echo "Use a different session name or kill the existing session" >&2
  exit 1
fi

# Build and run tmux command
cmd=(tmux -L "$socket" new-session -d -s "$session" -n "$window")
if [[ -n "$start_dir" ]]; then
  cmd+=(-c "$start_dir")
fi
"${cmd[@]}"

# Get actual pane target (window index depends on tmux config)
pane_target=$(tmux -L "$socket" list-panes -t "$session" -F '#{session_name}:#{window_index}.#{pane_index}' | head -1)

# Output JSON for Claude to parse (stdout)
printf '{"socket": "%s", "session": "%s", "target": "%s"}\n' "$socket" "$session" "$pane_target"

# Human-readable info (stderr)
cat >&2 <<EOF

Started session '$session' on socket '$socket'

To monitor: tmux -L $socket attach -t $session
To capture: tmux -L $socket capture-pane -p -J -t $pane_target -S -200
EOF
