# git-interactive — maintainer notes

How this skill handles permissions for the rebase editor files, and a decision record for the
removed PermissionRequest hook. Claude Code loads only `SKILL.md`; this file is for humans
maintaining the skill.

## How editor files are written

The interactive-rebase workflow exchanges the rebase todo and commit messages through files under
`/tmp/claude-git-editor-XXXX/` (git's `$EDITOR` points at `scripts/git-editor-claude.sh`). The skill
writes these files with Claude's file tools, not Bash redirection:

- The rebase todo is created with the Write tool at `$CLAUDE_GIT_EDITOR_DIR/todo`.
- Commit messages are edited in place with the Edit tool on the `CONTENT` file.

Both are auto-permitted by static `allowed-tools` rules (`Write(//tmp/claude-git-editor-*/**)`,
`Edit(//tmp/claude-git-editor-*/**)`), so the workflow needs no permission hook and does not depend
on the auto-mode classifier for these writes. File-tool rules match the file path directly, so they
work in every permission mode and inside subagents.

## Why not shell redirection

`allowed-tools` and permission globs cannot cover writes done through shell redirection. Claude Code
parses a Bash command and strips redirections before matching the rule glob, so a command like
`printf … > /tmp/claude-git-editor-XXX/todo` is matched as just `printf` — the redirect target is
invisible to any `Bash(...)` pattern. Redirect targets are checked by a separate working-directory
and path layer that forbids globs in write targets and treats out-of-project `/tmp` paths as a
prompt. (Behavior confirmed against the Claude Code source.)

That is why the todo is written with the Write tool rather than `cat >`/`printf >`: only a file-tool
write — or a hook reading the raw command — can be statically permitted for these paths.

## The removed PermissionRequest hook

This skill used to declare a `PermissionRequest` hook in `SKILL.md` frontmatter that ran
`scripts/permit-git-interactive.sh`, which auto-approved any Bash command touching a
`claude-git-editor-*` temp file, including redirected writes. The hook and script were removed:

- The hook command referenced `$CLAUDE_SKILL_DIR`, which Claude Code does not expand inside
  frontmatter hook commands. It resolved to empty, so the hook never actually ran.
- Switching the todo to the Write tool removed the only redirected write in the normal workflow, so
  the gap the hook covered no longer exists on the happy path.

## Limitations — when this breaks down

The Write-tool approach holds only for the normal, authored-text workflow. It does not cover:

- Auto-classifier failure: anything still left to the classifier will prompt or be denied if the
  classifier declines, or if the session is not in auto mode.
- Write-tool mistakes: if the agent writes to the wrong path, or falls back to Bash redirection out
  of habit instead of the Write tool, the static rule does not apply and the write hits a prompt.
- Dynamic generation: producing the todo (or any editor file) by piping command output —
  `git log … | sed … > todo`, `cmd | cat > …` — cannot use the Write tool directly, and the
  redirection is not statically permittable.

If any of these becomes a real need, the redirection gap returns and another solution will be
required. Options not currently in place: restore the PermissionRequest hook (which reads the raw
command), or add the editor directory to the session's allowed write directories. This is left as a
known gap.

## Restoring the hook

If you restore the hook (for example to support dynamic or redirected writes):

- Re-add the `PermissionRequest` hook block to `SKILL.md` frontmatter.
- Use an absolute command path rather than `$CLAUDE_SKILL_DIR` (for example
  `${HOME}/.claude/skills/git-interactive/scripts/permit-git-interactive.sh`); the variable is not
  expanded in frontmatter hook commands.
- Recover `scripts/permit-git-interactive.sh` from git history.
