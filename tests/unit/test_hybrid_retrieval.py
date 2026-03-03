"""Unit tests for hybrid retrieval BM25-lite + RRF fusion."""

import importlib.util
from pathlib import Path

MODULE_PATH = Path("hybrid_retrieval.py")
SPEC = importlib.util.spec_from_file_location("hybrid_retrieval", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_bm25_lite_score_prefers_overlap() -> None:
    high = MODULE.bm25_lite_score("retention policy", "internal retention policy document")
    low = MODULE.bm25_lite_score("retention policy", "unrelated source code")
    assert high > low


def test_rank_bm25_lite_orders_by_score() -> None:
    rows = [
        {"id": "a", "text": "policy retention"},
        {"id": "b", "text": "hello world"},
    ]
    ranked = MODULE.rank_bm25_lite("retention policy", rows)
    assert ranked[0]["id"] == "a"
    assert "bm25_score" in ranked[0]


def test_rrf_fusion_combines_vector_and_bm25_ranks() -> None:
    vector = [
        {"id": "a", "text": "one", "score": 0.9},
        {"id": "b", "text": "two", "score": 0.8},
    ]
    bm25 = [
        {"id": "b", "text": "two", "bm25_score": 1.0},
        {"id": "a", "text": "one", "bm25_score": 0.5},
    ]
    fused = MODULE.fuse_rrf(vector, bm25, rrf_k=60, top_k=2)
    assert len(fused) == 2
    assert all("rrf_score" in item for item in fused)
