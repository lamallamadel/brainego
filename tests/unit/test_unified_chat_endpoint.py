"""Static tests for unified chat endpoint wiring in api_server.py."""

from pathlib import Path


API_SERVER_SOURCE = Path("api_server.py").read_text(encoding="utf-8")


def test_unified_chat_request_model_exposes_orchestration_controls():
    """Unified request model should provide explicit RAG/memory orchestration knobs."""
    assert "class UnifiedChatRequest(BaseModel):" in API_SERVER_SOURCE
    assert "use_rag: bool = Field(True" in API_SERVER_SOURCE
    assert "use_memory: bool = Field(True" in API_SERVER_SOURCE
    assert "store_memory: bool = Field(True" in API_SERVER_SOURCE
    assert "use_temporal_decay: bool = Field(True" in API_SERVER_SOURCE
    assert "rag_k: int = Field(5, ge=1, le=20" in API_SERVER_SOURCE
    assert "memory_top_k: int = Field(5, ge=1, le=20" in API_SERVER_SOURCE


def test_unified_chat_endpoint_maps_to_chat_completion_options():
    """Unified endpoint should map switches into ChatRAGOptions/ChatMemoryOptions."""
    assert '@app.post("/v1/chat")' in API_SERVER_SOURCE
    assert "async def unified_chat(request: UnifiedChatRequest, raw_request: Request):" in API_SERVER_SOURCE
    assert "resolved_user = request.user_id or request.user" in API_SERVER_SOURCE
    assert "rag=ChatRAGOptions(" in API_SERVER_SOURCE
    assert "enabled=request.use_rag" in API_SERVER_SOURCE
    assert ") if request.use_rag else None" in API_SERVER_SOURCE
    assert "memory=ChatMemoryOptions(" in API_SERVER_SOURCE
    assert "enabled=request.use_memory" in API_SERVER_SOURCE
    assert "auto_store=request.store_memory" in API_SERVER_SOURCE
    assert "use_temporal_decay=request.use_temporal_decay" in API_SERVER_SOURCE
    assert ") if request.use_memory else None" in API_SERVER_SOURCE
    assert "return await chat_completions(completion_request, raw_request)" in API_SERVER_SOURCE
