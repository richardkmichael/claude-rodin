---
name: git-interactive
description: "Reorganize and reshape git commit history: rebase -i, split commits, add -p, rebase --onto. Uses the tmux skill for terminal sessions."
allowed-tools: "Read(//tmp/claude-edit-*/**), Edit(//tmp/claude-edit-*/**), Bash(git *), Bash(touch /tmp/claude-edit-*/*), Bash(rm /tmp/claude-edit-*/*), Bash(rm -rf /tmp/claude-edit-*/), Bash(cp /tmp/claude-edit-* /tmp/*), Bash(mktemp *), Bash(*/scripts/git-editor-claude.sh *)"
---

# git-interactive Skill

Reshape and reorganize git commit history. This skill builds on the tmux skill
— invoke `/tmux` first to get a terminal session, then follow these workflows.

The goal is semantically atomic commits: each commit contains one logical change,
described accurately, in a sensible sequence.

## Always assess first

Before planning any operation, review the history:

```bash
git log --oneline [-n N]          # overview of commits
git show <hash>                    # full diff for one commit
git diff <hash>^ <hash>           # same, alternate form
git diff <base>..<tip>            # range of commits
git status                         # current working tree state
```

Reason about what needs changing and why before choosing an operation.
If the intent is ambiguous, show your proposed plan and wait for approval.
If you're confident, proceed — but state what you're about to do.

## The editor protocol (READY/DONE)

`git-editor-claude.sh` is a blocking editor for steps that require message
editing. Git calls it with a file path; it copies to `$EDIT_DIR/CONTENT`,
creates `READY`, and waits for `DONE`, then copies back and exits.

Only needed for:
- `reword` — one invocation per reworded commit
- `squash` — one invocation per squash group (to combine messages)
- `edit` stop — when you need to amend a commit message mid-rebase
- `git commit` without `-m`

Setup:
```bash
EDIT_DIR=$(mktemp -d /tmp/claude-edit-XXXXXX)
EDITOR_CMD="$SKILL_DIR/scripts/git-editor-claude.sh -d $EDIT_DIR"
```

Wait/signal pattern:
```bash
while [[ ! -f "$EDIT_DIR/READY" ]]; do sleep 0.5; done
# Read $EDIT_DIR/CONTENT, edit it
touch "$EDIT_DIR/DONE"
# Immediately wait for next READY if more invocations expected
```

## Pre-generating the todo list

When you already know what operations to perform, skip the READY/DONE round-trip
for the sequence editor entirely. Write the todo to a temp file and pass it
directly to git via `cp`:

```bash
# Build the todo list
TODO=$(mktemp)
cat > "$TODO" <<'EOF'
pick abc1234 Add authentication middleware
reword def5678 Fix typo in login handler
squash 9abcdef WIP: forgot error handling
fixup 1234abc debug logging
drop 5678def Temporary test commit
EOF

# Run rebase: sequence editor just copies our file; GIT_EDITOR handles reword/squash
GIT_SEQUENCE_EDITOR="cp $TODO" \
GIT_EDITOR="$EDITOR_CMD" \
  git rebase -i HEAD~5

rm "$TODO"
```

Git calls `GIT_SEQUENCE_EDITOR <todo-file>`, which becomes `cp $TODO <todo-file>` —
instant, no round-trip. If any commits are `reword` or `squash`, git then invokes
`GIT_EDITOR` for those messages only.

Always set both `GIT_SEQUENCE_EDITOR` and `GIT_EDITOR`. If only `GIT_EDITOR` is
set, it also handles the todo list but you lose the ability to bypass it.

## Operations

### Reorder, squash, fixup, drop, reword

Assess the log, build the todo, run with pre-generated sequence:

```bash
# Review
git log --oneline -10

# Build todo (reorder lines to reorder commits)
TODO=$(mktemp)
cat > "$TODO" <<'EOF'
pick <hash> <message>
squash <hash> <message>   # fold into previous, combine messages
fixup <hash> <message>    # fold into previous, discard this message
reword <hash> <message>   # keep commit, edit its message
drop <hash> <message>     # discard commit entirely
EOF

GIT_SEQUENCE_EDITOR="cp $TODO" GIT_EDITOR="$EDITOR_CMD" git rebase -i <base>
rm "$TODO"
```

For `reword` and `squash`: immediately after the sequence editor exits, wait for
READY — git will invoke `GIT_EDITOR` once per reword/squash group. The combined
message for a squash should describe all the squashed changes, not just one.

### Splitting a commit

Use when a commit contains multiple unrelated changes that should be separate commits.

1. Assess: review the commit's diff and reason about semantic groupings.
   Explain which hunks/files belong to which logical change.

2. Mark the commit `edit` in the todo list.

3. When rebase stops at the commit:
   ```bash
   # Unstage everything (mixed reset — working tree unchanged)
   git reset HEAD~

   # Now the working tree has all the changes, nothing staged
   # Selectively commit in pieces:

   # Option A — stage whole files:
   git add <file1> <file2>
   GIT_EDITOR="$EDITOR_CMD" git commit   # or git commit -m "..."

   # Option B — stage specific hunks:
   GIT_EDITOR="$EDITOR_CMD" git add -p
   # (see "Hunk-wise staging" below)
   GIT_EDITOR="$EDITOR_CMD" git commit

   # Repeat for remaining changes...

   # Continue the rebase
   git rebase --continue
   ```

