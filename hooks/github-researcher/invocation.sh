#!/usr/bin/env bash
# SubagentStart hook — logs every invocation of the github-researcher subagent.
# Wired with matcher: "github-researcher" so this script only runs for that agent.

set -uo pipefail

INPUT="$(cat)"
LOG_DIR="$HOME/.claude/logs/github-researcher"
LOG_FILE="$LOG_DIR/invocations.jsonl"
mkdir -p "$LOG_DIR"

TS="$(date -u +%FT%TZ)"
AGENT_ID="$(jq -r '.agent_id // empty' <<<"$INPUT")"
AGENT_TYPE="$(jq -r '.agent_type // empty' <<<"$INPUT")"
TRANSCRIPT="$(jq -r '.transcript_path // empty' <<<"$INPUT")"
SESSION="$(jq -r '.session_id // empty' <<<"$INPUT")"

jq -nc \
  --arg ts "$TS" \
  --arg agent_id "$AGENT_ID" \
  --arg agent_type "$AGENT_TYPE" \
  --arg transcript "$TRANSCRIPT" \
  --arg session "$SESSION" \
  '{ts:$ts, agent_id:$agent_id, agent_type:$agent_type, transcript_path:$transcript, session_id:$session}' \
  >> "$LOG_FILE"
exit 0
