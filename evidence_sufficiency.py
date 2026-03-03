"""Evidence Sufficiency Score (ESS) helpers for grounded response gating."""

from __future__ import annotations

from typing import Any, Dict, List


def compute_evidence_sufficiency(results: List[Dict[str, Any]], source_count: int) -> float:
    """Compute ESS in [0,1] from retrieved chunk scores and citation diversity.

    The score intentionally favors:
    - strong top retrieval confidence
    - stable average confidence across retrieved chunks
    - diversity of supporting sources
    """
    if not results:
        return 0.0

    normalized_scores: List[float] = []
    for item in results:
        try:
            score = float(item.get("score", 0.0))
        except (TypeError, ValueError):
            score = 0.0
        normalized_scores.append(max(0.0, min(1.0, score)))

    top_score = max(normalized_scores)
    avg_score = sum(normalized_scores) / len(normalized_scores)
    source_diversity = max(0.0, min(1.0, source_count / max(1, min(len(results), 4))))

    ess = (0.55 * top_score) + (0.30 * avg_score) + (0.15 * source_diversity)
    return round(max(0.0, min(1.0, ess)), 4)
