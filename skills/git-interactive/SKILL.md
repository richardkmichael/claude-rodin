---
name: git-interactive
description: "Reorganize and reshape git commit history: interactive rebase, split commits, squash, fixup, reorder commits, amend old commits, add -p, rebase --onto. Use this skill when the user wants to clean up commits, rewrite history, or make commits semantically atomic. Uses the tmux skill for terminal sessions."
allowed-tools: "Read(//tmp/claude-git-editor-*/**), Edit(//tmp/claude-git-editor-*/**), Write(//tmp/claude-git-editor-*/**), Bash(git *), Bash(touch /tmp/claude-git-editor-*/*), Bash(rm /tmp/claude-git-editor-*/*), Bash(rmdir /tmp/claude-git-editor-*/), Bash(cp /tmp/claude-git-editor-* /tmp/*), Bash(mktemp */claude-git-editor-*), Bash(rm /tmp/claude-git-editor-*), Bash(*/scripts/git-editor-claude.sh *)"
---

# git-interactive Skill

Reshape and reorganize git commit history. This skill builds on the tmux skill
— use the tmux skill to start a session, then follow these workflows.

The goal is semantically atomic commits: each commit contains one logical change,
described accurately, in a sensible sequence.

## Setup

Start a tmux session using the tmux skill, then set up the editor:

```bash
CLAUDE_GIT_EDITOR_DIR=$(mktemp -d /tmp/claude-git-editor-XXXXXX)
EDITOR_CMD="$CLAUDE_SKILL_DIR/scripts/git-editor-claude.sh -d $CLAUDE_GIT_EDITOR_DIR"
```

Always use the `/tmp/claude-git-editor-XXXXXX` template for `mktemp` — paths under
`/tmp/claude-git-editor-*` are auto-permitted by this skill's allowed-tools. Using
`mktemp -d` without the template produces `$TMPDIR`-based paths that may contain
spaces and will not be auto-permitted.

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
editing. Git calls it with a file path; it copies to `$CLAUDE_GIT_EDITOR_DIR/CONTENT`,
creates `READY`, and waits for `DONE`, then copies back and exits.

Only needed for:
- `reword` — one invocation per reworded commit
- `squash` — one invocation per squash group (to combine messages)
- `edit` stop — when you need to amend a commit message mid-rebase
- `git commit` without `-m`

Wait/signal pattern:
```bash
while [[ ! -f "$CLAUDE_GIT_EDITOR_DIR/READY" ]]; do sleep 0.5; done
# Read $CLAUDE_GIT_EDITOR_DIR/CONTENT, edit it
touch "$CLAUDE_GIT_EDITOR_DIR/DONE"
# Immediately wait for next READY if more invocations expected
```

## Pre-generating the todo list

When you already know what operations to perform, skip the READY/DONE round-trip
for the sequence editor entirely. Write the todo list with the Write tool to
`$CLAUDE_GIT_EDITOR_DIR/todo`, then pass it to git via `cp`.

Use the Write tool, not `cat >`/`printf >` redirection. The todo is authored text,
and writes to `/tmp/claude-git-editor-*` made with a file tool are auto-permitted by
this skill's allowed-tools; shell redirection to the same path is not (see
`README.md`).

Todo to Write at `$CLAUDE_GIT_EDITOR_DIR/todo`:

```
pick abc1234 Add authentication middleware
reword def5678 Fix typo in login handler
squash 9abcdef WIP: forgot error handling
fixup 1234abc debug logging
drop 5678def Temporary test commit
```

Then run the rebase — the sequence editor just copies our file; `GIT_EDITOR` handles
reword/squash:

```bash
GIT_SEQUENCE_EDITOR="cp $CLAUDE_GIT_EDITOR_DIR/todo" \
GIT_EDITOR="$EDITOR_CMD" \
  git rebase -i HEAD~5
```

Git calls `GIT_SEQUENCE_EDITOR <todo-file>`, which becomes
`cp $CLAUDE_GIT_EDITOR_DIR/todo <todo-file>` — instant, no round-trip. If any commits
are `reword` or `squash`, git then invokes `GIT_EDITOR` for those messages only.

