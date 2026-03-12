# Compaction Internals

## How compaction works in the JSONL

Compaction only affects the model's active context — all original entries remain
in the main session JSONL at their original indices. The JSONL file contains
the full history regardless of how many times the context was compacted.

When compaction occurs, two records are added:
1. A `system` record with `"subtype": "compact_boundary"` — this marks the
   boundary. Everything before it was summarized away from the model's context.
2. A `user` record with `isCompactSummary: true` containing "This session is
   being continued from a previous conversation..." — this is the summary the
   model sees going forward.

If a session was compacted multiple times, there are multiple boundaries. The
last one marks where the current active context begins. Everything before it
is the "lost" history that `/history` should search.

The `agent-acompact-*.jsonl` files in `<session-id>/subagents/` contain the
compaction agent's own transcript — useful for reading the summary the model
was given (rather than the original content).

Partial compaction ("Summarize from here") works similarly but only summarizes
a range of messages. The `compact_boundary` record includes a
`logicalParentUuid` pointing to the UUID of the last kept message. Records
between that UUID and the boundary are the summarized range; records before
that UUID remain in the model's active context. The accompanying summary user
record has both `isCompactSummary: true` and a `summarizeMetadata` field with
`messagesSummarized` and `userContext`. The `compactMetadata` on the boundary
also includes `messagesSummarized` and optionally `userContext`.

## Context interruption mechanisms

Four mechanisms affect session context:
- `/compact` creates a boundary within the same JSONL file. All original
  entries remain at their original indices; only the model's active context
  is replaced with a summary.
- "Clear context" (ExitPlanMode approval) creates a new JSONL file. The old
  session stops; the new session's early entries contain "read the full
  transcript at: <path>" pointing to the parent session.
- `/fork` copies all main-chain messages to a new JSONL file. Every record
  in the fork has a `forkedFrom` field with the original session ID. The
  original session continues independently. When searching with `/history all`,
  be aware that forks contain duplicate content from their parent.
- "Summarize from here" (ESC ESC message selector) creates a `compact_boundary`
  in the same JSONL file, but only summarizes a range of messages rather than
  everything before the boundary. The boundary record has a `logicalParentUuid`
  pointing to the last kept message; records between that UUID and the boundary
  are the summarized messages. `session-info.py` exposes this as `is_partial:
  true` and includes the `logicalParentUuid` on the compaction entry.

## Schema reference: inline query example

For queries beyond what the helper scripts support — e.g., filtering by
`stop_reason`, inspecting `logicalParentUuid` chains, extracting
`toolUseResult` content — consult the JSON Schema to discover field names
and structure, then write a short inline Python snippet:

```python
python -c "
import json
with open('session.jsonl') as f:
    for i, line in enumerate(f):
        r = json.loads(line)
        if r.get('type') == 'assistant':
            sr = r.get('message', {}).get('stop_reason')
            if sr == 'max_tokens':
                print(f'[{i}] stop_reason=max_tokens')
"
```

The schema is the authoritative reference for what fields exist on each record
type. Read it before writing custom queries.
