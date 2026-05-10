#!/usr/bin/env python3
"""Unified search across a session's compacted content and parent chain.

Usage: python3 auto-search.py [OPTIONS] PATTERN <session.jsonl>

Automates the multi-step scope determination:
1. Finds the last compaction boundary (if any)
2. Searches pre-compaction content in the current session
3. Follows the parent chain (clear-context or fork) and searches those files

This replaces the manual scope.py + search.py + session-info.py workflow
for the common case of "/history [query]".

Options:
  --type TYPE        Record type filter (user, assistant, system, etc.)
  --subtype SUB      System subtype or attachment.type filter
  --tool TOOL        Tool name filter ('*' for any)
  --limit N          Cap total output at N matches (default: unlimited)
  --full             Output full JSON records instead of summaries
  --count            Just print the total count of matching records
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path


# --- Inlined helpers (from scope.py, search.py, session-info.py) ---

def is_compact_boundary(record):
    return (record.get("type") == "system"
            and record.get("subtype") == "compact_boundary")


def extract_text(content):
    """Extract readable text from a message.content value."""
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
            elif btype == "tool_use":
                name = block.get("name", "?")
                inp = block.get("input", {})
                summary = ""
                if isinstance(inp, dict):
                    summary = (inp.get("command") or inp.get("pattern")
                               or inp.get("query") or inp.get("file_path")
                               or inp.get("prompt") or "")
                if summary:
                    parts.append(f"(tool_use {name}): {summary}")
                else:
                    parts.append(f"(tool_use {name})")
            elif btype == "tool_result":
                parts.append("(tool_result)")
            elif btype == "thinking":
                parts.append("(thinking)")
            else:
                parts.append(f"({btype})")
        return "\n".join(parts)
    return str(content) if content else ""


def get_tool_names(record):
    content = record.get("message", {}).get("content", [])
    if not isinstance(content, list):
        return []
    return [
        b.get("name", "")
        for b in content
        if isinstance(b, dict) and b.get("type") == "tool_use"
    ]


def get_tool_input_text(record):
    content = record.get("message", {}).get("content", [])
    if not isinstance(content, list):
        return ""
    parts = []
    for b in content:
        if isinstance(b, dict) and b.get("type") == "tool_use":
            inp = b.get("input", {})
            if isinstance(inp, dict):
                parts.append(json.dumps(inp))
            elif isinstance(inp, str):
                parts.append(inp)
    return " ".join(parts)


def matches_filters(record, args):
    if args.type and record.get("type") != args.type:
        return False
    if args.subtype:
        rec_subtype = record.get("subtype") or (
            record.get("attachment", {}).get("type")
            if isinstance(record.get("attachment"), dict) else None
        )
        if rec_subtype != args.subtype:
            return False
    if args.tool:
        if record.get("type") != "assistant":
            return False
        names = get_tool_names(record)
        if args.tool != "*" and args.tool not in names:
            return False
        if args.tool == "*" and not names:
            return False
    return True


def matches_pattern(record, pattern_re):
    if pattern_re is None:
        return True
    content = record.get("message", {}).get("content", "")
    text = extract_text(content)
    if pattern_re.search(text):
        return True
    if record.get("type") == "assistant":
        tool_text = get_tool_input_text(record)
        if pattern_re.search(tool_text):
            return True
    attachment = record.get("attachment")
    if isinstance(attachment, dict):
        if pattern_re.search(json.dumps(attachment)):
            return True
    sys_content = record.get("content", "")
    if isinstance(sys_content, str) and pattern_re.search(sys_content):
        return True
    return False


def get_content(record):
    return (record.get("message", {}).get("content")
            or record.get("content")
            or record.get("attachment", ""))


def format_summary(idx, record):
    rtype = record.get("type", "?")
    role = record.get("message", {}).get("role", "")
    role_str = f" {role}" if role else ""
    text = extract_text(get_content(record))[:300].replace("\n", " ")
    return f"[{idx}] {rtype}{role_str}: {text}"


def find_parent_path(records):
    """Look for 'read the full transcript at: <path>' in first 5 entries."""
    for record in records[:5]:
        content = record.get("message", {}).get("content", "")
        text = extract_text(content) if not isinstance(content, str) else content
        match = re.search(r"read the full transcript at: (\S+\.jsonl)", text)
        if match:
            return match.group(1)
    return None


def load_records(fpath):
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


# --- Core logic ---

def find_last_boundary(fpath):
    """Find the 0-based index of the last compact_boundary record."""
    last = None
    with open(fpath) as f:
        for idx, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if is_compact_boundary(record):
                last = idx
    return last


def collect_parent_files(fpath, visited=None):
    """Walk the parent chain and return list of JSONL paths (oldest first)."""
    if visited is None:
        visited = set()

    fpath = str(Path(fpath).resolve())
    if fpath in visited:
        return []
    visited.add(fpath)

    records = load_records(fpath)
    parent_path = find_parent_path(records)

    # Check for fork parent
    if not parent_path and records:
        if isinstance(records[0].get("forkedFrom"), dict):
            forked_from = records[0]["forkedFrom"].get("sessionId")
            if forked_from:
                candidate = Path(fpath).parent / f"{forked_from}.jsonl"
                if candidate.is_file():
                    parent_path = str(candidate)

    if parent_path and os.path.isfile(parent_path):
        ancestors = collect_parent_files(parent_path, visited)
        ancestors.append(parent_path)
        return ancestors

    return []


def search_file(fpath, pattern_re, args, before=None, label=None):
    """Search a single file, streaming line by line. Returns match count."""
    if label:
        print(f"=== {label} ===")

    count = 0
    try:
        f = open(fpath)
    except FileNotFoundError:
        print(f"File not found: {fpath}", file=sys.stderr)
        return 0

    for idx, raw in enumerate(f):
        raw = raw.strip()
        if not raw:
            continue
        if before is not None and idx >= before:
            continue

        try:
            record = json.loads(raw)
        except json.JSONDecodeError:
            continue

        if not matches_filters(record, args):
            continue
        if not matches_pattern(record, pattern_re):
            continue

        count += 1

        if args.count:
            continue

        if args.full:
            print(f"=== [{idx}] ===")
            print(json.dumps(record, indent=2))
        else:
            print(format_summary(idx, record))

        if args.limit is not None and count >= args.limit:
            break

    f.close()
    return count


def main():
    parser = argparse.ArgumentParser(
        description="Search compacted content and parent chain for a session",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("pattern", help="Regex pattern to search for (case-insensitive)")
    parser.add_argument("session_file", help="Path to the current session's JSONL file")
    parser.add_argument("--type", help="Record type filter")
    parser.add_argument("--subtype", help="System subtype or attachment.type filter")
    parser.add_argument("--tool", help="Tool name filter ('*' for any)")
    parser.add_argument("--limit", type=int, help="Cap total output at N matches")
    parser.add_argument("--full", action="store_true", help="Output full JSON records")
    parser.add_argument("--count", action="store_true", help="Print total match count")

    args = parser.parse_args()
    pattern_re = re.compile(args.pattern, re.IGNORECASE)

    session_file = args.session_file
    if not os.path.isfile(session_file):
        print(f"File not found: {session_file}", file=sys.stderr)
        sys.exit(2)

    total = 0
    remaining_limit = args.limit

    # Step 1: Search pre-compaction content in current session
    boundary = find_last_boundary(session_file)
    if boundary is not None:
        count = search_file(
            session_file, pattern_re, args,
            before=boundary,
            label=f"Pre-compaction content (before line {boundary})",
        )
        total += count
        if remaining_limit is not None:
            remaining_limit -= count
            if remaining_limit <= 0:
                if args.count:
                    print(total)
                return

    # Step 2: Search parent chain (oldest first)
    parent_files = collect_parent_files(session_file)
    for pfile in parent_files:
        if remaining_limit is not None:
            args.limit = remaining_limit
        count = search_file(
            pfile, pattern_re, args,
            label=f"Parent session: {pfile}",
        )
        total += count
        if remaining_limit is not None:
            remaining_limit -= count
            if remaining_limit <= 0:
                break

    if args.count:
        print(total)
    elif total == 0:
        if boundary is None and not parent_files:
            print("No compaction boundary found and no parent sessions — "
                  "the entire conversation is in context.")
        else:
            print("No matches found.")


if __name__ == "__main__":
    main()
