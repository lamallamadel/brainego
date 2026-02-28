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


def test_unified_mcp_requires_tool_name_for_call_tool() -> None:
    source_text = SOURCE.read_text(encoding="utf-8")
    assert 'if action == "call_tool":' in source_text
    assert 'Missing required field: tool_name' in source_text


def test_metrics_include_mcp_error_rate_fields() -> None:
    source_text = SOURCE.read_text(encoding="utf-8")
    assert '"mcp_errors"' in source_text
    assert '"mcp_error_rate"' in source_text
