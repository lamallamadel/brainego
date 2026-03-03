"""Static wiring tests for S2-5 learning events integration."""

from pathlib import Path


SOURCE = Path("api_server.py").read_text(encoding="utf-8")


def test_api_wires_learning_events_store() -> None:
    assert "LearningEventsStore" in SOURCE
    assert "record_learning_event(" in SOURCE


def test_teacher_and_support_paths_record_learning_events() -> None:
    assert '"teacher_used": True' in SOURCE
    assert '"outcome": "downgraded_missing_context"' in SOURCE
