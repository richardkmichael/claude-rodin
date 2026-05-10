#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: stop-session.sh -i <id> -s <name>
       stop-session.sh -i <id>

Stop a tmux server or all servers for a Claude session.

With -s: kills the named server (socket -L claude/<id>/<name>).
Without -s: kills all servers under claude/<id>/.

Options:
  -i, --id        Claude session ID
  -s, --name      purpose name to kill (omit to kill all)
  -h, --help      show this help

Example:
  ./stop-session.sh -i $CLAUDE_SESSION_ID -s python   # kill one
  ./stop-session.sh -i $CLAUDE_SESSION_ID              # kill all
USAGE
}

instance_id=""
name=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    -i|--id)      instance_id="${2-}"; shift 2 ;;
    -s|--name)    name="${2-}"; shift 2 ;;
    -h|--help)    usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

if ! command -v tmux >/dev/null 2>&1; then
  echo "tmux not found in PATH" >&2
  exit 1
fi

if [[ -z "$instance_id" ]]; then
  echo "-i is required" >&2
  exit 1
fi

tmux_socket_dir="${TMUX_TMPDIR:-/tmp}/tmux-$(id -u)"
socket_dir="${tmux_socket_dir}/claude/${instance_id}"

if [[ -n "$name" ]]; then
  # Kill one server
  socket_name="claude/${instance_id}/${name}"
  if tmux -L "$socket_name" has-session 2>/dev/null; then
    tmux -L "$socket_name" kill-server
  else
    echo "No server running for '${name}'" >&2
    exit 1
  fi
  rm -f "${socket_dir}/${name}"
  echo "Killed '${name}'" >&2
else
  # Kill all servers for this session
  if [[ ! -d "$socket_dir" ]]; then
    echo "No servers found for session '${instance_id}'" >&2
    exit 1
  fi
  killed=0
  for sock in "$socket_dir"/*; do
    [[ -e "$sock" ]] || continue
    sock_basename="$(basename "$sock")"
    socket_name="claude/${instance_id}/${sock_basename}"
    if tmux -L "$socket_name" has-session 2>/dev/null; then
      tmux -L "$socket_name" kill-server
      killed=$((killed + 1))
    fi
    rm -f "$sock"
    echo "Killed '${sock_basename}'" >&2
  done
  if [[ "$killed" -eq 0 ]]; then
    echo "No running servers found" >&2
  fi
  rmdir "$socket_dir" 2>/dev/null || true
fi
