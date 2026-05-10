#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: find-sessions.sh [-i <id>] [-q pattern]

List tmux servers started by the tmux skill.

Scans claude/<id>/<name> sockets in the default tmux socket directory.

Options:
  -i, --id      show only servers for this Claude session ID
  -q, --query   case-insensitive filter on socket names
  -h, --help    show this help

Example:
  ./find-sessions.sh                 # list all Claude tmux servers
  ./find-sessions.sh -i abc123       # list servers for one session
  ./find-sessions.sh -q python       # filter to sockets containing "python"
USAGE
}

instance_id=""
query=""
tmux_socket_dir="${TMUX_TMPDIR:-/tmp}/tmux-$(id -u)"
claude_dir="${tmux_socket_dir}/claude"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -i|--id)     instance_id="${2-}"; shift 2 ;;
    -q|--query)  query="${2-}"; shift 2 ;;
    -h|--help)   usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

if ! command -v tmux >/dev/null 2>&1; then
  echo "tmux not found in PATH" >&2
  exit 1
fi

if [[ ! -d "$claude_dir" ]]; then
  echo "No Claude tmux servers found"
  exit 0
fi

found=0

# Iterate session ID dirs (or just the one specified)
if [[ -n "$instance_id" ]]; then
  id_dirs=("${claude_dir}/${instance_id}")
else
  shopt -s nullglob
  id_dirs=("${claude_dir}"/*)
  shopt -u nullglob
fi

for id_dir in "${id_dirs[@]}"; do
  [[ -d "$id_dir" ]] || continue
  id_basename="$(basename "$id_dir")"

  shopt -s nullglob
  sockets=("${id_dir}"/*)
  shopt -u nullglob

  for sock in "${sockets[@]}"; do
    [[ -S "$sock" ]] || continue
    sock_basename="$(basename "$sock")"
    socket_name="claude/${id_basename}/${sock_basename}"

    if [[ -n "$query" ]]; then
      echo "$socket_name" | grep -qi -- "$query" || continue
    fi

    # Check if server is actually running
    if tmux -L "$socket_name" has-session 2>/dev/null; then
      sessions="$(tmux -L "$socket_name" list-sessions \
        -F $'#{session_name}\t#{session_attached}' 2>/dev/null || true)"
      while IFS=$'\t' read -r sess_name attached; do
        attached_label=$([[ "$attached" == "1" ]] && echo "attached" || echo "detached")
        printf '  -L %-40s  %s (%s)\n' "$socket_name" "$sess_name" "$attached_label"
      done <<< "$sessions"
      found=$((found + 1))
    fi
  done
done

if [[ "$found" -eq 0 ]]; then
  echo "No Claude tmux servers found"
else
  echo ""
  echo "To monitor: tmux -L <socket-name> attach"
fi
