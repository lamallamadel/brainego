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
