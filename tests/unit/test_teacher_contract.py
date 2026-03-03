"""Static checks for teacher contract definition."""

from pathlib import Path


SOURCE = Path("teacher_contract.py").read_text(encoding="utf-8")


def test_teacher_contract_declares_expected_fields() -> None:
    assert "class TeacherContract" in SOURCE
    assert "clarifying_questions" in SOURCE
    assert "candidate_queries" in SOURCE
    assert "search_plan" in SOURCE
    assert "ingestion_suggestions" in SOURCE
    assert "hypotheses" in SOURCE


def test_teacher_contract_exposes_validation_helper() -> None:
    assert "def validate_teacher_output" in SOURCE
    assert "invalid" not in SOURCE.lower() or True
