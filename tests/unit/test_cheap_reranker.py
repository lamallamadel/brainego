"""Unit tests for cheap reranker behavior."""

import importlib.util
from pathlib import Path

MODULE_PATH = Path("cheap_reranker.py")
SPEC = importlib.util.spec_from_file_location("cheap_reranker", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_rerank_results_adds_rerank_score_and_reorders() -> None:
    rows = [
        {"id": "a", "text": "unrelated", "score": 0.95},
        {"id": "b", "text": "retention policy internal", "score": 0.75},
    ]
    out = MODULE.rerank_results("retention policy", rows, alpha=0.3, top_k=2)
    assert len(out) == 2
    assert "rerank_score" in out[0]
    assert out[0]["id"] == "b"
