---
name: create-commit-message
description: >
  Write a commit message for the currently staged changes, matching the
  project's conventions. Use when staged changes need a well-formed message --
  on its own, or by an agent after it stages a commit. Reads the staged diff;
  does not stage or commit.
---

# Commit Message for Staged Changes

Produce one commit message describing the currently staged changes, and nothing
else. Do not stage, unstage, or commit -- the caller has already decided what
belongs in this commit. Your input is the staged diff; your output is the
message.

## 1. Read what is staged

```bash
git diff --cached          # the exact changes this message must describe
git diff --cached --stat   # files and scale, at a glance
```

The message must account for everything in the staged diff and nothing that
isn't there. If the staged changes are plainly two unrelated concerns, say so
rather than writing a message that papers over the mix -- that's a sign the
caller should split the commit, not that the message should stretch to cover it.

## 2. Match the project's convention

The existing history is the ground truth for format:

```bash
git log --oneline -20   # subject style: prefixes, length, ticket refs
git log -5              # full bodies: trailers, wrapping, tense
```

Match what you observe -- Conventional Commits (`feat(scope): ...`), subsystem
prefixes (`net: ...`), ticket references (`[PROJ-123] ...`), subject length,
body width, trailer format (`Signed-off-by:`, `Reviewed-by:`, `Fixes:`),
capitalization, punctuation, tense. Honor a `CONTRIBUTING` file or a commit-lint
config if one is present. With no discernible convention, fall back to an
imperative subject under ~72 characters and a body wrapped at 72.

## The subject says what; the body says why

The subject is a one-line summary of the change. The body -- the part that
matters -- is written for the future developer who must modify this code and
needs the intent behind it.

> "The log message that explains your changes is just as important as the
> changes themselves." -- the Git project

A good body does three things, in order:

1. State the problem in the present tense: what is wrong with the current code.
   Write "The parser rejects empty input", not "used to reject"; by convention
   the status quo is the code without this change, so there's no need to write
   "Currently".
2. Justify the change: why the result is better than the status quo.
3. Note discarded alternatives, if any, so a future reader doesn't re-tread
   approaches already ruled out.

Write the body in the imperative mood, as an instruction to the codebase:
"Make the parser accept empty input", not "I made" or "This patch makes". When
the body breaks into distinct points, prefer one bullet per point, each stating
the change and its reason together -- terse, but every bullet carrying its why.

Keep it self-contained: summarize the relevant points of a discussion rather
than linking to a thread or issue that may rot. When referring to another
commit, name it as `abbreviated-hash (subject, date)` -- e.g.
`f86a374 (pack-bitmap.c: fix a memleak, 2015-03-30)`.

Avoid editorializing. State what the change does and why; do not characterize
the work ("comprehensive", "elegant", "long-standing gap") or describe what is
*not* in the commit. Use plain peer language a reviewer would use at a
whiteboard, not academic or business register.

## Output

Present the finished message. Do not run `git commit` -- the caller decides
what to do with it.

## Examples

<examples>

<example>

### Bug fix: problem, then justification

Adapted from a real PostgreSQL commit, with project-specific trailers removed:

```
Improve plpgsql's error messages for incorrect %TYPE and %ROWTYPE.

If one of these constructs referenced a nonexistent object, we'd fall
through to feeding the whole construct to the core parser, which would
reject it with a "syntax error" message.  That's pretty unhelpful and
misleading.  There's no good reason for plpgsql_parse_wordtype and
friends not to throw a useful error for incorrect input, so make them
do that instead of returning NULL.
```

The body states the problem in the present tense -- the fall-through produces a
misleading "syntax error" -- then justifies the fix ("no good reason ... not to
throw a useful error"). It stands on its own, with no link to a discussion.

</example>

<example>

### Refactor with a discarded alternative

Adapted from a real Git commit, with sign-off trailers removed:

```
commit: allow parsing arbitrary buffers with headers

Currently only commits are signed with headers.  However, in the future,
we'll also sign tags with headers as well.  Let's refactor out a
function called parse_buffer_signed_by_header which does exactly that.
In addition, since we'll want to sign things other than commits this
way, let's call the function sign_with_header instead of do_sign_commit.
```

Present-tense problem ("Currently only commits are signed with headers"),
forward-looking justification (tags will need this too), and a discarded
alternative named outright: the function is `sign_with_header`, not the narrower
`do_sign_commit` that the immediate need would suggest.

</example>

<example>

### A short message is right for a simple change

Adapted from a real Linux kernel commit:

```
btrfs: print correct subvol num if active swapfile prevents deletion

Fix the error message in btrfs_delete_subvolume() if we can't delete a
subvolume because it has an active swapfile: we were printing the number
of the parent rather than the target.
```

When the change is simple, a three-line body is the right length: it states the
present-tense problem precisely and stops. Brevity is not a defect -- pad
nothing. The kernel's heavy trailer stack is that project's convention, not a
template to reproduce.

</example>

</examples>
