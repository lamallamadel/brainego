# Needs: python-package:pytest>=9.0.2
# Needs: python-package:fastapi>=0.104.1
"""Unit tests for workspace RBAC privilege escalation denial."""

from __future__ import annotations

import pathlib
import sys
from typing import Any, Dict
from unittest.mock import MagicMock, Mock

import pytest
from fastapi import HTTPException, Request

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Import after path setup
from api_server import (
    AUTH_ROLE_CONTEXT,
    enforce_mcp_tool_policy,
    _normalize_mcp_policy_role,
    _role_priority,
)


@pytest.mark.unit
def test_role_priority_ordering():
    """Verify role priority is correctly ordered: viewer < developer < admin."""
    assert _role_priority("viewer") == 0
    assert _role_priority("developer") == 1
    assert _role_priority("admin") == 2
    assert _role_priority("unknown") == -1
    assert _role_priority(None) == -1


@pytest.mark.unit
def test_normalize_mcp_policy_role_defaults_to_viewer():
    """Verify unknown roles default to viewer for least privilege."""
    assert _normalize_mcp_policy_role("viewer") == "viewer"
    assert _normalize_mcp_policy_role("developer") == "developer"
    assert _normalize_mcp_policy_role("admin") == "admin"
    assert _normalize_mcp_policy_role("unknown") == "unknown"
    assert _normalize_mcp_policy_role("") == "viewer"
    assert _normalize_mcp_policy_role(None) == "viewer"


@pytest.mark.unit
def test_enforce_mcp_tool_policy_rejects_viewer_to_developer_escalation():
    """Viewer attempting to escalate to developer role should be rejected."""
    # Setup mock request with viewer authentication
    mock_request = Mock(spec=Request)
    mock_request.state = Mock()
    mock_request.state.workspace_id = "ws-test"
    mock_request.state.auth_role = "viewer"
    mock_request.headers = {"x-workspace-id": "ws-test"}
    
    # Mock services
    workspace_service = MagicMock()
    workspace_service.assert_workspace_active = MagicMock(return_value="ws-test")
    
    from api_server import workspace_service as ws_svc_module
    original_ws_svc = ws_svc_module
    
    # Patch workspace service getter
    import api_server
    api_server.workspace_service = workspace_service
    
    try:
        # Set authenticated role context to viewer
        token = AUTH_ROLE_CONTEXT.set("viewer")
        try:
            with pytest.raises(HTTPException) as exc_info:
                enforce_mcp_tool_policy(
                    raw_request=mock_request,
                    server_id="mcp-test",
                    tool_name="write_file",
                    workspace_id="ws-test",
                    request_id="req-1",
                    action="write",
                    role="developer",  # Attempting escalation
                    scopes=["filesystem:write"],
                )
            
            assert exc_info.value.status_code == 403
            detail = exc_info.value.detail
            assert "role escalation denied" in detail["reason"]
            assert "viewer" in detail["reason"]
            assert "developer" in detail["reason"]
        finally:
            AUTH_ROLE_CONTEXT.reset(token)
    finally:
        api_server.workspace_service = original_ws_svc


@pytest.mark.unit
def test_enforce_mcp_tool_policy_rejects_developer_to_admin_escalation():
    """Developer attempting to escalate to admin role should be rejected."""
    mock_request = Mock(spec=Request)
    mock_request.state = Mock()
    mock_request.state.workspace_id = "ws-test"
    mock_request.state.auth_role = "developer"
    mock_request.headers = {"x-workspace-id": "ws-test"}
    
    workspace_service = MagicMock()
    workspace_service.assert_workspace_active = MagicMock(return_value="ws-test")
    
    import api_server
    original_ws_svc = api_server.workspace_service
    api_server.workspace_service = workspace_service
    
    try:
        token = AUTH_ROLE_CONTEXT.set("developer")
        try:
            with pytest.raises(HTTPException) as exc_info:
                enforce_mcp_tool_policy(
                    raw_request=mock_request,
                    server_id="mcp-admin",
                    tool_name="disable_workspace",
                    workspace_id="ws-test",
                    request_id="req-2",
                    action="delete",
                    role="admin",  # Attempting escalation
                    scopes=["admin:workspaces"],
                )
            
            assert exc_info.value.status_code == 403
            detail = exc_info.value.detail
            assert "role escalation denied" in detail["reason"]
            assert "developer" in detail["reason"]
            assert "admin" in detail["reason"]
        finally:
            AUTH_ROLE_CONTEXT.reset(token)
    finally:
        api_server.workspace_service = original_ws_svc


@pytest.mark.unit
def test_enforce_mcp_tool_policy_rejects_viewer_to_admin_escalation():
    """Viewer attempting to escalate directly to admin should be rejected."""
    mock_request = Mock(spec=Request)
    mock_request.state = Mock()
    mock_request.state.workspace_id = "ws-test"
    mock_request.state.auth_role = "viewer"
    mock_request.headers = {"x-workspace-id": "ws-test"}
    
    workspace_service = MagicMock()
    workspace_service.assert_workspace_active = MagicMock(return_value="ws-test")
    
    import api_server
    original_ws_svc = api_server.workspace_service
    api_server.workspace_service = workspace_service
    
    try:
        token = AUTH_ROLE_CONTEXT.set("viewer")
        try:
            with pytest.raises(HTTPException) as exc_info:
                enforce_mcp_tool_policy(
                    raw_request=mock_request,
                    server_id="mcp-admin",
                    tool_name="delete_all_workspaces",
                    workspace_id="ws-test",
                    request_id="req-3",
                    action="delete",
                    role="admin",  # Attempting escalation
                    scopes=["admin:*"],
                )
            
            assert exc_info.value.status_code == 403
            detail = exc_info.value.detail
            assert "role escalation denied" in detail["reason"]
            assert "viewer" in detail["reason"]
            assert "admin" in detail["reason"]
        finally:
            AUTH_ROLE_CONTEXT.reset(token)
    finally:
        api_server.workspace_service = original_ws_svc


