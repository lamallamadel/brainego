"""Standardized missing-context response helpers for grounded workflows."""

from __future__ import annotations

from typing import Any, Dict, List


_GENERIC_QUESTIONS = [
    "Quel document ou repository interne contient la réponse attendue ?",
    "Quelle période, version ou commit dois-je cibler pour répondre précisément ?",
    "Peux-tu préciser le périmètre (équipe, projet, workspace) à couvrir ?",
]


def should_return_missing_context(grounding_intent: str, ess: float, ess_threshold_high: float) -> bool:
    """Return True when policy requires a missing-context response without LLM call."""
    return (grounding_intent or "").strip().lower() == "must_ground" and float(ess) < float(ess_threshold_high)


def build_missing_context_payload(query: str, ess: float, ess_threshold_high: float) -> Dict[str, Any]:
    """Build stable missing-context payload with max 3 targeted questions + 1 ingestion suggestion."""
    cleaned_query = (query or "").strip()
    targeted_questions: List[str] = list(_GENERIC_QUESTIONS)
    if cleaned_query:
        targeted_questions[0] = (
            f"Sur quels documents internes spécifiques dois-je m'appuyer pour: '{cleaned_query[:120]}' ?"
        )

    return {
        "type": "missing_context",
        "reason": "insufficient_evidence",
        "ess": round(max(0.0, min(1.0, float(ess))), 4),
        "ess_threshold_high": float(ess_threshold_high),
        "targeted_questions": targeted_questions[:3],
        "ingestion_suggestion": "Ingest the missing source documents (or latest commit/files) into this workspace then retry.",
    }
