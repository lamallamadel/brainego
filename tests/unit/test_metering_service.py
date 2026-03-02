# Needs: python-package:pytest>=9.0.2

from datetime import datetime

import pytest

from metering_service import MeteringService


@pytest.mark.unit
def test_add_event_requires_workspace_id_before_db_access() -> None:
    service = MeteringService.__new__(MeteringService)

    with pytest.raises(ValueError, match="workspace_id is required for metering events"):
        service.add_event(workspace_id="", meter_key="rag.query.requests")


@pytest.mark.unit
def test_add_event_requires_meter_key_before_db_access() -> None:
    service = MeteringService.__new__(MeteringService)

    with pytest.raises(ValueError, match="meter_key is required for metering events"):
        service.add_event(workspace_id="ws-1", meter_key="")


@pytest.mark.unit
def test_build_summary_filters_supports_workspace_user_key_and_dates() -> None:
    start = datetime(2026, 1, 1, 0, 0, 0)
    end = datetime(2026, 1, 31, 23, 59, 59)

    where_sql, params = MeteringService._build_summary_filters(
        workspace_id="ws-1",
        user_id="user-1",
        meter_key="rag.query.requests",
        start_date=start,
        end_date=end,
    )

    assert "workspace_id = %s" in where_sql
    assert "user_id = %s" in where_sql
    assert "meter_key = %s" in where_sql
    assert "created_at >= %s" in where_sql
    assert "created_at <= %s" in where_sql
    assert params == ["ws-1", "user-1", "rag.query.requests", start, end]


@pytest.mark.unit
def test_normalize_optional_user_id_trims_and_allows_none() -> None:
    assert MeteringService._normalize_optional_user_id("  user-1  ") == "user-1"
    assert MeteringService._normalize_optional_user_id("   ") is None
    assert MeteringService._normalize_optional_user_id(None) is None