4. If the split produces commits that still need reordering, do a second rebase
   pass after this one completes (see "Multi-pass rebase").

### Amending a specific historical commit

Use `edit` in the todo to stop at a commit and amend it:

```bash
TODO=$(mktemp)
printf 'edit %s %s\n' "<hash>" "<message>" > "$TODO"
# ... other lines as pick
GIT_SEQUENCE_EDITOR="cp $TODO" GIT_EDITOR="$EDITOR_CMD" git rebase -i <base>
rm "$TODO"

# Git stops at the commit. Make changes:
git add <files>               # add missing changes
git reset HEAD~ -- <file>    # remove a file from this commit (keeps in working tree)
GIT_EDITOR="$EDITOR_CMD" git commit --amend

git rebase --continue
```

### Hunk-wise staging (add -p, reset -p, checkout -p)

Used to selectively stage, unstage, or discard individual hunks.

```bash
# Stage specific hunks
GIT_EDITOR="$EDITOR_CMD" git add -p [<file>]

# Unstage specific hunks (keeps changes in working tree)
GIT_EDITOR="$EDITOR_CMD" git reset -p [<file>]

# Discard specific hunks from working tree (destructive — cannot undo)
GIT_EDITOR="$EDITOR_CMD" git checkout -p [<file>]
```

Hunk prompts and responses:
- `y` — apply to selection (stage/unstage/discard)
- `n` — skip this hunk
- `s` — split into smaller hunks (if possible)
- `e` — edit the hunk manually (opens `GIT_EDITOR`)
- `q` — quit, leaving remaining hunks unchanged

Capture the pane after each action to see the current hunk and prompt:
```bash
tmux -L $SOCKET capture-pane -p -J -t $TARGET -S -50
```

Editing a hunk in CONTENT (`e`):
- `-` lines: change to ` ` (space) to leave that deletion unstaged
- `+` lines: delete the line entirely to exclude that addition
- Context lines (space-prefixed): do not modify

### Moving commits to a different base (rebase --onto)

Use when you want to replay a range of commits onto a different branch or commit.

```bash
# Move commits from <upstream>..<branch> onto <newbase>
git rebase --onto <newbase> <upstream> [<branch>]
```

Examples:
```bash
# Move the last 3 commits from feature onto main
git rebase --onto main HEAD~3 feature

# Move a range between two hashes onto another branch
git rebase --onto <newbase> <first-commit-to-move>^ <last-commit-to-move>
```

After moving, the original commits still exist (visible in reflog) until GC.

### Multi-pass rebase

Some reorganizations require multiple rebase passes — for example, split a commit
in pass 1, then reorder the resulting commits in pass 2. This is normal and
preferable to trying to do everything in one complex rebase.

After each pass, review with `git log --oneline` before starting the next.

## Conflict resolution

When rebase stops with a conflict:

```bash
git status        # shows conflicted files and rebase progress
```

Resolve:
1. Read the conflicted file — look for `<<<<<<<`, `=======`, `>>>>>>>`
2. Edit to keep the correct content, remove all conflict markers
3. `git add <file>`
4. `git rebase --continue` — may invoke `GIT_EDITOR` for the commit message

If the conflict is too complex or the rebase plan was wrong:
```bash
git rebase --abort    # returns to pre-rebase state
```
Always tell the user before aborting.

## Safety

### Recovery tag

Before any non-trivial rebase, create a throwaway tag as an instant recovery point:

```bash
git tag claude-was-here/<description>
```

Generate the description from context — the branch name, operation, or affected
commits (e.g., `claude-was-here/squash-auth-commits`, `claude-was-here/split-config`).
Keep it short and lowercase with hyphens.

If the rebase goes wrong: `git reset --hard claude-was-here/<description>`
returns instantly — no reflog spelunking needed, no data loss.

When done and satisfied with the result: `git tag -d claude-was-here/<description>`

Never push these tags. They are local recovery points only:
```bash
# Safe push — explicitly excludes the namespace
git push                          # fine: tags are not pushed by default
git push --tags                   # NEVER use this — would push claude-was-here/* tags
git push origin 'refs/tags/*'     # NEVER use this either
```

### Other rules

- Never `git rm <file>` to remove from history — it deletes the working tree copy.
  To remove a file from a commit while keeping it locally: use `edit`, then
  `git reset HEAD~ -- <file>`, then `git commit --amend --no-edit`, then
  `git rebase --continue`.
- Show `git reflog` when something goes wrong or when the user asks.
  Do not show it implicitly on success.
- After completing a rebase, show `git log --oneline` so the user can verify
  the result looks correct.
- Never force-push without explicit user instruction.

## Commit message discipline

- Each message describes one logical change
- Present tense imperative ("Add X", "Fix Y", "Remove Z")
- When squashing: write a message covering all the squashed changes, not just one
- `fixup` silently discards the folded commit's message — use it only when the
  parent commit's message already covers the change

## Cleanup

```bash
rm -rf "$EDIT_DIR"
$TMUX_SKILL_DIR/scripts/stop-session.sh -i ${CLAUDE_SESSION_ID} -s git
```
