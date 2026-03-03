"""Static wiring tests for S2-4 support-check metrics."""

from pathlib import Path


SOURCE = Path("api_server.py").read_text(encoding="utf-8")


def test_unsupported_answer_metric_is_exposed() -> None:
    assert "unsupported_answer_events" in SOURCE
    assert "record_unsupported_answer" in SOURCE
    assert '"unsupported_answer_rate"' in SOURCE


def test_support_check_failure_records_unsupported_metric() -> None:
    assert "metrics.record_unsupported_answer()" in SOURCE
