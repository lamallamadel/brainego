# Needs: python-package:pytest>=9.0.2

from pathlib import Path


SOURCE = Path(__file__).resolve().parents[2] / "api_server.py"


def test_admin_workspace_routes_and_metering_route_exist() -> None:
    content = SOURCE.read_text(encoding="utf-8")

    assert '@app.post("/admin/workspaces", response_model=WorkspaceResponse)' in content
    assert '@app.post("/admin/workspaces/{workspace_id}/disable", response_model=WorkspaceResponse)' in content
    assert '@app.get("/admin/workspaces", response_model=WorkspaceListResponse)' in content
    assert '@app.get("/metering", response_model=MeteringSummaryResponse)' in content


def test_rag_delete_is_workspace_scoped() -> None:
    content = SOURCE.read_text(encoding="utf-8")

    assert "async def rag_delete_document(" in content
    assert "workspace_id: str = Query(..., description=\"Workspace owning the document\")" in content
    assert "service.delete_document(document_id, workspace_id=normalized_workspace_id)" in content


def test_audit_export_enforces_workspace_scope() -> None:
    content = SOURCE.read_text(encoding="utf-8")

    assert "_resolve_workspace_scope(" in content
    assert "workspace_id is required for audit export" in content


def test_mcp_policy_checks_workspace_lifecycle_state() -> None:
    content = SOURCE.read_text(encoding="utf-8")

    assert "context=\"MCP tool policy\"" in content
    assert "_ensure_workspace_active(" in content
