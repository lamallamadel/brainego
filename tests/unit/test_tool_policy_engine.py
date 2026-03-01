# Needs: python-package:pyyaml>=6.0.1
# Needs: python-package:pytest>=9.0.2
"""Unit tests for workspace-scoped MCP tool policy engine."""

from __future__ import annotations

import pathlib
import sys
from typing import Any, Dict

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tool_policy_engine import ToolPolicyEngine


def _write_policy(tmp_path, payload: Dict[str, Any]) -> str:
    config_path = tmp_path / "tool-policy.yaml"
    config_path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return str(config_path)


@pytest.mark.unit
def test_policy_engine_denies_unknown_workspace_by_default(tmp_path):
    config_path = _write_policy(
        tmp_path,
        {
            "default_workspace": "ws-1",
            "workspaces": {
                "ws-1": {
                    "allowed_mcp_servers": ["mcp-docs"],
                    "allowed_tool_actions": ["read"],
                    "allowed_tool_names": {"read": ["search_docs"]},
                }
            },
        },
    )
    engine = ToolPolicyEngine.from_yaml(config_path)

    decision = engine.evaluate_tool_call(
        workspace_id="ws-unknown",
        request_id="req-1",
        server_id="mcp-docs",
        tool_name="search_docs",
        action="read",
        arguments={"query": "hello"},
        default_timeout_seconds=3.0,
    )

    assert decision.allowed is False
    assert decision.code == "PolicyDenied"
    assert "no tool policy configured" in (decision.reason or "")


@pytest.mark.unit
def test_policy_engine_allows_explicit_server_tool_and_applies_timeout(tmp_path):
    config_path = _write_policy(
        tmp_path,
        {
            "default_workspace": "ws-1",
            "workspaces": {
                "ws-1": {
                    "allowed_mcp_servers": ["mcp-docs"],
                    "allowed_tool_actions": ["read"],
                    "allowed_tool_names": {"read": ["search_docs"]},
                    "per_call_timeout_seconds": 0.75,
                }
            },
        },
    )
    engine = ToolPolicyEngine.from_yaml(config_path)

    decision = engine.evaluate_tool_call(
        workspace_id=None,
        request_id="req-2",
        server_id="mcp-docs",
        tool_name="search_docs",
        action="read",
        arguments={"query": "docs"},
        default_timeout_seconds=10.0,
    )

    assert decision.allowed is True
    assert decision.workspace_id == "ws-1"
    assert decision.timeout_seconds == 0.75


@pytest.mark.unit
def test_policy_engine_enforces_argument_allowlist(tmp_path):
    config_path = _write_policy(
        tmp_path,
        {
            "default_workspace": "ws-1",
            "workspaces": {
                "ws-1": {
                    "allowed_mcp_servers": ["mcp-filesystem"],
                    "allowed_tool_actions": ["read"],
                    "allowed_tool_names": {"read": ["read_file"]},
                    "allowlists": {
                        "servers": {
                            "mcp-filesystem": {
                                "path": ["/workspace/**"],
                            }
                        }
                    },
                }
            },
        },
    )
    engine = ToolPolicyEngine.from_yaml(config_path)

    denied = engine.evaluate_tool_call(
        workspace_id="ws-1",
        request_id="req-3",
        server_id="mcp-filesystem",
        tool_name="read_file",
        action="read",
        arguments={"path": "/etc/passwd"},
        default_timeout_seconds=3.0,
    )
    allowed = engine.evaluate_tool_call(
        workspace_id="ws-1",
        request_id="req-3b",
        server_id="mcp-filesystem",
        tool_name="read_file",
        action="read",
        arguments={"path": "/workspace/README.md"},
        default_timeout_seconds=3.0,
    )

    assert denied.allowed is False
    assert "outside allowlist" in (denied.reason or "")
    assert allowed.allowed is True


@pytest.mark.unit
def test_policy_engine_enforces_max_tool_calls_per_request(tmp_path):
    config_path = _write_policy(
        tmp_path,
        {
            "default_workspace": "ws-1",
            "workspaces": {
                "ws-1": {
                    "allowed_mcp_servers": ["mcp-docs"],
                    "allowed_tool_actions": ["read"],
                    "allowed_tool_names": {"read": ["search_docs"]},
                    "max_tool_calls_per_request": 2,
                }
            },
        },
    )
    engine = ToolPolicyEngine.from_yaml(config_path)

    first = engine.evaluate_tool_call(
        workspace_id="ws-1",
        request_id="req-4",
        server_id="mcp-docs",
        tool_name="search_docs",
        action="read",
        arguments={"query": "first"},
        default_timeout_seconds=3.0,
    )
    second = engine.evaluate_tool_call(
        workspace_id="ws-1",
        request_id="req-4",
        server_id="mcp-docs",
        tool_name="search_docs",
        action="read",
        arguments={"query": "second"},
        default_timeout_seconds=3.0,
    )
    third = engine.evaluate_tool_call(
        workspace_id="ws-1",
        request_id="req-4",
        server_id="mcp-docs",
        tool_name="search_docs",
        action="read",
        arguments={"query": "third"},
        default_timeout_seconds=3.0,
    )

    assert first.allowed is True
    assert second.allowed is True
    assert third.allowed is False
    assert "max tool calls per request exceeded" in (third.reason or "")