@pytest.mark.unit
def test_enforce_mcp_tool_policy_allows_same_role():
    """Authenticated user can request their own role (no escalation)."""
    mock_request = Mock(spec=Request)
    mock_request.state = Mock()
    mock_request.state.workspace_id = "ws-test"
    mock_request.state.auth_role = "developer"
    mock_request.headers = {"x-workspace-id": "ws-test", "x-request-id": "req-4"}
    
    workspace_service = MagicMock()
    workspace_service.assert_workspace_active = MagicMock(return_value="ws-test")
    
    tool_policy_engine = MagicMock()
    policy_decision = MagicMock()
    policy_decision.allowed = True
    policy_decision.workspace_id = "ws-test"
    policy_decision.timeout_seconds = 10.0
    tool_policy_engine.evaluate_tool_call = MagicMock(return_value=policy_decision)
    
    import api_server
    original_ws_svc = api_server.workspace_service
    original_tool_policy = api_server.tool_policy_engine
    api_server.workspace_service = workspace_service
    api_server.tool_policy_engine = tool_policy_engine
    
    try:
        token = AUTH_ROLE_CONTEXT.set("developer")
        try:
            result = enforce_mcp_tool_policy(
                raw_request=mock_request,
                server_id="mcp-filesystem",
                tool_name="write_file",
                workspace_id="ws-test",
                request_id="req-4",
                action="write",
                role="developer",  # Same as authenticated role
                scopes=None,
            )
            # Should succeed (no exception)
            assert result[0] == "ws-test"
        finally:
            AUTH_ROLE_CONTEXT.reset(token)
    finally:
        api_server.workspace_service = original_ws_svc
        api_server.tool_policy_engine = original_tool_policy


@pytest.mark.unit
def test_enforce_mcp_tool_policy_rejects_client_controlled_scopes_when_authenticated():
    """Authenticated users cannot provide scopes in request body (must use auth token scopes)."""
    mock_request = Mock(spec=Request)
    mock_request.state = Mock()
    mock_request.state.workspace_id = "ws-test"
    mock_request.state.auth_role = "developer"
    mock_request.headers = {"x-workspace-id": "ws-test"}
    
    workspace_service = MagicMock()
    workspace_service.assert_workspace_active = MagicMock(return_value="ws-test")
    
    import api_server
    original_ws_svc = api_server.workspace_service
    api_server.workspace_service = workspace_service
    
    try:
        token = AUTH_ROLE_CONTEXT.set("developer")
        try:
            with pytest.raises(HTTPException) as exc_info:
                enforce_mcp_tool_policy(
                    raw_request=mock_request,
                    server_id="mcp-filesystem",
                    tool_name="write_file",
                    workspace_id="ws-test",
                    request_id="req-5",
                    action="write",
                    role="developer",
                    scopes=["filesystem:write", "admin:*"],  # Client-controlled scopes
                )
            
            assert exc_info.value.status_code == 403
            detail = exc_info.value.detail
            assert "scopes cannot be provided in request body" in detail["reason"]
        finally:
            AUTH_ROLE_CONTEXT.reset(token)
    finally:
        api_server.workspace_service = original_ws_svc


@pytest.mark.unit
def test_enforce_mcp_tool_policy_allows_role_downgrade():
    """Admin can request lower privilege role (admin → developer)."""
    mock_request = Mock(spec=Request)
    mock_request.state = Mock()
    mock_request.state.workspace_id = "ws-test"
    mock_request.state.auth_role = "admin"
    mock_request.headers = {"x-workspace-id": "ws-test", "x-request-id": "req-6"}
    
    workspace_service = MagicMock()
    workspace_service.assert_workspace_active = MagicMock(return_value="ws-test")
    
    tool_policy_engine = MagicMock()
    policy_decision = MagicMock()
    policy_decision.allowed = True
    policy_decision.workspace_id = "ws-test"
    policy_decision.timeout_seconds = 10.0
    tool_policy_engine.evaluate_tool_call = MagicMock(return_value=policy_decision)
    
    import api_server
    original_ws_svc = api_server.workspace_service
    original_tool_policy = api_server.tool_policy_engine
    api_server.workspace_service = workspace_service
    api_server.tool_policy_engine = tool_policy_engine
    
    try:
        token = AUTH_ROLE_CONTEXT.set("admin")
        try:
            result = enforce_mcp_tool_policy(
                raw_request=mock_request,
                server_id="mcp-test",
                tool_name="read_file",
                workspace_id="ws-test",
                request_id="req-6",
                action="read",
                role="developer",  # Lower privilege than admin (allowed)
                scopes=None,
            )
            # Should succeed
            assert result[0] == "ws-test"
        finally:
            AUTH_ROLE_CONTEXT.reset(token)
    finally:
        api_server.workspace_service = original_ws_svc
        api_server.tool_policy_engine = original_tool_policy
