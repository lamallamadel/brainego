"""Hybrid retrieval helpers: lexical ranking + RRF fusion."""

from __future__ import annotations

import re
from typing import Any, Dict, List


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def bm25_lite_score(query: str, text: str) -> float:
    """Lightweight lexical score as overlap ratio proxy for BM25."""
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


def rank_bm25_lite(query: str, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ranked: List[Dict[str, Any]] = []
    for item in results:
        row = dict(item)
        row["bm25_score"] = bm25_lite_score(query, str(item.get("text", "")))
        ranked.append(row)
    ranked.sort(key=lambda x: x.get("bm25_score", 0.0), reverse=True)
    return ranked


def fuse_rrf(vector_ranked: List[Dict[str, Any]], bm25_ranked: List[Dict[str, Any]], *, rrf_k: int = 60, top_k: int = 10) -> List[Dict[str, Any]]:
    """Fuse vector and bm25 rankings with Reciprocal Rank Fusion."""
    fused: Dict[str, Dict[str, Any]] = {}

    def _get_id(item: Dict[str, Any], idx: int) -> str:
        candidate = item.get("id")
        return str(candidate) if candidate is not None else f"idx-{idx}"

    for rank, item in enumerate(vector_ranked, start=1):
        key = _get_id(item, rank)
        entry = fused.setdefault(key, dict(item))
        entry["vector_rank"] = rank
        entry.setdefault("bm25_rank", None)
        entry["rrf_score"] = entry.get("rrf_score", 0.0) + (1.0 / (rrf_k + rank))

    for rank, item in enumerate(bm25_ranked, start=1):
        key = _get_id(item, rank)
        entry = fused.setdefault(key, dict(item))
        entry["bm25_rank"] = rank
        entry.setdefault("vector_rank", None)
        entry["rrf_score"] = entry.get("rrf_score", 0.0) + (1.0 / (rrf_k + rank))
        if "bm25_score" in item:
            entry["bm25_score"] = item["bm25_score"]

    ranked = sorted(fused.values(), key=lambda x: x.get("rrf_score", 0.0), reverse=True)
    return ranked[: max(1, top_k)]
