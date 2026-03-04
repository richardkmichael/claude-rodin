#!/usr/bin/env python3
"""Find the last compaction boundary in a session JSONL file.

Usage: python3 scope.py <session.jsonl>

Prints the 0-based line index of the last compact_boundary record.
If no boundary exists, prints nothing and exits with code 1.

Use the output with search.py --before to limit searches to pre-compaction
content (content no longer in the model's active context):

    BOUNDARY=$(python3 scope.py session.jsonl)
    python3 search.py --type user --before $BOUNDARY "keyword" session.jsonl
"""

import json
import sys


def main():
    if len(sys.argv) != 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__.strip())
        sys.exit(0 if sys.argv[1:] in (["-h"], ["--help"]) else 2)

    fpath = sys.argv[1]
    last_boundary = None

    try:
        with open(fpath) as f:
            for idx, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if (
                    record.get("type") == "system"
                    and record.get("subtype") == "compact_boundary"
                ):
                    last_boundary = idx
    except FileNotFoundError:
        print(f"File not found: {fpath}", file=sys.stderr)
        sys.exit(2)

    if last_boundary is not None:
        print(last_boundary)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
