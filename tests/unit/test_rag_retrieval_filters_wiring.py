# Needs: python-package:pytest>=9.0.2

"""Static tests for repo/path/lang retrieval filter wiring in api_server.py."""

from pathlib import Path


API_SERVER_SOURCE = Path("api_server.py").read_text(encoding="utf-8")


def test_rag_request_models_expose_repo_path_lang_filters() -> None:
    assert "class ChatRAGOptions(BaseModel):" in API_SERVER_SOURCE
    assert "repo: Optional[RetrievalFilterValue] = Field(" in API_SERVER_SOURCE
    assert "path: Optional[RetrievalFilterValue] = Field(" in API_SERVER_SOURCE
    assert "lang: Optional[RetrievalFilterValue] = Field(" in API_SERVER_SOURCE
    assert "rag_repo: Optional[RetrievalFilterValue] = Field(" in API_SERVER_SOURCE
    assert "rag_path: Optional[RetrievalFilterValue] = Field(" in API_SERVER_SOURCE
    assert "rag_lang: Optional[RetrievalFilterValue] = Field(" in API_SERVER_SOURCE


def test_rag_endpoints_use_retrieval_filter_builder() -> None:
    assert "from workspace_context import (" in API_SERVER_SOURCE
    assert "build_rag_retrieval_filters," in API_SERVER_SOURCE
    assert "rag_filters = build_rag_retrieval_filters(" in API_SERVER_SOURCE
    assert "repo=request.repo" in API_SERVER_SOURCE
    assert "path=request.path" in API_SERVER_SOURCE
    assert "lang=request.lang" in API_SERVER_SOURCE
