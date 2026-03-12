#!/usr/bin/env python3
"""Search session JSONL files with structured filters.

Usage: python3 search.py [OPTIONS] [PATTERN] FILE [FILE...]

Filters (narrow which records to search):
  --type TYPE        Record type: user, assistant, system, attachment, progress
  --subtype SUB      System subtype (e.g. compact_boundary, api_error) or
                     attachment subtype (e.g. plan_mode_exit, hook_success)
  --tool TOOL        Tool name — matches assistant records containing a
                     tool_use block with this name (e.g. Bash, Read, Grep)
  --before N         Only search lines with index < N (0-based).
                     Use with scope.py to limit to pre-compaction content.
  --after N          Only search lines with index > N (0-based).
  --limit N          Cap output at N matches (default: unlimited).

Output:
  --field PATH       Dotted path to extract from matching records instead of
                     content summary (e.g. "message.usage", "attachment.type")
  --full             Output full JSON record instead of content summary
  --count            Just print the count of matching records

PATTERN is a regex (case-insensitive). If omitted, all records matching the
filters are returned.

Examples:
  # User messages mentioning "caching" before compaction boundary
  BOUNDARY=$(python3 scope.py session.jsonl)
  python3 search.py --type user --before $BOUNDARY "caching" session.jsonl

  # All Bash tool invocations containing "git"
  python3 search.py --tool Bash "git" session.jsonl

  # Extract token usage from all assistant records
  python3 search.py --type assistant --field message.usage session.jsonl

  # Count plan_mode_exit attachments
  python3 search.py --subtype plan_mode_exit --count session.jsonl

  # List all tool names used in a session
  python3 search.py --tool '*' --field _tool_names session.jsonl
"""

import argparse
import json
import re
import sys


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
    """Extract tool names from an assistant record's content blocks."""
    content = record.get("message", {}).get("content", [])
    if not isinstance(content, list):
        return []
    return [
        b.get("name", "")
        for b in content
        if isinstance(b, dict) and b.get("type") == "tool_use"
    ]


def get_tool_input_text(record):
    """Extract searchable text from tool_use input fields."""
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


def resolve_field(record, dotted_path):
    """Resolve a dotted field path like 'message.usage' against a record."""
    # Special virtual fields
    if dotted_path == "_tool_names":
        return get_tool_names(record)

    parts = dotted_path.split(".")
    obj = record
    for part in parts:
        if isinstance(obj, dict):
            obj = obj.get(part)
        else:
            return None
    return obj


def matches_filters(record, args):
    """Check if a record matches all specified filters."""
    if args.type and record.get("type") != args.type:
        return False

    if args.subtype:
        rec_subtype = record.get("subtype") or (
            record.get("attachment", {}).get("type") if isinstance(record.get("attachment"), dict) else None
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
    """Check if a record's searchable text matches the pattern."""
    if pattern_re is None:
        return True

    # Search message.content text
    content = record.get("message", {}).get("content", "")
    text = extract_text(content)
    if pattern_re.search(text):
        return True

    # Search tool input for assistant records
    if record.get("type") == "assistant":
        tool_text = get_tool_input_text(record)
        if pattern_re.search(tool_text):
            return True

    # Search attachment content
    attachment = record.get("attachment")
    if isinstance(attachment, dict):
        if pattern_re.search(json.dumps(attachment)):
            return True

    # Search system content field
    sys_content = record.get("content", "")
    if isinstance(sys_content, str) and pattern_re.search(sys_content):
        return True

    return False


def get_content(record):
    """Get the content value from a record, checking message, top-level, then attachment."""
    return (record.get("message", {}).get("content")
            or record.get("content")
            or record.get("attachment", ""))


def format_summary(idx, record):
    """Format a record as a one-line summary."""
    rtype = record.get("type", "?")
    role = record.get("message", {}).get("role", "")
    role_str = f" {role}" if role else ""

    text = extract_text(get_content(record))[:300].replace("\n", " ")
    return f"[{idx}] {rtype}{role_str}: {text}"


def main():
    parser = argparse.ArgumentParser(
        description="Search session JSONL files with structured filters",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  %(prog)s --type user "caching" session.jsonl
  %(prog)s --tool Bash "git" session.jsonl
  %(prog)s --type assistant --field message.usage session.jsonl
  %(prog)s --subtype plan_mode_exit --count session.jsonl
  %(prog)s --tool '*' --field _tool_names session.jsonl""",
    )

    parser.add_argument("--type", help="Record type: user, assistant, system, attachment, progress")
    parser.add_argument("--subtype", help="System subtype or attachment.type")
    parser.add_argument("--tool", help="Tool name (matches assistant tool_use blocks, '*' for any)")
    parser.add_argument("--before", type=int, help="Only lines with index < N")
    parser.add_argument("--after", type=int, help="Only lines with index > N")
    parser.add_argument("--limit", type=int, help="Cap output at N matches")
    parser.add_argument("--field", help="Dotted path to extract (e.g. message.usage)")
    parser.add_argument("--full", action="store_true", help="Output full JSON records")
    parser.add_argument("--count", action="store_true", help="Just print match count")
    parser.add_argument("args", nargs="+", help="[PATTERN] FILE [FILE...]")

    args = parser.parse_args()

    # Separate pattern from files
    remaining = args.args
    files = [a for a in remaining if a.endswith(".jsonl")]
    non_files = [a for a in remaining if not a.endswith(".jsonl")]

    if not files:
        parser.error("No .jsonl files specified")

    if len(non_files) > 1:
        parser.error(f"Expected at most one PATTERN, got {len(non_files)}: {non_files}")

    pattern_str = non_files[0] if non_files else None
    pattern_re = re.compile(pattern_str, re.IGNORECASE) if pattern_str else None

    multi = len(files) > 1
    total_count = 0

    for fpath in files:
        if multi:
            print(f"=== {fpath} ===")

        try:
            f = open(fpath)
        except FileNotFoundError:
            print(f"File not found: {fpath}", file=sys.stderr)
            continue

        file_count = 0
        hit_limit = False
        for idx, raw in enumerate(f):
            raw = raw.strip()
            if not raw:
                continue

            # Range filters — skip early if past the window
            if args.before is not None and idx >= args.before:
                continue
            if args.after is not None and idx <= args.after:
                continue

            try:
                record = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if not matches_filters(record, args):
                continue
            if not matches_pattern(record, pattern_re):
                continue

            file_count += 1

            if args.count:
                continue

            if args.full:
                print(f"=== [{idx}] ===")
                print(json.dumps(record, indent=2))
            elif args.field:
                value = resolve_field(record, args.field)
                if value is not None:
                    if isinstance(value, (dict, list)):
                        print(f"[{idx}] {json.dumps(value)}")
                    else:
                        print(f"[{idx}] {value}")
            else:
                print(format_summary(idx, record))

            if args.limit is not None and file_count >= args.limit:
                hit_limit = True
                break

        f.close()
        total_count += file_count
        if hit_limit:
            break

    if args.count:
        print(total_count)


if __name__ == "__main__":
    main()
