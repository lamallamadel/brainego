"""Unit tests for /v1/rag/queryAPI alias endpoint registration."""

from __future__ import annotations

import ast
from pathlib import Path


API_SERVER_PATH = Path("api_server.py")


def _load_module_ast() -> ast.Module:
    source = API_SERVER_PATH.read_text(encoding="utf-8")
    return ast.parse(source)


def test_rag_queryapi_alias_route_registered() -> None:
    """Ensure both /v1/rag/query and /v1/rag/queryAPI map to rag_query handler."""
    module = _load_module_ast()

    for node in module.body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "rag_query":
            route_paths: set[str] = set()

            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call):
                    continue
                if not isinstance(decorator.func, ast.Attribute):
                    continue
                if decorator.func.attr != "post":
                    continue
                if not decorator.args:
                    continue
                route_arg = decorator.args[0]
                if isinstance(route_arg, ast.Constant) and isinstance(route_arg.value, str):
                    route_paths.add(route_arg.value)

            assert "/v1/rag/query" in route_paths
            assert "/v1/rag/queryAPI" in route_paths
            return

    raise AssertionError("rag_query endpoint handler not found in api_server.py")


def test_root_endpoint_lists_rag_queryapi_alias() -> None:
    """Ensure the root endpoint metadata exposes the queryAPI alias."""
    module = _load_module_ast()

    for node in module.body:
        if not isinstance(node, ast.AsyncFunctionDef) or node.name != "root":
            continue
        for statement in node.body:
            if not isinstance(statement, ast.Return):
                continue
            if not isinstance(statement.value, ast.Dict):
                continue

            for key_node, value_node in zip(statement.value.keys, statement.value.values):
                if not (isinstance(key_node, ast.Constant) and key_node.value == "endpoints"):
                    continue
                if not isinstance(value_node, ast.Dict):
                    continue

                endpoint_map = {
                    key.value: value.value
                    for key, value in zip(value_node.keys, value_node.values)
                    if isinstance(key, ast.Constant)
                    and isinstance(value, ast.Constant)
                    and isinstance(key.value, str)
                    and isinstance(value.value, str)
                }

                assert endpoint_map.get("rag_query_api") == "/v1/rag/queryAPI"
                return

    raise AssertionError("root endpoint metadata not found in api_server.py")
