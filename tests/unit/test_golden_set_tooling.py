from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SUITE_PATH = REPO_ROOT / "tests" / "contract" / "fixtures" / "repo_rag_golden_set.ndjson"
TOOL_PATH = REPO_ROOT / "scripts" / "golden_set_tool.py"


spec = importlib.util.spec_from_file_location("golden_set_tool", TOOL_PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_validate_repo_rag_suite_passes() -> None:
    suite = module.load_suite(SUITE_PATH)
    module.validate_suite(suite)


def test_bump_version_patch() -> None:
    assert module.bump_version("1.2.3", "patch") == "1.2.4"


def test_validate_detects_mismatched_total_cases(tmp_path: Path) -> None:
    suite = module.load_suite(SUITE_PATH)
    suite["metadata"]["total_cases"] = 999
    broken_path = tmp_path / "broken.json"
    broken_path.write_text(json.dumps(suite), encoding="utf-8")

    payload = module.load_suite(broken_path)

    try:
        module.validate_suite(payload)
    except module.GoldenSetError as exc:
        assert "total_cases" in str(exc)
    else:
        raise AssertionError("expected GoldenSetError")
