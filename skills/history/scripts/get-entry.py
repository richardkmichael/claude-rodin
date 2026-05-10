#!/usr/bin/env python3
"""Get full content of entries from a session JSONL by 0-based index.

Usage: python3 get-entry.py <session.jsonl> <index> [index ...]

Indices come from user-messages.py or search.py output.

Example: python3 get-entry.py session.jsonl 228 469 652
"""

import json
import sys


def extract_content(content):
    """Extract readable content, summarizing non-text blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type", "")
            if btype == "text":
                parts.append(block.get("text", ""))
            elif btype == "tool_result":
                parts.append(f"(tool_result id={block.get('tool_use_id', '?')})")
            elif btype == "tool_use":
                parts.append(f"(tool_use name={block.get('name', '?')})")
            elif btype == "thinking":
                parts.append("(thinking)")
            else:
                parts.append(f"({btype})")
        return "\n".join(parts)
    return f"(content type: {type(content).__name__})"


def get_content(record):
    """Get the content value from a record, checking message, top-level, then attachment."""
    return (record.get("message", {}).get("content")
            or record.get("content")
            or record.get("attachment", ""))


def main():
    if len(sys.argv) < 3 or sys.argv[1] in ("-h", "--help"):
        print(__doc__.strip())
        sys.exit(0 if "--help" in sys.argv or "-h" in sys.argv else 2)

    fpath = sys.argv[1]
    try:
        raw_indices = [int(a) for a in sys.argv[2:]]
    except ValueError:
        print("Error: indices must be integers", file=sys.stderr)
        sys.exit(2)

    indices = list(dict.fromkeys(raw_indices))

    try:
        with open(fpath) as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"File not found: {fpath}", file=sys.stderr)
        sys.exit(2)

    for idx in indices:
        if idx < 0 or idx >= len(lines):
            print(f"Index {idx} out of range (file has {len(lines)} lines)", file=sys.stderr)
            continue
        raw = lines[idx].strip()
        if not raw:
            continue
        try:
            record = json.loads(raw)
        except json.JSONDecodeError:
            print(f"Invalid JSON at index {idx}", file=sys.stderr)
            continue
        rtype = record.get("type", "?")
        role = record.get("message", {}).get("role", "-")
        text = extract_content(get_content(record))
        print(f"=== [{idx}] type={rtype} role={role} ===")
        print(text)


if __name__ == "__main__":
    main()
