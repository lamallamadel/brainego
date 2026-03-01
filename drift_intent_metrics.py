"""Utilities for intent-distribution drift metrics (PSI)."""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Optional


def _normalize_intent(intent: Any) -> str:
    """Normalize raw intent values for stable counting."""
    if intent is None:
        return "unknown"

    normalized = str(intent).strip().lower()
    return normalized or "unknown"


def get_intent_distribution(
    feedback_data: List[Dict[str, Any]],
    categories: Optional[Iterable[str]] = None,
) -> Dict[str, int]:
    """Build intent counts from feedback rows."""
    normalized_categories = [_normalize_intent(category) for category in (categories or [])]
    distribution: Dict[str, int] = {category: 0 for category in normalized_categories}

    for record in feedback_data:
        intent = _normalize_intent(record.get("intent"))
        if normalized_categories and intent not in distribution:
            intent = "unknown"
        distribution[intent] = distribution.get(intent, 0) + 1

    return distribution


def calculate_population_stability_index(
    reference_distribution: Dict[str, int],
    current_distribution: Dict[str, int],
    categories: Optional[Iterable[str]] = None,
    epsilon: float = 1e-6,
) -> float:
    """Calculate PSI between a reference and current intent distribution."""
    category_set = {_normalize_intent(category) for category in (categories or [])}
    category_set.update(reference_distribution.keys())
    category_set.update(current_distribution.keys())

    if not category_set:
        return 0.0

    reference_total = float(sum(reference_distribution.values()))
    current_total = float(sum(current_distribution.values()))

    if reference_total == 0.0 and current_total == 0.0:
        return 0.0

    reference_total = reference_total or 1.0
    current_total = current_total or 1.0

    psi = 0.0
    for category in category_set:
        reference_pct = (reference_distribution.get(category, 0) / reference_total) + epsilon
        current_pct = (current_distribution.get(category, 0) / current_total) + epsilon
        psi += (current_pct - reference_pct) * math.log(current_pct / reference_pct)

    return float(psi)
