# Needs: python-package:pytest>=9.0.2

import ast
from pathlib import Path


SOURCE = Path(__file__).resolve().parents[2] / "gateway_service_mcp.py"


def _parse_module() -> ast.Module:
    return ast.parse(SOURCE.read_text(encoding="utf-8"))


def _find_route(module: ast.Module, path: str, method: str) -> ast.AsyncFunctionDef | None:
    for node in module.body:
        if isinstance(node, ast.AsyncFunctionDef):
            for decorator in node.decorator_list:
                if (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Attribute)
                    and isinstance(decorator.func.value, ast.Name)
                    and decorator.func.value.id == "app"
                    and decorator.func.attr == method
                    and decorator.args
                    and isinstance(decorator.args[0], ast.Constant)
                    and decorator.args[0].value == path
                ):
                    return node
    return None


def test_metrics_endpoint_is_public() -> None:
    module = _parse_module()
    route = _find_route(module, "/metrics", "get")
    assert route is not None, "Missing GET /metrics route"
    assert route.args.args == [], "GET /metrics should not require auth dependency args"


def test_unified_mcp_route_exists() -> None:
    module = _parse_module()
    route = _find_route(module, "/mcp", "post")
    assert route is not None, "Missing POST /mcp route"


def test_gateway_enforces_workspace_context_on_mcp_routes() -> None:
    source_text = SOURCE.read_text(encoding="utf-8")
    assert "async def enforce_workspace_context(request: Request, call_next):" in source_text
    assert 'WORKSPACE_REQUIRED_PREFIXES = ("/mcp",)' in source_text
    assert "workspace_id = resolve_workspace_id(request)" in source_text
    assert '"code": "workspace_id_missing"' in source_text
    assert '"code": "workspace_id_unknown"' in source_text


def test_mcp_models_include_workspace_scope_field() -> None:
    source_text = SOURCE.read_text(encoding="utf-8")
    assert "class MCPResourceRequest(BaseModel):" in source_text
    assert "class MCPToolRequest(BaseModel):" in source_text
    assert "workspace_id: Optional[str] = Field(None, description=\"Workspace scope for the MCP request\")" in source_text


def test_unified_mcp_requires_tool_name_for_call_tool() -> None:
    source_text = SOURCE.read_text(encoding="utf-8")
    assert 'if action == "call_tool":' in source_text
    assert 'Missing required field: tool_name' in source_text


def test_metrics_include_mcp_error_rate_fields() -> None:
    source_text = SOURCE.read_text(encoding="utf-8")
    assert '"mcp_errors"' in source_text
    assert '"mcp_error_rate"' in source_text


def test_mcp_tool_request_supports_write_confirmation_fields() -> None:
    source_text = SOURCE.read_text(encoding="utf-8")
    assert "confirm: bool = Field(" in source_text
    assert "confirmation_id: Optional[str] = Field(" in source_text


def test_write_actions_return_pending_confirmation_when_unconfirmed() -> None:
    source_text = SOURCE.read_text(encoding="utf-8")
    assert 'requires_write_confirmation(request.tool_name)' in source_text
    assert '"status": "pending_confirmation"' in source_text
    assert "write_confirmation_store.create_plan(" in source_text
    assert "confirm=true and confirmation_id" in source_text


def test_unified_mcp_passes_confirm_fields_to_call_tool_request() -> None:
    source_text = SOURCE.read_text(encoding="utf-8")
    assert 'confirm=bool(request.get("confirm", False))' in source_text
    assert 'confirmation_id=request.get("confirmation_id")' in source_text


def test_unified_mcp_resolves_workspace_and_passes_request_context() -> None:
    source_text = SOURCE.read_text(encoding="utf-8")
    assert "workspace_id = _resolve_workspace_for_request(" in source_text
    assert "provided_workspace_id=request.get(\"workspace_id\")" in source_text
    assert "raw_request: Request" in source_text
    assert "workspace_id=workspace_id" in source_text


def test_call_tool_path_injects_workspace_into_arguments() -> None:
    source_text = SOURCE.read_text(encoding="utf-8")
    assert "tool_arguments = _ensure_workspace_arguments(" in source_text
    assert "arguments=tool_arguments," in source_text
    assert "result = await mcp_client.call_tool(" in source_text


def test_rate_limit_identifier_is_workspace_scoped() -> None:
    source_text = SOURCE.read_text(encoding="utf-8")
    assert 'identifier = f"{workspace_id}:{role}:{auth.get(\'api_key\', \'\')[:10]}"' in source_text
