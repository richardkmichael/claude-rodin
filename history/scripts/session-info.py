#!/usr/bin/env python3
"""Show structural info for a session and its chain (parent/child sessions).

Usage: python3 session-info.py <session.jsonl>

Detects compaction boundaries, clear-context links, and fork relationships.
Follows the chain recursively and outputs JSON.

Cross-session links come in two forms:
- Clear-context: text pointer "read the full transcript at: <path>" in the
  child's early entries. The parent's JSONL has no marker.
- Fork: `forkedFrom` field on every record in the fork, containing the
  parent's sessionId and each record's original messageUuid.
"""

import json
import os
import re
import sys
from pathlib import Path


def load_records(fpath):
    """Load all JSON records from a JSONL file."""
    records = []
    with open(fpath) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def extract_text(content):
    """Get searchable text from a message.content value."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(block.get("text", ""))
        return " ".join(parts)
    return ""


def find_parent_path(records):
    """Look for 'read the full transcript at: <path>' in first 5 entries."""
    for record in records[:5]:
        content = record.get("message", {}).get("content", "")
        text = extract_text(content)
        match = re.search(r"read the full transcript at: (\S+\.jsonl)", text)
        if match:
            return match.group(1)
    return None


def find_compact_subagents(fpath):
    """Find compaction subagent files for a session."""
    session_id = Path(fpath).stem
    subagent_dir = Path(fpath).parent / session_id / "subagents"
    if not subagent_dir.is_dir():
        return []
    return sorted(
        str(p) for p in subagent_dir.glob("agent-acompact-*.jsonl")
    )


def analyze_session(fpath):
    """Analyze a single session file (no recursion)."""
    records = load_records(fpath)
    session_id = Path(fpath).stem

    # Find compaction boundary indices (system records with compact_boundary subtype)
    compaction_indices = []
    for idx, record in enumerate(records):
        if (record.get("type") == "system"
                and record.get("subtype") == "compact_boundary"):
            compaction_indices.append(idx)

    # Build compaction entries with segment sizes between boundaries
    segment_ends = compaction_indices[1:] + [len(records)]
    compactions = [
        {"index": boundary_idx, "entries_after": end - boundary_idx - 1}
        for boundary_idx, end in zip(compaction_indices, segment_ends)
    ]

    timestamps = [r.get("timestamp") for r in records if r.get("timestamp")]
    date_range = [timestamps[0], timestamps[-1]] if timestamps else [None, None]

    parent_path = find_parent_path(records)

    # Detect fork: first record has forkedFrom with the parent session ID
    forked_from = None
    if records and isinstance(records[0].get("forkedFrom"), dict):
        forked_from = records[0]["forkedFrom"].get("sessionId")

    return {
        "session_id": session_id,
        "file": str(fpath),
        "entry_count": len(records),
        "date_range": date_range,
        "compactions": compactions,
        "parent_path": parent_path,
        "forked_from_session": forked_from,
    }


def resolve_session(fpath, direction="both", depth=0, visited=None):
    """Resolve the full session chain recursively."""
    if visited is None:
        visited = set()

    fpath = str(Path(fpath).resolve())

    if fpath in visited or not os.path.isfile(fpath) or depth > 10:
        return None

    visited.add(fpath)
    info = analyze_session(fpath)

    # Add compaction subagent paths
    subagent_files = find_compact_subagents(fpath)
    for i, compaction in enumerate(info["compactions"]):
        if i < len(subagent_files):
            compaction["summary_file"] = subagent_files[i]

    # Resolve parent (clear-context or fork)
    parent = None
    if direction in ("both", "up"):
        parent_path = info.get("parent_path")
        forked_from = info.get("forked_from_session")
        if parent_path and os.path.isfile(parent_path):
            parent = resolve_session(parent_path, "up", depth + 1, visited)
        elif forked_from:
            # Find the parent session's JSONL by session ID
            fork_parent_path = Path(fpath).parent / f"{forked_from}.jsonl"
            if fork_parent_path.is_file():
                parent = resolve_session(
                    str(fork_parent_path), "up", depth + 1, visited
                )

    # Resolve children
    children = []
    if direction in ("both", "down") and depth < 3:
        session_id = info["session_id"]
        session_dir = Path(fpath).parent
        for sibling in sorted(session_dir.glob("*.jsonl")):
            sibling_str = str(sibling.resolve())
            if sibling_str == fpath:
                continue
            # Check first 5 lines for a reference to our session
            try:
                with open(sibling) as f:
                    head = "".join(f.readline() for _ in range(5))
                if session_id in head:
                    child = resolve_session(sibling_str, "down", depth + 1, visited)
                    if child is not None:
                        children.append(child)
            except (OSError, UnicodeDecodeError):
                continue

    # Determine relationship type for this session
    link_type = None
    if info.get("forked_from_session"):
        link_type = "fork"
    elif info.get("parent_path"):
        link_type = "clear-context"

    # Remove internal fields, add resolved links
    info.pop("parent_path", None)
    info.pop("forked_from_session", None)
    info["link_type"] = link_type
    info["parent"] = parent
    info["children"] = children

    return info


def main():
    if len(sys.argv) != 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__.strip())
        sys.exit(0 if "--help" in sys.argv or "-h" in sys.argv else 2)

    fpath = sys.argv[1]
    if not os.path.isfile(fpath):
        print(f"File not found: {fpath}", file=sys.stderr)
        sys.exit(2)

    result = resolve_session(fpath)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
