#!/usr/bin/env python3
"""
Read verification.log (or path given as first argument) and look for errors.
Exit 0 if no errors found, 1 if errors or missing log.
"""
import re
import sys
from pathlib import Path

LOG_PATH = Path(__file__).resolve().parent / "verification.log"
if len(sys.argv) > 1:
    LOG_PATH = Path(sys.argv[1])

ERROR_PATTERNS = [
    re.compile(r"Traceback\s*\(", re.IGNORECASE),
    re.compile(r"Error\s*:", re.IGNORECASE),
    re.compile(r"Exception\s*:", re.IGNORECASE),
    re.compile(r"\bError\b", re.IGNORECASE),
    re.compile(r"exit code:\s*[1-9]\d*", re.IGNORECASE),
]

def main():
    if not LOG_PATH.exists():
        print(f"Log file not found: {LOG_PATH}", file=sys.stderr)
        return 1
    text = LOG_PATH.read_text()
    found = []
    for pat in ERROR_PATTERNS:
        for m in pat.finditer(text):
            snippet = text[max(0, m.start() - 20) : m.end() + 80]
            found.append(snippet.replace("\n", " "))
    if found:
        print("Errors or exceptions found in log:", file=sys.stderr)
        for s in found[:10]:
            print("  ", s[:200], file=sys.stderr)
        if len(found) > 10:
            print(f"  ... and {len(found) - 10} more", file=sys.stderr)
        return 1
    print("No errors found in log.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
