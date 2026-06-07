# Compaction and context interruption

## Compaction in the JSONL

Compaction only affects the model's active context. All original entries remain in the session JSONL
at their original indices. The file holds the full history no matter how many times the context was
compacted, so `history.py search` finds pre-compaction content directly.

A full compaction adds two records:

1. A `system` record with `"subtype": "compact_boundary"`. Everything before it was summarized away
   from the model's context.
2. A `user` record with `isCompactSummary: true` ("This session is being continued..."). This is the
   summary the model sees going forward.

Multiple compactions mean multiple boundaries; the last marks where the current active context
begins. `history.py search --current` searches before that last boundary, the content no longer
visible to the model, then follows the parent chain.

The `agent-acompact-*.jsonl` files under `<session-id>/subagents/` hold the compaction agent's own
transcript (the summary it produced), if you want the summary rather than the original content.

Partial compaction ("Summarize from here") summarizes only a range. The `compact_boundary` record's
`compactMetadata` carries `messagesSummarized` and `userContext`, present only for partial. The
`logicalParentUuid` on a `compact_boundary` (full and partial) points to the last message before the
boundary. For partial, that is the last kept message: records between it and the boundary are the
summarized range, and records before it remain in active context. The summary user record has
`isCompactSummary: true` and a `summarizeMetadata` field.

## Microcompaction

Microcompaction is a separate, automatic mechanism that reclaims tokens by dropping individual tool
outputs and attachments from the active context, rather than summarizing a span. It writes a
`system` record with `"subtype": "microcompact_boundary"` and a `microcompactMetadata` object:

    { "trigger": "auto", "preTokens": N, "tokensSaved": N,
      "compactedToolIds": ["toolu_...", ...], "clearedAttachmentUUIDs": [...] }

Unlike `compact_boundary`, it has no `logicalParentUuid` and no summary record. The pruned
tool_result records remain in the JSONL at their original indices with full content; only active
context loses them. So `microcompact_boundary` is not a search boundary. Content before it is
still present and findable, and `history.py search --current` ignores it, keying only on
`compact_boundary`.

## Context interruption mechanisms

Four mechanisms change a session's context. Only `/compact` and "Summarize from here" create
`compact_boundary` records.

- `/compact` creates a boundary within the same JSONL file. Originals stay at their indices; only
  active context is replaced with a summary.
- Clear context (ExitPlanMode approval) creates a new JSONL file. The old session stops; the new
  session's early entries contain "read the full transcript at: <path>" pointing to the parent.
- `/fork` copies the main-chain messages to a new JSONL file. Every record carries a `forkedFrom`
  with the original session ID, and the original continues independently. A project-wide search sees
  both, so forks show content duplicated from their parent.
- "Summarize from here" (ESC ESC message selector) creates a `compact_boundary` in the same file,
  summarizing only a range, distinguished by `messagesSummarized` and `userContext` in
  `compactMetadata`.

`history.py search --current` follows clear-context and fork parents, since those files are entirely
out of the current context. A project-wide search reads every session in the project directly, so it
does not need to walk the chain.

## Queries beyond the standard verbs

For queries past what `history.py` covers, such as filtering by `stop_reason`, inspecting
`logicalParentUuid` chains, or extracting `toolUseResult`, consult the bundled JSON Schema for field
names and structure, then write a short inline snippet:

```python
python -c "
import json
with open('session.jsonl') as f:
    for i, line in enumerate(f):
        r = json.loads(line)
        if r.get('type') == 'assistant' and r.get('message', {}).get('stop_reason') == 'max_tokens':
            print(f'[{i}] stop_reason=max_tokens')
"
```

The schema is the authoritative reference for what fields exist on each record type. Read it before
writing custom queries.
