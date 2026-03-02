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

from tool_policy_engine import ToolPolicyEngine, load_default_tool_policy_engine


def _write_policy(tmp_path, payload: Dict[str, Any]) -> str:
    config_path = tmp_path / "tool-policy.yaml"
    config_path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return str(config_path)


def _base_payload() -> Dict[str, Any]:
    return {
        "default_workspace": "ws-1",
        "workspaces": {
            "ws-1": {
                "allowed_mcp_servers": ["mcp-docs", "mcp-filesystem"],
                "allowed_tool_actions": ["read"],
                "allowed_tool_names": {"read": ["search_docs", "read_file"]},
            }
        },
    }


@pytest.mark.unit
def test_policy_engine_denies_unknown_workspace_by_default(tmp_path):
    engine = ToolPolicyEngine.from_yaml(_write_policy(tmp_path, _base_payload()))

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
    assert "no tool policy configured" in (decision.reason or "")


@pytest.mark.unit
def test_policy_engine_enforces_allowlist_and_timeout(tmp_path):
    payload = _base_payload()
    payload["workspaces"]["ws-1"]["allowlists"] = {
        "servers": {"mcp-filesystem": {"path": ["/workspace/**"]}}
    }
    payload["workspaces"]["ws-1"]["per_call_timeout_seconds"] = 0.75
    engine = ToolPolicyEngine.from_yaml(_write_policy(tmp_path, payload))

    denied = engine.evaluate_tool_call(
        workspace_id="ws-1",
        request_id="req-2",
        server_id="mcp-filesystem",
        tool_name="read_file",
        action="read",
        arguments={"path": "/etc/passwd"},
        default_timeout_seconds=5.0,
    )
    allowed = engine.evaluate_tool_call(
        workspace_id="ws-1",
        request_id="req-3",
        server_id="mcp-filesystem",
        tool_name="read_file",
        action="read",
        arguments={"path": "/workspace/README.md"},
        default_timeout_seconds=5.0,
    )

    assert denied.allowed is False
    assert "outside allowlist" in (denied.reason or "")
    assert allowed.allowed is True
    assert allowed.timeout_seconds == 0.75


@pytest.mark.unit
def test_policy_engine_enforces_max_tool_calls_per_request(tmp_path):
    payload = _base_payload()
    payload["workspaces"]["ws-1"]["max_tool_calls_per_request"] = 2
    engine = ToolPolicyEngine.from_yaml(_write_policy(tmp_path, payload))

    first = engine.evaluate_tool_call(
        workspace_id="ws-1",
        request_id="req-limit",
        server_id="mcp-docs",
        tool_name="search_docs",
        action="read",
        arguments={"query": "a"},
        default_timeout_seconds=3.0,
    )
    second = engine.evaluate_tool_call(
        workspace_id="ws-1",
        request_id="req-limit",
        server_id="mcp-docs",
        tool_name="search_docs",
        action="read",
        arguments={"query": "b"},
        default_timeout_seconds=3.0,
    )
    third = engine.evaluate_tool_call(
        workspace_id="ws-1",
        request_id="req-limit",
        server_id="mcp-docs",
        tool_name="search_docs",
        action="read",
        arguments={"query": "c"},
        default_timeout_seconds=3.0,
    )

    assert first.allowed is True
    assert second.allowed is True
    assert third.allowed is False
    assert "max tool calls per request exceeded" in (third.reason or "")


@pytest.mark.unit
def test_policy_engine_supports_role_scoped_permissions(tmp_path):
    payload = {
        "default_workspace": "ws-1",
        "workspaces": {
            "ws-1": {
                "allowed_mcp_servers": ["mcp-github"],
                "default_role": "viewer",
                "roles": {
                    "viewer": {
                        "allowed_tool_actions": ["read"],
                        "tool_scopes": {"read": ["github_list_issues"]},
                    },
                    "developer": {
                        "allowed_tool_actions": ["read", "write"],
                        "tool_scopes": {
                            "read": ["github_list_issues"],
                            "write": ["github_create_issue"],
                        },
                        "required_scopes": {"write": ["mcp.tool.write"]},
                    },
                },
            }
        },
    }
    engine = ToolPolicyEngine.from_yaml(_write_policy(tmp_path, payload))

    denied = engine.evaluate_tool_call(
        workspace_id="ws-1",
        request_id="rbac-1",
        server_id="mcp-github",
        tool_name="github_create_issue",
        action="write",
        arguments={"title": "x"},
        role="viewer",
        scopes=["mcp.tool.write"],
        default_timeout_seconds=3.0,
    )
    allowed = engine.evaluate_tool_call(
        workspace_id="ws-1",
        request_id="rbac-2",
        server_id="mcp-github",
        tool_name="github_create_issue",
        action="write",
        arguments={"title": "x"},
        role="developer",
        scopes=["mcp.tool.write"],
        default_timeout_seconds=3.0,
    )

    assert denied.allowed is False
    assert "not allowed for role 'viewer'" in (denied.reason or "")
    assert allowed.allowed is True


@pytest.mark.unit
def test_policy_engine_redacts_arguments_from_policy_rules(tmp_path):
    payload = _base_payload()
    payload["workspaces"]["ws-1"]["redaction_rules"] = [
        {"argument": "token", "patterns": ["*"], "replacement": "[TOKEN_REDACTED]"},
        {"argument": "authorization", "patterns": ["Bearer *"]},
    ]
    engine = ToolPolicyEngine.from_yaml(_write_policy(tmp_path, payload))

    redacted, redactions = engine.redact_tool_arguments(
        workspace_id="ws-1",
        server_id="mcp-docs",
        tool_name="search_docs",
        arguments={
            "query": "hello",
            "token": "s3cr3t",
            "authorization": "Bearer abc.def.ghi",
        },
    )

    assert redactions == 2
    assert redacted["token"] == "[TOKEN_REDACTED]"
    assert redacted["authorization"] == "[REDACTED]"
    assert redacted["query"] == "hello"


@pytest.mark.unit
def test_policy_engine_rejects_invalid_redaction_rules(tmp_path):
    payload = _base_payload()
    payload["workspaces"]["ws-1"]["redaction_rules"] = [{"argument": "token", "patterns": []}]

    with pytest.raises(ValueError, match="patterns must include at least one pattern"):
        ToolPolicyEngine.from_yaml(_write_policy(tmp_path, payload))


@pytest.mark.unit
def test_load_default_policy_engine_falls_back_to_deny_by_default_on_invalid_config(
    tmp_path,
    monkeypatch,
):
    config_path = tmp_path / "tool-policy.yaml"
    config_path.write_text("workspaces:\n  - invalid\n", encoding="utf-8")
    monkeypatch.setenv("MCP_TOOL_POLICY_CONFIG", str(config_path))

    engine = load_default_tool_policy_engine()
    decision = engine.evaluate_tool_call(
        workspace_id="ws-1",
        request_id="req-invalid-loader",
        server_id="mcp-docs",
        tool_name="search_docs",
        action="read",
        arguments={"query": "hello"},
        default_timeout_seconds=3.0,
    )

    assert decision.allowed is False
    assert "no tool policy configured" in (decision.reason or "")
