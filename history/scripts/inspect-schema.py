#!/usr/bin/env python3
"""Show the schema of a Claude Code session JSONL file.

Usage: python3 inspect-schema.py <session.jsonl>

Displays: top-level keys (from first entry), entry type distribution,
and user entry content formats. Run this on an unfamiliar file to
validate assumptions before using other scripts.
"""

import json
import sys
from collections import Counter


def main():
    if len(sys.argv) != 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__.strip())
        sys.exit(0 if "--help" in sys.argv or "-h" in sys.argv else 2)

    fpath = sys.argv[1]

    try:
        with open(fpath) as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"File not found: {fpath}", file=sys.stderr)
        sys.exit(2)

    records = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    if not records:
        print("No valid JSON records found")
        sys.exit(1)

    # Top-level keys from first entry
    print("=== Top-level keys (first entry) ===")
    print(json.dumps(sorted(records[0].keys())))

    # Entry type distribution
    print("\n=== Entry types and counts ===")
    type_counts = Counter(r.get("type", "(no type field)") for r in records)
    for rtype, count in type_counts.most_common():
        print(f"  {count:>6}  {rtype}")

    # User content formats
    print("\n=== User entry content formats ===")
    format_counts = Counter()
    for r in records:
        if r.get("type") != "user":
            continue
        content = r.get("message", {}).get("content")
        if isinstance(content, str):
            format_counts["string"] += 1
        elif isinstance(content, list):
            types = [b.get("type", "?") for b in content if isinstance(b, dict)]
            format_counts[json.dumps(types)] += 1
        elif content is None:
            format_counts["null"] += 1
        else:
            format_counts[f"unknown: {type(content).__name__}"] += 1

    for fmt, count in format_counts.most_common(20):
        print(f"  {count:>6}  {fmt}")


if __name__ == "__main__":
    main()
