# Needs: python-package:pytest>=9.0.2
# Needs: python-package:pyyaml>=6.0.1

"""Integration tests for MCP tool allow/deny + write confirmation flow."""

from __future__ import annotations

import pathlib
import sys
from typing import Any, Dict, Optional

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mcp_write_confirmation import PendingWritePlanStore, evaluate_write_confirmation_gate
from tool_policy_engine import ToolPolicyEngine


def _write_policy(tmp_path, payload: Dict[str, Any]) -> str:
    config_path = tmp_path / "tool-policy.yaml"
    config_path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return str(config_path)


def _base_policy_payload() -> Dict[str, Any]:
    return {
        "default_workspace": "ws-1",
        "workspaces": {
            "ws-1": {
                "allowed_mcp_servers": ["mcp-github"],
                "allowed_tool_actions": ["read", "write"],
                "allowed_tool_names": {
                    "read": ["github_list_issues"],
                    "write": ["github_create_issue"],
                },
                "allowlists": {
                    "tools": {
                        "github_create_issue": {
                            "repository": ["brainego/*"],
                        }
                    }
                },
            }
        },
    }


def _evaluate_flow(
    *,
    engine: ToolPolicyEngine,
    confirmation_store: PendingWritePlanStore,
    request_id: str,
    server_id: str,
    tool_name: str,
    action: str,
    arguments: Dict[str, Any],
    requested_by: str,
    confirm: bool = False,
    confirmation_id: Optional[str] = None,
) -> Dict[str, Any]:
    policy_decision = engine.evaluate_tool_call(
        workspace_id="ws-1",
        request_id=request_id,
        server_id=server_id,
        tool_name=tool_name,
        action=action,
        arguments=arguments,
        default_timeout_seconds=10.0,
    )
    if not policy_decision.allowed:
        return {
            "status": "policy_denied",
            "reason": policy_decision.reason,
        }

    confirmation_decision = evaluate_write_confirmation_gate(
        store=confirmation_store,
        requested_by=requested_by,
        server_id=server_id,
        tool_name=tool_name,
        arguments=arguments,
        confirm=confirm,
        confirmation_id=confirmation_id,
    )
    if confirmation_decision.status_code:
        return {
            "status": "confirmation_denied",
            "status_code": confirmation_decision.status_code,
            "reason": confirmation_decision.reason,
        }
    if confirmation_decision.pending_plan:
        return {
            "status": "pending_confirmation",
            "confirmation_id": confirmation_decision.pending_plan.confirmation_id,
        }
    return {"status": "allowed"}


@pytest.mark.integration
def test_integration_denies_write_outside_allowlist_boundary(tmp_path) -> None:
    engine = ToolPolicyEngine.from_yaml(_write_policy(tmp_path, _base_policy_payload()))
    store = PendingWritePlanStore(ttl_seconds=600)

    flow = _evaluate_flow(
        engine=engine,
        confirmation_store=store,
        request_id="req-deny-boundary",
        server_id="mcp-github",
        tool_name="github_create_issue",
        action="write",
        arguments={"repository": "attacker/repo", "title": "AFR-106"},
        requested_by="sk-test-key-123",
    )

    assert flow["status"] == "policy_denied"
    assert "outside allowlist" in str(flow.get("reason"))


@pytest.mark.integration
def test_integration_requires_confirmation_for_allowed_write_then_allows_confirmed_replay(
    tmp_path,
) -> None:
    engine = ToolPolicyEngine.from_yaml(_write_policy(tmp_path, _base_policy_payload()))
    store = PendingWritePlanStore(ttl_seconds=600)

    first = _evaluate_flow(
        engine=engine,
        confirmation_store=store,
        request_id="req-pending-1",
        server_id="mcp-github",
        tool_name="github_create_issue",
        action="write",
        arguments={"repository": "brainego/core", "title": "AFR-106"},
        requested_by="sk-test-key-123",
    )
    assert first["status"] == "pending_confirmation"
    assert first.get("confirmation_id")

    second = _evaluate_flow(
        engine=engine,
        confirmation_store=store,
        request_id="req-pending-2",
        server_id="mcp-github",
        tool_name="github_create_issue",
        action="write",
        arguments={"repository": "brainego/core", "title": "AFR-106"},
        requested_by="sk-test-key-123",
        confirm=True,
        confirmation_id=first["confirmation_id"],
    )
    assert second["status"] == "allowed"


@pytest.mark.integration
def test_integration_rejects_confirm_true_without_confirmation_id_for_write_tool(tmp_path) -> None:
    engine = ToolPolicyEngine.from_yaml(_write_policy(tmp_path, _base_policy_payload()))
    store = PendingWritePlanStore(ttl_seconds=600)

    flow = _evaluate_flow(
        engine=engine,
        confirmation_store=store,
        request_id="req-missing-confirmation-id",
        server_id="mcp-github",
        tool_name="github_create_issue",
        action="write",
        arguments={"repository": "brainego/core", "title": "AFR-106"},
        requested_by="sk-test-key-123",
        confirm=True,
        confirmation_id=None,
    )

    assert flow["status"] == "confirmation_denied"
    assert flow["status_code"] == 400
    assert flow["reason"] == "confirm=true requires confirmation_id"


@pytest.mark.integration
def test_integration_allows_read_tool_without_confirmation_gate(tmp_path) -> None:
    engine = ToolPolicyEngine.from_yaml(_write_policy(tmp_path, _base_policy_payload()))
    store = PendingWritePlanStore(ttl_seconds=600)

    flow = _evaluate_flow(
        engine=engine,
        confirmation_store=store,
        request_id="req-read-allowed",
        server_id="mcp-github",
        tool_name="github_list_issues",
        action="read",
        arguments={"repository": "brainego/core"},
        requested_by="sk-test-key-123",
    )

    assert flow["status"] == "allowed"
