#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: start-session.sh -i <id> -s <name>

Start an isolated tmux server for a specific purpose.

Each purpose (python, git, etc.) gets its own socket via -L:
  tmux -L claude/<id>/<name>

Sockets are stored in tmux's default directory (usually /tmp/tmux-<uid>/).
Options:
  -i, --id        Claude session ID
  -s, --name      purpose name (e.g., python, git)
  -m, --monitor   open an Alacritty window attached to the server
  -h, --help      show this help

Output (JSON to stdout):
  {"socket": "...", "session": "...", "target": "...", "log": "..."}

Pane output is automatically logged to ${TMPDIR:-/tmp}/claude-tmux-logs/.

Example:
  ./start-session.sh -i $CLAUDE_SESSION_ID -s python
  ./start-session.sh -i $CLAUDE_SESSION_ID -s git
USAGE
}

instance_id=""
name=""
monitor=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    -i|--id)      instance_id="${2-}"; shift 2 ;;
    -s|--name)    name="${2-}"; shift 2 ;;
    -m|--monitor) monitor=true; shift ;;
    -h|--help)    usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

if ! command -v tmux >/dev/null 2>&1; then
  echo "tmux not found in PATH" >&2
  exit 1
fi

if [[ -z "$instance_id" || -z "$name" ]]; then
  echo "Both -i and -s are required" >&2
  exit 1
fi

# Socket name for -L: claude/<id>/<name>
# tmux stores -L sockets under ${TMUX_TMPDIR:-/tmp}/tmux-$(id -u)/
socket_name="claude/${instance_id}/${name}"
tmux_socket_dir="${TMUX_TMPDIR:-/tmp}/tmux-$(id -u)"
mkdir -p "${tmux_socket_dir}/claude/${instance_id}"

session="claude-${name}-${instance_id}"

# Check if this server is already running
if tmux -L "$socket_name" has-session 2>/dev/null; then
  echo "Server already running for '${name}'" >&2
  exit 1
fi

# Create the session
tmux -L "$socket_name" new-session -d -s "$session"
tmux -L "$socket_name" set-option -g status-left-length 80

# Get actual pane target
pane_target=$(tmux -L "$socket_name" list-panes -t "$session" \
  -F '#{session_name}:#{window_index}.#{pane_index}' | head -1)

# Set up pane logging
log_dir="${TMPDIR:-/tmp}/claude-tmux-logs"
mkdir -p "$log_dir"
log_file="${log_dir}/${session}-$(date +%Y%m%dT%H%M%S).log"
tmux -L "$socket_name" pipe-pane -t "$pane_target" -o "cat >> '${log_file}'"

# Output JSON for Claude to parse (stdout)
printf '{"socket": "%s", "session": "%s", "target": "%s", "log": "%s"}\n' \
  "$socket_name" "$session" "$pane_target" "$log_file"

# Open Alacritty monitoring window (only with -m flag)
if [[ "$monitor" == true && -n "${ALACRITTY_SOCKET:-}" ]]; then
  tmux_bin=$(command -v tmux)
  if alacritty msg --socket "$ALACRITTY_SOCKET" create-window \
       --title "claude: ${name}" \
       -e "$tmux_bin" -L "$socket_name" attach; then
    :
  fi
fi
