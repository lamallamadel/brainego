# Needs: python-package:pytest>=9.0.2

import pytest

from audit_service import AuditService


@pytest.mark.unit
def test_add_event_requires_workspace_id_before_db_access() -> None:
    service = AuditService.__new__(AuditService)

    with pytest.raises(ValueError, match="workspace_id is required for audit events"):
        service.add_event(
            event_type="request",
            request_id="req-1",
            endpoint="/health",
            method="GET",
            status_code=200,
            workspace_id=None,
        )