Always set both `GIT_SEQUENCE_EDITOR` and `GIT_EDITOR`. If only `GIT_EDITOR` is
set, it also handles the todo list but you lose the ability to bypass it.

## Operations

### Reorder, squash, fixup, drop, reword

Assess the log, build the todo, run with pre-generated sequence:

```bash
git log --oneline -10
```

Write the todo to `$CLAUDE_GIT_EDITOR_DIR/todo` with the Write tool (reorder lines to
reorder commits):

```
pick <hash> <message>
squash <hash> <message>   # fold into previous, combine messages
fixup <hash> <message>    # fold into previous, discard this message
reword <hash> <message>   # keep commit, edit its message
drop <hash> <message>     # discard commit entirely
```

Run the rebase:

```bash
GIT_SEQUENCE_EDITOR="cp $CLAUDE_GIT_EDITOR_DIR/todo" GIT_EDITOR="$EDITOR_CMD" git rebase -i <base>
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

Write the todo to `$CLAUDE_GIT_EDITOR_DIR/todo` with the Write tool — the target
commit marked `edit`, the rest `pick`:

```
edit <hash> <message>
pick <hash> <message>
```

Run the rebase, then amend at the stop:

```bash
GIT_SEQUENCE_EDITOR="cp $CLAUDE_GIT_EDITOR_DIR/todo" GIT_EDITOR="$EDITOR_CMD" git rebase -i <base>

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

These prompts require the response character followed by Enter:
```bash
tmux -L $SOCKET send-keys -t $TARGET e Enter
```

Do not omit `Enter` — the character alone will not submit the response.

Capture the pane after each action to see the current hunk and prompt.
Use the tmux skill to read the pane output.

Editing a hunk in CONTENT (`e`):
- `-` lines: change to ` ` (space) to leave that deletion unstaged
- `+` lines: delete the line entirely to exclude that addition
- Context lines (space-prefixed): do not modify

### Moving commits to a different base (rebase --onto)

```bash
git rebase --onto <newbase> <upstream> [<branch>]

# Example: move last 3 commits onto main
git rebase --onto main HEAD~3 feature
```

### Multi-pass rebase

Split in pass 1, reorder in pass 2. Preferable to one overly complex rebase.
Review `git log --oneline` between passes.

## Conflict resolution

`git status` shows conflicted files and rebase progress. Resolve conflicts, then
`git add <file>` and `git rebase --continue` (may invoke `GIT_EDITOR`).

Tell the user before running `git rebase --abort`.

## Safety

### Never use `git rm` to remove a file from history

`git rm <file>` deletes the working tree copy. To remove a file from a commit
while keeping it locally: use `edit`, then `git reset HEAD~ -- <file>`, then
`git commit --amend --no-edit`, then `git rebase --continue`.

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

Never push these tags (`git push --tags` would include them). Local recovery only.

### When to bail out

If conflicts cascade or the rebase is going sideways, recover using the tag:

```bash
git rebase --abort                              # if rebase is still in progress
git reset --hard claude-was-here/<description>  # restore to pre-rebase state
git tag -d claude-was-here/<description>        # clean up the tag
```

Tell the user before aborting. Show `git reflog` if they want to understand
what happened.

### Other rules

- Show `git reflog` when something goes wrong or when the user asks.
  Do not show it implicitly on success.
- After completing a rebase, show `git log --oneline` so the user can verify
  the result looks correct.
- Never force-push without explicit user instruction.

## Commit message discipline

- When squashing: write a message covering all squashed changes, not just the top one
- Use `fixup` only when the parent commit's message already covers the folded change

## Cleanup

```bash
rm "$CLAUDE_GIT_EDITOR_DIR"/CONTENT "$CLAUDE_GIT_EDITOR_DIR"/READY "$CLAUDE_GIT_EDITOR_DIR"/DONE "$CLAUDE_GIT_EDITOR_DIR"/todo 2>/dev/null; rmdir "$CLAUDE_GIT_EDITOR_DIR"
```

Stop the tmux session using the tmux skill.
