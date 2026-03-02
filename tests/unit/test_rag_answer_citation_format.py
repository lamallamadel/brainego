# Needs: python-package:pytest>=9.0.2
"""Static checks for AFR-110 answer citation formatting when RAG is enabled."""

from pathlib import Path


API_SERVER_SOURCE = Path("api_server.py").read_text(encoding="utf-8")


def test_rag_citation_helpers_and_constants_exist() -> None:
    """api_server should define deterministic citation and missing-context helpers."""
    assert 'RAG_CITATION_SECTION_HEADER = "Sources (path + commit):"' in API_SERVER_SOURCE
    assert "RAG_MISSING_CONTEXT_GUIDANCE = (" in API_SERVER_SOURCE
    assert "def extract_rag_sources(results: List[Dict[str, Any]]) -> List[Dict[str, str]]:" in API_SERVER_SOURCE
    assert "def append_rag_citations_and_guidance(" in API_SERVER_SOURCE
    assert "'- path: <path> | commit: <commit>'" in API_SERVER_SOURCE


def test_chat_completions_appends_sources_and_tracks_missing_context_guidance() -> None:
    """Chat completions should append path+commit citations whenever RAG is enabled."""
    assert "if request.rag and request.rag.enabled:" in API_SERVER_SOURCE
    assert "generated_text = append_rag_citations_and_guidance(" in API_SERVER_SOURCE
    assert '"missing_context_guidance_required": rag_context_insufficient' in API_SERVER_SOURCE
    assert 'response_data["sources"] = rag_sources' in API_SERVER_SOURCE


def test_rag_query_response_exposes_sources_payload() -> None:
    """RAG query response model and runtime payload should expose grounded sources."""
    assert "class RAGQueryResponse(BaseModel):" in API_SERVER_SOURCE
    assert "sources: Optional[List[Dict[str, str]]] = Field(" in API_SERVER_SOURCE
    assert "sources=source_citations if source_citations else None" in API_SERVER_SOURCE
    assert '"missing_context_guidance_required": missing_context_guidance_required' in API_SERVER_SOURCE


def test_graph_rag_query_response_uses_same_citation_contract() -> None:
    """Graph-enriched RAG query should follow the same sources + guidance contract."""
    assert "class RAGGraphQueryResponse(BaseModel):" in API_SERVER_SOURCE
    assert "sources: Optional[List[Dict[str, str]]] = Field(" in API_SERVER_SOURCE
    assert "rag_sources=source_citations," in API_SERVER_SOURCE
    assert "context_insufficient=missing_context_guidance_required," in API_SERVER_SOURCE
