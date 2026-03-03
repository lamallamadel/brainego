"""Static wiring tests for S2-1 teacher broker integration."""

from pathlib import Path


SOURCE = Path("api_server.py").read_text(encoding="utf-8")


def test_teacher_metrics_are_exposed() -> None:
    assert "teacher_calls" in SOURCE
    assert "teacher_blocked_redaction" in SOURCE
    assert "record_teacher_call" in SOURCE


def test_missing_context_paths_call_teacher_broker() -> None:
    assert "teacher_broker.build_request(" in SOURCE
    assert "await teacher_broker.call(" in SOURCE
    assert 'missing_context_payload["teacher_guidance"]' in SOURCE
