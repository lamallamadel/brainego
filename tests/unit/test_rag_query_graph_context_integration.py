"""Static tests for Neo4j graph context integration in /v1/rag/query."""

from pathlib import Path


API_SERVER_SOURCE = Path("api_server.py").read_text(encoding="utf-8")


def test_rag_query_request_exposes_graph_enrichment_controls() -> None:
    """RAGQueryRequest should include graph enrichment controls."""
    assert "class RAGQueryRequest(BaseModel):" in API_SERVER_SOURCE
    assert "include_graph_context: Optional[bool] = Field(" in API_SERVER_SOURCE
    assert "graph_limit: int = Field(" in API_SERVER_SOURCE


def test_rag_query_response_exposes_graph_context_fields() -> None:
    """RAGQueryResponse should include graph context payload fields."""
    assert "class RAGQueryResponse(BaseModel):" in API_SERVER_SOURCE
    assert "graph_context: Optional[Dict[str, Any]] = Field(" in API_SERVER_SOURCE
    assert "graph_context_formatted: Optional[str] = Field(" in API_SERVER_SOURCE


def test_rag_query_endpoint_uses_graph_enrichment_when_available() -> None:
    """rag_query should call graph enrichment and include graph stats in retrieval metadata."""
    assert "should_enrich_with_graph = bool(" in API_SERVER_SOURCE
    assert "enriched_results = service.search_with_graph_enrichment(" in API_SERVER_SOURCE
    assert '"relationships_found": relationships_found' in API_SERVER_SOURCE
    assert '"entities_in_graph": entities_in_graph' in API_SERVER_SOURCE
    assert "graph_context=graph_context if request.include_context else None" in API_SERVER_SOURCE
