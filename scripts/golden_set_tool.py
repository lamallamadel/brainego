#!/usr/bin/env python3
"""Golden set schema validator and versioning tool for AFR-130."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


class GoldenSetError(RuntimeError):
    pass


def load_suite(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise GoldenSetError("Golden set payload must be a JSON object")
    return payload


def _ensure(condition: bool, message: str) -> None:
    if not condition:
        raise GoldenSetError(message)


def validate_suite(payload: dict[str, Any]) -> None:
    metadata = payload.get("metadata")
    cases = payload.get("cases")

    _ensure(isinstance(metadata, dict), "metadata must be an object")
    _ensure(isinstance(cases, list) and cases, "cases must be a non-empty list")

    schema_version = metadata.get("schema_version")
    version = metadata.get("version")
    _ensure(schema_version == "golden_qa.v1", "metadata.schema_version must be golden_qa.v1")
    _ensure(isinstance(version, str) and SEMVER_RE.match(version), "metadata.version must be semver")
    _ensure(metadata.get("total_cases") == len(cases), "metadata.total_cases must match number of cases")

    ids: set[str] = set()
    for case in cases:
        _ensure(isinstance(case, dict), "each case must be an object")
        case_id = case.get("id")
        _ensure(isinstance(case_id, str) and case_id.strip(), "case.id must be a non-empty string")
        _ensure(case_id not in ids, f"duplicate case id: {case_id}")
        ids.add(case_id)

        expected_sources = case.get("expected_sources")
        _ensure(isinstance(expected_sources, list) and expected_sources, f"{case_id}: expected_sources must be non-empty")

        expected_citations = case.get("expected_citations")
        _ensure(isinstance(expected_citations, list) and expected_citations, f"{case_id}: expected_citations must be non-empty")
        for citation in expected_citations:
            _ensure(isinstance(citation, dict), f"{case_id}: expected_citations entries must be objects")
            source = citation.get("source")
            _ensure(source in expected_sources, f"{case_id}: expected citation source must be present in expected_sources")

        expected_tools = case.get("expected_tool_usage")
        _ensure(isinstance(expected_tools, list) and expected_tools, f"{case_id}: expected_tool_usage must be non-empty")
        for tool in expected_tools:
            _ensure(isinstance(tool, dict), f"{case_id}: expected_tool_usage entries must be objects")
            _ensure(isinstance(tool.get("tool"), str) and tool["tool"].strip(), f"{case_id}: tool name must be non-empty")


def _parse_semver(version: str) -> tuple[int, int, int]:
    if not SEMVER_RE.match(version):
        raise GoldenSetError(f"invalid semver: {version}")
    major, minor, patch = version.split(".")
    return int(major), int(minor), int(patch)


def bump_version(version: str, part: str) -> str:
    major, minor, patch = _parse_semver(version)
    if part == "major":
        major += 1
        minor = 0
        patch = 0
    elif part == "minor":
        minor += 1
        patch = 0
    else:
        patch += 1
    return f"{major}.{minor}.{patch}"


def cmd_validate(args: argparse.Namespace) -> int:
    suite = load_suite(args.path)
    validate_suite(suite)
    print(f"OK: {args.path}")
    return 0


def cmd_bump(args: argparse.Namespace) -> int:
    suite = load_suite(args.path)
    validate_suite(suite)
    metadata = suite["metadata"]
    metadata["version"] = bump_version(metadata["version"], args.part)
    args.path.write_text(json.dumps(suite, indent=2) + "\n", encoding="utf-8")
    print(f"Bumped {args.part}: {metadata['version']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Golden set tooling")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="validate suite schema")
    validate_parser.add_argument("--path", type=Path, required=True)
    validate_parser.set_defaults(func=cmd_validate)

    bump_parser = subparsers.add_parser("bump", help="bump metadata.version")
    bump_parser.add_argument("--path", type=Path, required=True)
    bump_parser.add_argument("--part", choices=("major", "minor", "patch"), default="patch")
    bump_parser.set_defaults(func=cmd_bump)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
