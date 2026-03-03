"""Cheap reranker utilities for hybrid retrieval pipelines."""

from __future__ import annotations

import re
from typing import Any, Dict, List


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def _lexical_score(query: str, text: str) -> float:
    q_tokens = _tokenize(query)
    if not q_tokens:
        return 0.0
    t_tokens = _tokenize(text)
    if not t_tokens:
        return 0.0
    q_set = set(q_tokens)
    t_set = set(t_tokens)
    overlap = len(q_set.intersection(t_set))
    return round(overlap / max(1, len(q_set)), 6)


def rerank_results(query: str, results: List[Dict[str, Any]], *, alpha: float = 0.65, top_k: int = 10) -> List[Dict[str, Any]]:
    """Attach `rerank_score` and sort by blended final score.

    final_score = alpha * vector_score + (1-alpha) * rerank_score
    """
    clamped_alpha = max(0.0, min(1.0, float(alpha)))
    reranked: List[Dict[str, Any]] = []
    for item in results:
        row = dict(item)
        vector_score = float(row.get("score", 0.0) or 0.0)
        rerank_score = _lexical_score(query, str(row.get("text", "")))
        final_score = (clamped_alpha * vector_score) + ((1.0 - clamped_alpha) * rerank_score)
        row["rerank_score"] = round(rerank_score, 6)
        row["score"] = round(final_score, 6)
        row["ranking_stage"] = "reranked"
        reranked.append(row)

    reranked.sort(key=lambda x: x.get("score", 0.0), reverse=True)
    return reranked[: max(1, top_k)]
