"""Teacher JSON contract and validation helpers."""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field, ValidationError


class TeacherContract(BaseModel):
    clarifying_questions: List[str] = Field(default_factory=list, max_length=3)
    candidate_queries: List[str] = Field(default_factory=list)
    search_plan: List[str] = Field(default_factory=list)
    ingestion_suggestions: List[str] = Field(default_factory=list)
    hypotheses: List[str] = Field(default_factory=list)


def validate_teacher_output(payload: dict) -> TeacherContract | None:
    """Validate teacher output. Return None when invalid."""
    try:
        return TeacherContract.model_validate(payload)
    except ValidationError:
        return None
