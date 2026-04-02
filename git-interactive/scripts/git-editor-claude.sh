#!/usr/bin/env bash
set -euo pipefail

# Blocking editor for git's file-driven workflow.
#
# Git expects the editor to:
#   1. Receive a file path as argument
#   2. Block until editing is complete
#   3. Exit 0 on success (git reads the edited file and proceeds)
#   4. Exit non-zero to abort (git cancels the operation: commit, rebase, etc.)
#
# This script implements a READY/DONE marker protocol so Claude can edit
# the file via Read/Edit tools while the script blocks.
#
# Why copy to CONTENT instead of editing git's file directly?
#   Git's temp file paths vary (.git/addp-hunk-edit.diff, /tmp/git-commit-XXX, etc.)
#   Copying to a predictable location (/tmp/claude-git-editor-*/) allows the skill's
#   allowed-tools pattern to auto-permit Read/Edit without prompts.

usage() {
  cat <<'USAGE'
Usage: git-editor-claude.sh -d <edit-dir> [options] <file>

Blocking editor for git (READY/DONE marker protocol).

Options:
  -d, --dir DIR      Edit session directory (required)
  -T, --timeout N    Seconds to wait for DONE marker (default: 300)
  -h, --help         Show this help

Protocol:
  1. Copies <file> to $EDIT_DIR/CONTENT
  2. Creates $EDIT_DIR/READY marker
  3. Waits for $EDIT_DIR/DONE marker (or timeout)
  4. Copies edited CONTENT back to <file>
  5. Exits 0 (success) or 1 (timeout/error)

Git behavior on exit:
  Exit 0: Git reads the edited file and proceeds with the operation
  Exit 1: Git aborts the operation (commit cancelled, rebase aborted, etc.)

Example:
  EDIT_DIR=$(mktemp -d /tmp/claude-git-editor-XXXXXX)
  GIT_EDITOR="git-editor-claude.sh -d $EDIT_DIR" git rebase -i HEAD~3
  # Monitor $EDIT_DIR/READY, edit $EDIT_DIR/CONTENT, touch $EDIT_DIR/DONE
USAGE
}

edit_dir=""
timeout=300
file=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    -d|--dir)      edit_dir="${2-}"; shift 2 ;;
    -T|--timeout)  timeout="${2-}"; shift 2 ;;
    -h|--help)     usage; exit 0 ;;
    -*)            echo "Unknown option: $1" >&2; usage; exit 1 ;;
    *)             file="$1"; shift ;;
  esac
done

if [[ -z "$edit_dir" ]]; then
  echo "Error: Edit directory required (-d)" >&2
  usage
  exit 1
fi

if [[ -z "$file" ]]; then
  echo "Error: No file specified" >&2
  usage
  exit 1
fi

if [[ ! -f "$file" ]]; then
  echo "Error: File does not exist: $file" >&2
  exit 1
fi

if ! [[ "$timeout" =~ ^[0-9]+$ ]]; then
  echo "Error: Timeout must be an integer" >&2
  exit 1
fi

# Create edit directory
mkdir -p "$edit_dir"

# Clean up any stale markers
rm -f "$edit_dir/READY" "$edit_dir/DONE"

# Copy file to known location (allows allowed-tools pattern to match)
cp "$file" "$edit_dir/CONTENT"

# Cleanup on exit
cleanup() {
  rm -f "$edit_dir/READY" "$edit_dir/DONE"
}
trap cleanup EXIT

# Signal ready
touch "$edit_dir/READY"
echo "git-editor-claude: EDIT_DIR=$edit_dir" >&2
echo "git-editor-claude: Waiting for $edit_dir/DONE (timeout: ${timeout}s)" >&2

# Wait for DONE marker
start_epoch=$(date +%s)
deadline=$((start_epoch + timeout))

while true; do
  if [[ -f "$edit_dir/DONE" ]]; then
    cp "$edit_dir/CONTENT" "$file"
    echo "git-editor-claude: Edit complete, exiting 0 (git proceeds)" >&2
    exit 0
  fi

  now=$(date +%s)
  if (( now >= deadline )); then
    echo "git-editor-claude: Timeout, exiting 1 (git aborts)" >&2
    exit 1
  fi

  sleep 0.5
done
