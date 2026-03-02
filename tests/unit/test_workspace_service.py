# Needs: python-package:pytest>=9.0.2

import pytest

from workspace_service import WorkspaceService


@pytest.mark.unit
def test_normalize_workspace_id_rejects_empty_values() -> None:
    with pytest.raises(ValueError, match="workspace_id must be a non-empty string"):
        WorkspaceService._normalize_workspace_id(None)

    with pytest.raises(ValueError, match="workspace_id must be a non-empty string"):
        WorkspaceService._normalize_workspace_id("   ")


@pytest.mark.unit
def test_assert_workspace_active_rejects_unknown_workspace() -> None:
    service = WorkspaceService.__new__(WorkspaceService)
    service.get_workspace = lambda workspace_id: None

    with pytest.raises(ValueError, match="does not exist"):
        service.assert_workspace_active("ws-missing", context="unit-test")


@pytest.mark.unit
def test_assert_workspace_active_rejects_disabled_workspace() -> None:
    service = WorkspaceService.__new__(WorkspaceService)
    service.get_workspace = lambda workspace_id: {
        "workspace_id": workspace_id,
        "status": "disabled",
    }

    with pytest.raises(ValueError, match="is disabled"):
        service.assert_workspace_active("ws-disabled", context="unit-test")


@pytest.mark.unit
def test_assert_workspace_active_accepts_active_workspace() -> None:
    service = WorkspaceService.__new__(WorkspaceService)
    service.get_workspace = lambda workspace_id: {
        "workspace_id": workspace_id,
        "status": "active",
    }

    resolved = service.assert_workspace_active(" ws-ok ", context="unit-test")
    assert resolved == "ws-ok"


@pytest.mark.unit
def test_get_workspace_policy_returns_policy_fields_from_metadata() -> None:
    """get_workspace_policy extracts policy fields from metadata JSONB column."""
    service = WorkspaceService.__new__(WorkspaceService)
    service.get_workspace = lambda workspace_id: {
        "workspace_id": workspace_id,
        "status": "active",
        "metadata": {
            "tool_policy_override": {"allowed_mcp_servers": ["mcp-test"]},
            "quota_limits": {"max_requests_per_day": 1000},
            "allowed_models": ["llama-3.3-8b"],
            "allowed_mcp_servers": ["mcp-test", "mcp-docs"],
            "other_field": "should not be returned",
        },
    }

    policy = service.get_workspace_policy("ws-test")

    assert policy["tool_policy_override"] == {"allowed_mcp_servers": ["mcp-test"]}
    assert policy["quota_limits"] == {"max_requests_per_day": 1000}
    assert policy["allowed_models"] == ["llama-3.3-8b"]
    assert policy["allowed_mcp_servers"] == ["mcp-test", "mcp-docs"]
    assert "other_field" not in policy


@pytest.mark.unit
def test_get_workspace_policy_raises_when_workspace_does_not_exist() -> None:
    """get_workspace_policy raises ValueError when workspace does not exist."""
    service = WorkspaceService.__new__(WorkspaceService)
    service.get_workspace = lambda workspace_id: None

    with pytest.raises(ValueError, match="does not exist"):
        service.get_workspace_policy("ws-missing")


@pytest.mark.unit
def test_get_workspace_policy_returns_none_fields_when_metadata_empty() -> None:
    """get_workspace_policy returns None for policy fields when metadata is empty."""
    service = WorkspaceService.__new__(WorkspaceService)
    service.get_workspace = lambda workspace_id: {
        "workspace_id": workspace_id,
        "status": "active",
        "metadata": {},
    }

    policy = service.get_workspace_policy("ws-test")

    assert policy["tool_policy_override"] is None
    assert policy["quota_limits"] is None
    assert policy["allowed_models"] is None
    assert policy["allowed_mcp_servers"] is None
