# Interactive Git Operations

Some git commands invoke an editor: `rebase -i`, `commit` without `-m`, or pressing `e` in patch mode (`add -p`, `reset -p`, `checkout -p`). These require `git-editor-claude.sh` with the READY/DONE marker protocol.

## Setup

```bash
# Start a tmux session for git work
./scripts/start-session.sh -s git
# {"socket": "claude-abc123", "session": "git", "target": "git:1.1"}

# Create edit directory and set editor path
EDIT_DIR=$(mktemp -d /tmp/claude-edit-XXXXXX)
EDITOR_CMD="./scripts/git-editor-claude.sh -d $EDIT_DIR"
```

## Workflow: Immediate editor (rebase -i, commit)

```bash
# 1. Send git command with custom editor
tmux -L $SOCKET send-keys -t $TARGET -- "GIT_EDITOR=\"$EDITOR_CMD\" git rebase -i HEAD~3" Enter

# 2. Wait for READY marker (editor has opened)
while [[ ! -f "$EDIT_DIR/READY" ]]; do sleep 0.5; done

# 3. Read and edit $EDIT_DIR/CONTENT

# 4. Signal done
touch "$EDIT_DIR/DONE"

# 5. Clean up
rm -rf "$EDIT_DIR"
```

## Workflow: Patch mode (add -p, reset -p, checkout -p)

Patch mode is interactive—editor only opens when you press `e` followed by Enter to edit a hunk.

```bash
# 1. Start patch mode with custom editor (editor won't open yet)
tmux -L $SOCKET send-keys -t $TARGET -- "GIT_EDITOR=\"$EDITOR_CMD\" git add -p" Enter

# 2. Interact with hunks: y (stage), n (skip), s (split), e (edit), q (quit)
#    Capture pane to see current hunk and prompt
tmux -L $SOCKET capture-pane -p -J -t $TARGET -S -50

# 3. To edit a hunk, send 'e' followed by Enter
tmux -L $SOCKET send-keys -t $TARGET -- e Enter

# 4. Wait for READY marker (editor has now opened)
while [[ ! -f "$EDIT_DIR/READY" ]]; do sleep 0.5; done

# 5. Read and edit $EDIT_DIR/CONTENT (see "Editing CONTENT" below)

# 6. Signal done
touch "$EDIT_DIR/DONE"

# 7. Continue with remaining hunks or clean up when done
```

## Editing CONTENT

### Patch mode (add -p, reset -p, checkout -p)

When editing hunks:
- `-` lines: Change to ` ` (space) to keep deletion unstaged; leave as `-` to stage
- `+` lines: Delete the line to exclude from staging; leave to stage

### git rebase -i

Each line: `<command> <hash> <message>`

Commands: `pick`, `reword`, `edit`, `squash`, `fixup`, `drop`

Reorder lines to reorder commits.

### git commit --amend

Edit the commit message directly. Lines starting with `#` are comments.

## Multiple editor invocations

Some rebase operations invoke the editor more than once, sequentially:

- `reword`: 1 invocation for the todo list + 1 per reworded commit (for its message)
- `squash`: 1 for the todo list + 1 per squash group (to combine messages)

The script handles this automatically — it cleans stale READY/DONE markers at
the start of each invocation. After signaling DONE, immediately wait for the
next READY, then read the new CONTENT, edit it, and signal DONE again.

```bash
# 1. Signal done for the current editor (e.g. the todo list)
touch "$EDIT_DIR/DONE"

# 2. Wait for the next editor invocation
while [[ ! -f "$EDIT_DIR/READY" ]]; do sleep 0.5; done

# 3. Read and edit $EDIT_DIR/CONTENT (now the commit message)

# 4. Signal done — repeat from step 2 if more invocations remain
touch "$EDIT_DIR/DONE"
```

## Conflict resolution

Conflicts don't use the editor. Resolve directly:

1. Read the conflicted file (look for `<<<<<<<`, `=======`, `>>>>>>>`)
2. Edit to resolve
3. `git add <file>` then `git rebase --continue`
