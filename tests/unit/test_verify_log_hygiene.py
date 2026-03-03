"""Unit tests for log hygiene secret marker verification script."""

import importlib.util
from pathlib import Path

MODULE_PATH = Path("scripts/observability/verify_log_hygiene.py")
SPEC = importlib.util.spec_from_file_location("verify_log_hygiene", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_scan_lines_detects_secret_and_redaction_marker() -> None:
    lines = [
        "ok line",
        "password=supersecret",
        "value [REDACTED_SECRET]",
    ]
    secret_hits, marker_hits = MODULE.scan_lines(lines)
    assert secret_hits == 1
    assert marker_hits == 1


def test_scan_files_zero_secret_returns_zero_hits(tmp_path: Path) -> None:
    p = tmp_path / "app.log"
    p.write_text("normal line\n[REDACTED_SECRET]\n", encoding="utf-8")
    secret_hits, marker_hits = MODULE.scan_files([p])
    assert secret_hits == 0
    assert marker_hits == 1
