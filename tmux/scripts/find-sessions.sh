#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: find-sessions.sh [-L socket] [-q pattern]

List tmux sessions. By default scans all claude-* sockets.

Options:
  -L, --socket  specific socket name (default: scan all claude-* sockets)
  -q, --query   case-insensitive filter on session names
  -h, --help    show this help

Example:
  ./find-sessions.sh              # list all Claude sessions across sockets
  ./find-sessions.sh -L claude-abc123  # list sessions on specific socket
  ./find-sessions.sh -q python    # filter to sessions containing "python"
USAGE
}

socket=""
query=""
socket_dir="${TMUX_TMPDIR:-/tmp}/tmux-$(id -u)"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -L|--socket) socket="${2-}"; shift 2 ;;
    -q|--query)  query="${2-}"; shift 2 ;;
    -h|--help)   usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

if ! command -v tmux >/dev/null 2>&1; then
  echo "tmux not found in PATH" >&2
  exit 1
fi

list_sessions() {
  local sock_name="$1"

  if ! sessions="$(tmux -L "$sock_name" list-sessions -F $'#{session_name}\t#{session_attached}' 2>/dev/null)"; then
    return 1
  fi

  if [[ -n "$query" ]]; then
    sessions="$(printf '%s\n' "$sessions" | grep -i -- "$query" || true)"
  fi

  if [[ -z "$sessions" ]]; then
    return 0
  fi

  printf '%s\n' "$sessions" | while IFS=$'\t' read -r name attached; do
    attached_label=$([[ "$attached" == "1" ]] && echo "attached" || echo "detached")
    printf '  %s: %s (%s)\n' "$sock_name" "$name" "$attached_label"
  done
}

# Single socket mode
if [[ -n "$socket" ]]; then
  echo "Sessions on socket '$socket':"
  if ! list_sessions "$socket"; then
    echo "  (no sessions or socket not running)"
  fi
  echo ""
  echo "To monitor: tmux -L $socket attach"
  exit 0
fi

# Scan all claude-* sockets
if [[ ! -d "$socket_dir" ]]; then
  echo "No Claude sessions found (socket directory doesn't exist)"
  exit 0
fi

shopt -s nullglob
sockets=("$socket_dir"/claude-*)
shopt -u nullglob

if [[ "${#sockets[@]}" -eq 0 ]]; then
  echo "No Claude sessions found"
  exit 0
fi

echo "Claude sessions:"
found_any=false
for sock_path in "${sockets[@]}"; do
  if [[ ! -S "$sock_path" ]]; then
    continue
  fi
  sock_name="$(basename "$sock_path")"
  if list_sessions "$sock_name"; then
    found_any=true
  fi
done

if [[ "$found_any" == false ]]; then
  echo "  (none)"
fi

echo ""
echo "To monitor a socket: tmux -L <socket-name> attach"
