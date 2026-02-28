# Needs: python-package:pytest>=9.0.2

import ast
from pathlib import Path


SOURCE = Path(__file__).resolve().parents[2] / "api_server.py"


def _parse() -> ast.Module:
    return ast.parse(SOURCE.read_text(encoding="utf-8"))


def test_v1_mcp_route_exists() -> None:
    module = _parse()
    found = False
    for node in module.body:
        if isinstance(node, ast.AsyncFunctionDef):
            for dec in node.decorator_list:
                if (
                    isinstance(dec, ast.Call)
                    and isinstance(dec.func, ast.Attribute)
                    and isinstance(dec.func.value, ast.Name)
                    and dec.func.value.id == "app"
                    and dec.func.attr == "post"
                    and dec.args
                    and isinstance(dec.args[0], ast.Constant)
                    and dec.args[0].value == "/v1/mcp"
                ):
                    found = True
    assert found


def test_v1_mcp_proxy_targets_mcp_gateway() -> None:
    content = SOURCE.read_text(encoding="utf-8")
    assert 'MCP_GATEWAY_URL = os.getenv("MCP_GATEWAY_URL", "http://mcpjungle:9100")' in content
    assert 'f"{MCP_GATEWAY_URL}/mcp"' in content
