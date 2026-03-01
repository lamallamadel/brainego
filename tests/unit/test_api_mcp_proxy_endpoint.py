# Needs: python-package:pytest>=9.0.2

import ast
from pathlib import Path


SOURCE = Path(__file__).resolve().parents[2] / "api_server.py"


def _parse() -> ast.Module:
    return ast.parse(SOURCE.read_text(encoding="utf-8"))


def _find_route(module: ast.Module, path: str, method: str) -> ast.AsyncFunctionDef | None:
    for node in module.body:
        if isinstance(node, ast.AsyncFunctionDef):
            for dec in node.decorator_list:
                if (
                    isinstance(dec, ast.Call)
                    and isinstance(dec.func, ast.Attribute)
                    and isinstance(dec.func.value, ast.Name)
                    and dec.func.value.id == "app"
                    and dec.func.attr == method
                    and dec.args
                    and isinstance(dec.args[0], ast.Constant)
                    and dec.args[0].value == path
                ):
                    return node
    return None


def _function_calls(function_node: ast.AsyncFunctionDef, function_name: str) -> bool:
    for node in ast.walk(function_node):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == function_name:
            return True
    return False


def test_v1_mcp_route_exists() -> None:
    module = _parse()
    route = _find_route(module, "/v1/mcp", "post")
    assert route is not None


def test_internal_mcp_tool_proxy_route_exists() -> None:
    module = _parse()
    route = _find_route(module, "/internal/mcp/tools/call", "post")
    assert route is not None


def test_v1_mcp_proxy_targets_mcp_gateway() -> None:
    content = SOURCE.read_text(encoding="utf-8")
    assert 'MCP_GATEWAY_URL = os.getenv("MCP_GATEWAY_URL", "http://mcpjungle:9100")' in content
    assert 'f"{MCP_GATEWAY_URL}/mcp"' in content

def test_internal_mcp_tool_proxy_supports_workspace_policy_fields() -> None:
    content = SOURCE.read_text(encoding="utf-8")
    assert "workspace_id: Optional[str]" in content
    assert "request_id: Optional[str]" in content
    assert "action: Optional[str]" in content
    assert "role: Optional[str]" in content
    assert "scopes: Optional[List[str]]" in content
    assert "workspace_id=request.workspace_id" in content
    assert "request_id=request.request_id" in content
    assert "action=request.action" in content
    assert "role=request.role" in content
    assert "scopes=request.scopes" in content


def test_mcp_proxy_models_include_write_confirmation_fields() -> None:
    content = SOURCE.read_text(encoding="utf-8")
    assert "confirm: bool = Field(" in content
    assert "confirmation_id: Optional[str] = Field(" in content


def test_v1_mcp_proxy_passes_confirmation_fields_to_gateway_payload() -> None:
    content = SOURCE.read_text(encoding="utf-8")
    assert 'payload["confirm"] = request.confirm' in content
    assert 'payload["confirmation_id"] = request.confirmation_id' in content


def test_internal_mcp_proxy_passes_confirmation_fields_to_gateway_client() -> None:
    content = SOURCE.read_text(encoding="utf-8")
    assert "confirm=request.confirm" in content
    assert "confirmation_id=request.confirmation_id" in content


def test_policy_enforced_for_v1_mcp_call_tool() -> None:
    module = _parse()
    route = _find_route(module, "/v1/mcp", "post")
    assert route is not None
    assert _function_calls(route, "enforce_mcp_tool_policy")


def test_policy_enforced_for_internal_mcp_tool_proxy() -> None:
    module = _parse()
    route = _find_route(module, "/internal/mcp/tools/call", "post")
    assert route is not None
    assert _function_calls(route, "enforce_mcp_tool_policy")


def test_policy_engine_is_loaded_in_api_and_returns_policy_denied() -> None:
    content = SOURCE.read_text(encoding="utf-8")
    assert "load_default_tool_policy_engine" in content
    assert "workspace_id is required by tool policy" in content
    assert '"error": "PolicyDenied"' in content


def test_internal_proxy_applies_policy_timeout_to_transport_client() -> None:
    content = SOURCE.read_text(encoding="utf-8")
    assert "timeout_seconds=effective_timeout_seconds" in content


def test_tool_output_guard_is_applied_before_mcp_proxy_responses() -> None:
    content = SOURCE.read_text(encoding="utf-8")
    assert "def _apply_tool_output_guard(value: Any)" in content
    assert "_apply_tool_output_guard(safe_payload)" in content
    assert "_apply_tool_output_guard(safe_error)" in content


def test_admin_policy_management_routes_exist() -> None:
    module = _parse()
    get_route = _find_route(module, "/internal/mcp/policies/{workspace_id}", "get")
    put_route = _find_route(module, "/internal/mcp/policies/{workspace_id}", "put")
    assert get_route is not None
    assert put_route is not None


def test_admin_policy_management_routes_require_admin_role() -> None:
    module = _parse()
    get_route = _find_route(module, "/internal/mcp/policies/{workspace_id}", "get")
    put_route = _find_route(module, "/internal/mcp/policies/{workspace_id}", "put")
    assert get_route is not None
    assert put_route is not None
    assert _function_calls(get_route, "_require_admin_tool_policy_role")
    assert _function_calls(put_route, "_require_admin_tool_policy_role")
