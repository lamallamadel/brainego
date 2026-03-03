"""Recovery planner for executing teacher candidate queries and rescoring ESS."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple


def _compute_ess(results: List[Dict[str, Any]]) -> float:
    if not results:
        return 0.0
    scores: List[float] = []
    for item in results:
        try:
            scores.append(max(0.0, min(1.0, float(item.get("score", 0.0)))))
        except (TypeError, ValueError):
            scores.append(0.0)
    top = max(scores)
    avg = sum(scores) / len(scores)
    return round((0.6 * top) + (0.4 * avg), 4)


def run_recovery_attempts(
    *,
    service: Any,
    candidate_queries: List[str],
    workspace_id: str,
    rag_filters: Dict[str, Any] | None,
    initial_results: List[Dict[str, Any]],
    initial_sources: List[Dict[str, str]],
    max_attempts: int,
    top_k: int,
) -> Tuple[List[Dict[str, Any]], float, int]:
    """Return best recovered results, best ESS and attempts used."""
    del initial_sources
    best_results = list(initial_results)
    best_ess = _compute_ess(initial_results)
    attempts_used = 0

    for query in candidate_queries[: max(0, max_attempts)]:
        if not str(query).strip():
            continue
        attempts_used += 1
        recovered = service.search_documents(
            query=str(query),
            limit=top_k,
            filters=rag_filters,
            workspace_id=workspace_id,
        )
        ess = _compute_ess(recovered)
        if ess > best_ess:
            best_ess = ess
            best_results = recovered

    return best_results, best_ess, attempts_used
