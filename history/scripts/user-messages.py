#!/usr/bin/env python3
"""List human-typed user messages from a session JSONL.

Usage: python3 user-messages.py <session.jsonl>

Filters out: tool results, teammate messages, system commands,
compaction summaries, slash-command entries, and interrupt notices.

Output: [INDEX] first 200 chars of message text
"""

import json
import sys

FILTER_PREFIXES = (
    "[Request interrupted",
    "This session is being continued",
    "<teammate-message",
    "<local-command",
    "<command-name",
    "<command-message",
    "Base directory for this skill:",
)


def extract_text(content):
    """Extract readable text from message.content, skipping tool results."""
    if isinstance(content, str) and content:
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(parts) if parts else None
    return None


def is_human(text):
    """Filter out non-human messages."""
    return not any(text.startswith(prefix) for prefix in FILTER_PREFIXES)


def main():
    if len(sys.argv) != 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__.strip())
        sys.exit(0 if "--help" in sys.argv or "-h" in sys.argv else 2)

    fpath = sys.argv[1]

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

                if record.get("type") != "user":
                    continue

                text = extract_text(record.get("message", {}).get("content"))
                if not text:
                    continue
                if not is_human(text):
                    continue

                preview = text[:200].replace("\n", " ")
                print(f"[{idx}] {preview}")

    except FileNotFoundError:
        print(f"File not found: {fpath}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
