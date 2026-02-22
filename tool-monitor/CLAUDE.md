# Tool Monitor Description

This Claude tool implements four Claude Code hooks `PreToolUse`, `PostToolUse`, `PostToolUseFailure`,
and `PermissionRequest` to store hook payloads in SQLite for future analysis of Claude's tool usage.

The hooks implemented do not *alter* tool calls, they simply return exit code 0 (success) to be
transparent and only capture the hook payload.  In this hook usage, `stdout` is shown to the Claude
Code user in Claude Code's "transcript mode" (CTRL-R).

# Resources

- Overview: @./README.md
- `tool-monitor` hook information: @./HOOK_SCHEMAS.md
- Claude Code Hooks reference documentation: https://code.claude.com/docs/en/hooks
  - Review this documentation when adding new features, debugging, or answering questions about Hooks, generally
  - Official documentation has known inaccuracies — always verify hook schemas empirically
    against real captured payloads
