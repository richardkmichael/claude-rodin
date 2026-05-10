# Hook Event Architecture

This document describes Claude Code's runtime hook event model — how events are
identified, routed, and logged.  It complements:

- `HOOK_SCHEMAS.md` — payload structure (what fields hooks receive on stdin)
- [Claude Code Hooks reference](https://code.claude.com/docs/en/hooks) — configuration syntax

## Two-Level Event Hierarchy

Hook events have a two-level identity:

1. The hook event type (`PreToolUse`, `PostToolUse`, `PermissionRequest`, etc.)
2. The specific tool that triggered it (`Bash`, `ExitPlanMode`, `Task`, etc.)

### In session JSONL transcripts

Session JSONL `hook_progress` entries expose both levels:

```json
{
  "type": "hook_progress",
  "hookEvent": "PreToolUse",
  "hookName": "PreToolUse:ExitPlanMode",
  "command": "/path/to/hook-script.sh"
}
```

`hookName` follows the format `{hookEvent}:{tool_name}`.  The part after the
colon is the tool name, not the matcher regex from configuration.

### In hook stdin payloads

The compound `hookName` form does not appear in the JSON passed to hook scripts.
Instead, the two levels are separate fields:

```json
{
  "hook_event_name": "PreToolUse",
  "tool_name": "ExitPlanMode",
  ...
}
```

### In settings.json configuration

Hooks subscribe to events using the `matcher` field — a regex that filters by
tool name (for tool events) or by other criteria for non-tool events:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "*",
        "hooks": [{"type": "command", "command": "my-hook.sh"}]
      }
    ]
  }
}
```

The matcher determines whether a hook fires for a given tool invocation.  A
`matcher: "*"` hook fires for all tools; `matcher: "Bash"` fires only for
Bash; `matcher: "Edit|Write"` fires for either.  The matcher value does not
appear in hook stdin or in the `hookName` logged to the session transcript —
only the resolved `tool_name` does.

### Matcher support by event type

| Event                                          | Matcher filters on                                  |
|----------------------------------------------- |---------------------------------------------------- |
| PreToolUse, PostToolUse, PostToolUseFailure, PermissionRequest | tool name (`Bash`, `Edit\|Write`, `mcp__.*`) |
| SessionStart                                   | session source (`startup`, `resume`, `clear`)        |
| Notification                                   | notification type (`permission_prompt`, `idle_prompt`) |
| SessionEnd                                     | exit reason                                          |
| SubagentStart, SubagentStop                    | agent type                                           |


## Observed Event Frequency

From session `32dff3bf` (claude-scratch project, 2026-02-25):

| hookEvent   | hookName sub-category                  | Count |
|------------ |--------------------------------------- |------ |
| PreToolUse  | Bash                                   | 27    |
| PostToolUse | Bash                                   | 7     |
| PreToolUse  | AskUserQuestion                        | 6     |
| PreToolUse  | Task                                   | 4     |
| PreToolUse  | Write, Skill, Grep, ExitPlanMode       | 2 each |
| PostToolUse | Write, Task, Grep, AskUserQuestion     | 2 each |
| PostToolUse | Skill                                  | 1     |


## Lifecycle Gaps

Not all tools complete the full PreToolUse → PostToolUse cycle.

### ExitPlanMode on the "clear context" path

When a user approves a plan with "Yes, clear context and auto-accept edits",
the session resets before the PostToolUse hook fires.  Observed events:

```
101058  PreToolUse         ExitPlanMode  2026-02-25 18:56:45
101059  PermissionRequest  ExitPlanMode  2026-02-25 18:56:45
(no PostToolUse — session reset)
101060  PreToolUse         Glob          2026-02-25 18:56:56  ← new session
```

The user's choice (continue in session vs. clear context) is not recorded in
any hook payload.  To infer it, check whether a new session starts in the same
project directory within seconds of the ExitPlanMode `PermissionRequest`.
