"""Static checks for S1-5 workspace partition and audit trace wiring."""

from pathlib import Path


API_SOURCE = Path("api_server.py").read_text(encoding="utf-8")
RAG_SOURCE = Path("rag_service.py").read_text(encoding="utf-8")


def test_api_emits_workspace_audit_trace_on_rag_paths() -> None:
    assert "def emit_workspace_audit_trace(" in API_SOURCE
    assert 'emit_workspace_audit_trace(endpoint="/v1/rag/query"' in API_SOURCE
    assert 'emit_workspace_audit_trace(endpoint="/v1/rag/query/graph-enriched"' in API_SOURCE


def test_retrieval_enforces_workspace_partition_assertion() -> None:
    assert "Cross-workspace retrieval leakage detected" in RAG_SOURCE
    assert "workspace_id=resolved_workspace_id" in RAG_SOURCE
