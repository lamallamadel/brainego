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


def _rbac_payload() -> Dict[str, Any]:
    return {
        "default_workspace": "ws-1",
        "default_role": "viewer",
        "workspaces": {
            "ws-1": {
                "allowed_mcp_servers": ["mcp-github"],
                "roles": {
                    "admin": {
                        "allowed_tool_actions": ["read", "write", "delete"],
                        "tool_scopes": {
                            "read": ["*"],
                            "write": ["*"],
                            "delete": ["*"],
                        },
                    },
                    "developer": {
                        "allowed_tool_actions": ["read", "write"],
                        "tool_scopes": {
                            "read": ["github_list_issues"],
                            "write": ["github_create_issue"],
                        },
                        "required_scopes": {
                            "write": ["mcp.tool.write"],
                        },
                    },
                    "viewer": {
                        "allowed_tool_actions": ["read"],
                        "tool_scopes": {
                            "read": ["github_list_issues"],
                        },
                    },
                },
            }
        },
    }


@pytest.mark.unit
def test_policy_engine_rbac_viewer_cannot_call_write_tool(tmp_path):
    config_path = _write_policy(tmp_path, _rbac_payload())
    engine = ToolPolicyEngine.from_yaml(config_path)

    decision = engine.evaluate_tool_call(
        workspace_id="ws-1",
        request_id="req-rbac-1",
        server_id="mcp-github",
        tool_name="github_create_issue",
        action="write",
        arguments={"title": "AFR-86"},
        role="viewer",
        scopes=["mcp.tool.write"],
        default_timeout_seconds=3.0,
    )

    assert decision.allowed is False
    assert "not allowed for role 'viewer'" in (decision.reason or "")


@pytest.mark.unit
def test_policy_engine_rbac_developer_write_requires_explicit_scope(tmp_path):
    config_path = _write_policy(tmp_path, _rbac_payload())
    engine = ToolPolicyEngine.from_yaml(config_path)

    denied = engine.evaluate_tool_call(
        workspace_id="ws-1",
        request_id="req-rbac-2",
        server_id="mcp-github",
        tool_name="github_create_issue",
        action="write",
        arguments={"title": "AFR-86"},
        role="developer",
        scopes=[],
        default_timeout_seconds=3.0,
    )
    allowed = engine.evaluate_tool_call(
        workspace_id="ws-1",
        request_id="req-rbac-3",
        server_id="mcp-github",
        tool_name="github_create_issue",
        action="write",
        arguments={"title": "AFR-86"},
        role="developer",
        scopes=["mcp.tool.write"],
        default_timeout_seconds=3.0,
    )

    assert denied.allowed is False
    assert "missing required scope" in (denied.reason or "")
    assert allowed.allowed is True


@pytest.mark.unit
def test_policy_engine_supports_workspace_policy_upsert_for_admin_workflows(tmp_path):
    config_path = _write_policy(tmp_path, _rbac_payload())
    engine = ToolPolicyEngine.from_yaml(config_path)

    updated = engine.upsert_workspace_policy(
        "ws-2",
        {
            "allowed_mcp_servers": ["mcp-filesystem"],
            "default_role": "viewer",
            "roles": {
                "admin": {
                    "allowed_tool_actions": ["read", "write", "delete"],
                    "tool_scopes": {"read": ["*"], "write": ["*"], "delete": ["*"]},
                },
                "developer": {
                    "allowed_tool_actions": ["read", "write"],
                    "tool_scopes": {"read": ["read_file"], "write": ["write_file"]},
                    "required_scopes": {"write": ["mcp.tool.write"]},
                },
                "viewer": {
                    "allowed_tool_actions": ["read"],
                    "tool_scopes": {"read": ["read_file"]},
                },
            },
        },
    )

    snapshot = engine.get_workspace_policy("ws-2")
    assert updated["default_role"] == "viewer"
    assert snapshot["default_role"] == "viewer"
    assert snapshot["allowed_mcp_servers"] == ["mcp-filesystem"]
    assert snapshot["roles"]["developer"]["required_scopes"]["write"] == ["mcp.tool.write"]
