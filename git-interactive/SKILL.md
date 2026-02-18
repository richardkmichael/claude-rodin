---
name: git-interactive
description: "Perform interactive git operations requiring an editor: rebase -i, add -p, commit, reword, squash. Uses the tmux skill for terminal sessions."
allowed-tools: "Read(//tmp/claude-edit-*/**), Edit(//tmp/claude-edit-*/**), Bash(git *), Bash(touch /tmp/claude-edit-*/*), Bash(rm /tmp/claude-edit-*/*), Bash(*/scripts/git-editor-claude.sh *)"
---

# git-interactive Skill

Perform interactive git operations that require an editor. This skill builds on
the tmux skill — invoke `/tmux` first to get a terminal session, then use this
skill's workflows for the git operations.

## Setup

```bash
# 1. Invoke /tmux to start a git terminal session
#    (use the socket/target/session from its JSON output)

# 2. Create an edit directory for the READY/DONE protocol
EDIT_DIR=$(mktemp -d /tmp/claude-edit-XXXXXX)

# 3. Set both editor variables to the same script
#    GIT_SEQUENCE_EDITOR: fires for the rebase todo list (pick/squash/drop)
#    GIT_EDITOR: fires for commit messages, reword, squash message combining
EDITOR="$SKILL_DIR/scripts/git-editor-claude.sh -d $EDIT_DIR"
```

Always set both `GIT_SEQUENCE_EDITOR` and `GIT_EDITOR` to the same script and
`EDIT_DIR` so both todo-list and message editing work without prompts.

## READY/DONE Protocol

`git-editor-claude.sh` is a blocking editor git invokes as `GIT_EDITOR` /
`GIT_SEQUENCE_EDITOR`. It:

1. Copies git's file to `$EDIT_DIR/CONTENT`
2. Creates `$EDIT_DIR/READY`
3. Waits for `$EDIT_DIR/DONE` (timeout: 300s)
4. Copies `CONTENT` back and exits 0 (git proceeds) or 1 (timeout → git aborts)

Claude's role: detect READY, read and edit CONTENT, signal DONE.

## Workflow: rebase -i

```bash
# Send the rebase command with both editors set
tmux -L $SOCKET send-keys -t $TARGET \
  -l -- "GIT_SEQUENCE_EDITOR=\"$EDITOR\" GIT_EDITOR=\"$EDITOR\" git rebase -i HEAD~3"
tmux -L $SOCKET send-keys -t $TARGET Enter

# Wait for READY (todo list is ready to edit)
while [[ ! -f "$EDIT_DIR/READY" ]]; do sleep 0.5; done

# Read $EDIT_DIR/CONTENT — edit the todo list:
#   pick/reword/edit/squash/fixup/drop on each line
#   Reorder lines to reorder commits

# Signal done
touch "$EDIT_DIR/DONE"

# If reword/squash: immediately wait for next READY (commit message editor)
while [[ ! -f "$EDIT_DIR/READY" ]]; do sleep 0.5; done
# Read, edit commit message in CONTENT, then signal done again
touch "$EDIT_DIR/DONE"
# Repeat until no more READY markers appear
```

## Workflow: commit (without -m)

```bash
tmux -L $SOCKET send-keys -t $TARGET \
  -l -- "GIT_EDITOR=\"$EDITOR\" git commit"
tmux -L $SOCKET send-keys -t $TARGET Enter

while [[ ! -f "$EDIT_DIR/READY" ]]; do sleep 0.5; done
# Edit commit message in $EDIT_DIR/CONTENT
# Lines starting with # are comments — git ignores them
touch "$EDIT_DIR/DONE"
```

## Workflow: add -p (patch mode)

Patch mode is interactive — the editor only opens when you press `e` to edit a hunk.

```bash
# Start patch mode
tmux -L $SOCKET send-keys -t $TARGET \
  -l -- "GIT_EDITOR=\"$EDITOR\" git add -p"
tmux -L $SOCKET send-keys -t $TARGET Enter

# Interact with each hunk — capture pane to see prompt and hunk:
tmux -L $SOCKET capture-pane -p -J -t $TARGET -S -50

# Respond to each hunk:
#   y — stage it       n — skip it
#   s — split hunk     e — edit manually    q — quit

# To edit a hunk manually:
tmux -L $SOCKET send-keys -t $TARGET e
tmux -L $SOCKET send-keys -t $TARGET Enter

while [[ ! -f "$EDIT_DIR/READY" ]]; do sleep 0.5; done
# Edit $EDIT_DIR/CONTENT (see "Editing patch hunks" below)
touch "$EDIT_DIR/DONE"

# Continue with remaining hunks
```

## Editing CONTENT

### Rebase todo list

Each line: `<command> <hash> <summary>`

Commands: `pick`, `reword`, `edit`, `squash`, `fixup`, `drop`

Reorder lines to reorder commits. Delete a line to drop it (or use `drop`).

### Commit messages

Edit freely. Lines starting with `#` are ignored by git. An empty message aborts.

When squashing: the combined message should describe all squashed commits, not
just the top one.

### Patch hunks (add -p)

- `-` lines: change to ` ` (space) to leave the change unstaged; keep as `-` to stage the deletion
- `+` lines: delete the line entirely to exclude it from staging; keep to stage it
- Context lines (space-prefixed): do not modify

## Multiple editor invocations

A single rebase can invoke the editor multiple times sequentially:

- `reword`: todo list + 1 invocation per reworded commit message
- `squash`: todo list + 1 invocation per squash group (to write combined message)

After each `touch "$EDIT_DIR/DONE"`, immediately start waiting for the next
READY. The script cleans stale markers automatically at each invocation start.

Poll with a short sleep loop; do not assume a fixed number of invocations —
capture the pane to check whether rebase has completed.

## Conflict resolution

Conflicts don't use the editor. When a rebase stops with a conflict:

1. `git status` — identifies conflicted files and shows rebase progress
2. Read the conflicted file (`<<<<<<<`, `=======`, `>>>>>>>` markers)
3. Edit to resolve (keep the correct lines, remove all conflict markers)
4. `git add <file>`
5. `git rebase --continue` — may invoke editor again for the commit message

Use `git reflog` after completing a rebase to verify the result looks correct.

## Safety rules

- Never `git rebase --abort` without telling the user first
- Never `git rm <file>` — it deletes from both git and the working tree.
  To remove from git history while preserving the file: use `git rebase -i`,
  stop at the commit with `edit`, then `git reset HEAD~ -- <file>` and
  `git commit --amend --no-edit`, then `git rebase --continue`
- After a destructive rebase, show `git reflog` so the user can verify
- When squashing commits, the final message must describe all the squashed changes

## Cleanup

```bash
rm -rf "$EDIT_DIR"
# Then stop the tmux server:
$TMUX_SKILL_DIR/scripts/stop-session.sh -i ${CLAUDE_SESSION_ID} -s git
```
