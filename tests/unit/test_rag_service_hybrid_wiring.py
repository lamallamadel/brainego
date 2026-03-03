"""Static wiring checks for S1-1 hybrid retrieval in rag_service.py."""

from pathlib import Path


SOURCE = Path("rag_service.py").read_text(encoding="utf-8")


def test_search_documents_uses_hybrid_rrf_and_workspace_assertion() -> None:
    assert "HYBRID_RETRIEVAL_ENABLED" in SOURCE
    assert "rank_bm25_lite(query, vector_results)" in SOURCE
    assert "fuse_rrf(" in SOURCE
    assert "Cross-workspace retrieval leakage detected" in SOURCE


def test_graph_enrichment_path_uses_hybrid_rrf() -> None:
    assert "if HYBRID_RETRIEVAL_ENABLED:" in SOURCE
    assert "vector_results = fuse_rrf(" in SOURCE


def test_reranker_is_wired_and_configurable() -> None:
    assert "RERANK_ENABLED" in SOURCE
    assert "RERANK_ALPHA" in SOURCE
    assert "RERANK_ALPHA_BY_WORKSPACE" in SOURCE
    assert "rerank_results(" in SOURCE
    assert "_resolve_rerank_alpha(" in SOURCE
