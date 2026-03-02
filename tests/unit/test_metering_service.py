# Needs: python-package:pytest>=9.0.2

import json
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
    assert params == ["ws-1", "rag.query.requests", start, end]


@pytest.mark.unit
def test_add_event_redacts_sensitive_values_before_insert() -> None:
    service = MeteringService.__new__(MeteringService)
    captured = {}

    class _FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, query, params):
            if "INSERT INTO workspace_metering_events" in query:
                captured["params"] = params

        def fetchone(self):
            return ("evt-metering-redacted", datetime(2026, 3, 1, 0, 0, 0))

    class _FakeConnection:
        def cursor(self):
            return _FakeCursor()

        def commit(self):
            captured["committed"] = True

        def rollback(self):
            captured["rolled_back"] = True

    service._get_connection = lambda: _FakeConnection()
    service._return_connection = lambda conn: captured.setdefault("returned", True)

    result = service.add_event(
        workspace_id="ws-redaction",
        meter_key="usage.alice@example.com",
        quantity=1.0,
        request_id="req-alice@example.com",
        metadata={
            "email": "alice@example.com",
            "token": "sk-secretvalue12345",
            "ip": "203.0.113.10",
        },
        event_id="evt-metering-fixed",
        created_at=datetime(2026, 3, 1, 0, 0, 0),
    )

    assert result["status"] == "success"
    assert captured.get("committed") is True
    params = captured["params"]
    metadata_payload = json.loads(params[5])

    assert "alice@example.com" not in str(params)
    assert "sk-secretvalue12345" not in str(params)
    assert "203.0.113.10" not in str(params)
    assert metadata_payload["email"] == "[REDACTED_SECRET]"
    assert metadata_payload["token"] == "[REDACTED_SECRET]"
    assert metadata_payload["ip"] == "[REDACTED_SECRET]"
    assert params == ["ws-1", "user-1", "rag.query.requests", start, end]


@pytest.mark.unit
def test_normalize_optional_user_id_trims_and_allows_none() -> None:
    assert MeteringService._normalize_optional_user_id("  user-1  ") == "user-1"
    assert MeteringService._normalize_optional_user_id("   ") is None
    assert MeteringService._normalize_optional_user_id(None) is None
