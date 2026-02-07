#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: send-and-wait.sh -L socket -t target -c command -p pattern [options]

Send a command to a tmux pane and wait for expected output.

Options:
  -L, --socket    tmux socket name (required)
  -t, --target    tmux target session:window.pane (required)
  -c, --command   command to send (required)
  -p, --pattern   regex pattern to wait for (required)
  -l, --literal   send command literally (-l flag to send-keys)
  -T, --timeout   seconds to wait (default: 15)
  -h, --help      show this help

Example:
  ./send-and-wait.sh -L claude-abc123 -t main:1.1 -c 'print("hello")' -p 'hello' -l
USAGE
}

socket=""
target=""
command=""
pattern=""
literal=false
timeout=15

while [[ $# -gt 0 ]]; do
  case "$1" in
    -L|--socket)  socket="${2-}"; shift 2 ;;
    -t|--target)  target="${2-}"; shift 2 ;;
    -c|--command) command="${2-}"; shift 2 ;;
    -p|--pattern) pattern="${2-}"; shift 2 ;;
    -l|--literal) literal=true; shift ;;
    -T|--timeout) timeout="${2-}"; shift 2 ;;
    -h|--help)    usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

if [[ -z "$socket" || -z "$target" || -z "$command" || -z "$pattern" ]]; then
  echo "socket, target, command, and pattern are required" >&2
  usage
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Send the command
if [[ "$literal" == true ]]; then
  tmux -L "$socket" send-keys -t "$target" -l -- "$command"
  tmux -L "$socket" send-keys -t "$target" Enter
else
  tmux -L "$socket" send-keys -t "$target" -- "$command" Enter
fi

# Wait for the pattern
"$SCRIPT_DIR/wait-for-text.sh" -L "$socket" -t "$target" -p "$pattern" -T "$timeout"
