# Needs: python-package:pytest>=9.0.2

"""Static tests for workspace context enforcement and propagation in api_server.py."""

from pathlib import Path


API_SERVER_SOURCE = Path("api_server.py").read_text(encoding="utf-8")


def test_api_server_defines_workspace_enforcement_middleware() -> None:
    assert "async def enforce_workspace_context(request: Request, call_next):" in API_SERVER_SOURCE
    assert 'WORKSPACE_REQUIRED_PREFIXES = ("/v1/", "/memory", "/graph", "/internal/")' in API_SERVER_SOURCE
    assert "workspace_id = resolve_workspace_id(request)" in API_SERVER_SOURCE
    assert '"code": "workspace_id_missing"' in API_SERVER_SOURCE
    assert '"code": "workspace_id_unknown"' in API_SERVER_SOURCE
    assert "request.state.workspace_id = workspace_id" in API_SERVER_SOURCE
    assert "WORKSPACE_CONTEXT.set(workspace_id)" in API_SERVER_SOURCE


def test_workspace_id_propagates_through_chat_rag_and_memory_layers() -> None:
    assert "workspace_id = get_current_workspace_id()" in API_SERVER_SOURCE
    assert "filters=ensure_workspace_filter(None, workspace_id)," in API_SERVER_SOURCE
    assert "rag_filters = ensure_workspace_filter(request.rag.filters, workspace_id)" in API_SERVER_SOURCE
    assert '"workspace_id": workspace_id' in API_SERVER_SOURCE
    assert "metadata=ensure_workspace_metadata(" in API_SERVER_SOURCE


def test_workspace_id_propagates_to_mcp_tool_layer() -> None:
    assert "headers[WORKSPACE_ID_RESPONSE_HEADER] = workspace_id" in API_SERVER_SOURCE
    assert 'payload["workspace_id"] = workspace_id' in API_SERVER_SOURCE
    assert 'tool_arguments.setdefault("workspace_id", workspace_id)' in API_SERVER_SOURCE
    assert "workspace_id=workspace_id," in API_SERVER_SOURCE
