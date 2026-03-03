"""Static wiring tests for S2-2 teacher contract usage."""

from pathlib import Path


SOURCE = Path("api_server.py").read_text(encoding="utf-8")


def test_api_validates_teacher_output_before_exposing() -> None:
    assert "validate_teacher_output" in SOURCE
    assert '"invalid_teacher_output": True' in SOURCE


def test_hypotheses_are_kept_in_teacher_guidance_not_as_facts() -> None:
    assert '"teacher_guidance"' in SOURCE
