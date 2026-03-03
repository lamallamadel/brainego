#!/usr/bin/env python3
"""Verify log hygiene by scanning for secret markers and unredacted leaks."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Iterable, List, Tuple

SECRET_PATTERNS = [
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"api[_-]?key\s*[:=]\s*[^\s]+", re.IGNORECASE),
    re.compile(r"password\s*[:=]\s*[^\s]+", re.IGNORECASE),
    re.compile(r"token\s*[:=]\s*[^\s]+", re.IGNORECASE),
]
REDACTION_MARKER = "[REDACTED"


def scan_lines(lines: Iterable[str]) -> Tuple[int, int]:
    secret_hits = 0
    marker_hits = 0
    for line in lines:
        if REDACTION_MARKER in line:
            marker_hits += 1
        if any(pattern.search(line) for pattern in SECRET_PATTERNS):
            secret_hits += 1
    return secret_hits, marker_hits


def scan_files(paths: List[Path]) -> Tuple[int, int]:
    total_secret_hits = 0
    total_marker_hits = 0
    for path in paths:
        if not path.exists() or not path.is_file():
            continue
        secret_hits, marker_hits = scan_lines(path.read_text(encoding="utf-8", errors="replace").splitlines())
        total_secret_hits += secret_hits
        total_marker_hits += marker_hits
    return total_secret_hits, total_marker_hits


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify log hygiene (0 secret leaks expected).")
    parser.add_argument("paths", nargs="+", help="Log files to scan")
    args = parser.parse_args()

    files = [Path(p) for p in args.paths]
    secret_hits, marker_hits = scan_files(files)

    print(f"secret_hits={secret_hits}")
    print(f"redaction_marker_hits={marker_hits}")

    return 1 if secret_hits > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
