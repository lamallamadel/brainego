# Needs: python-package:pytest>=9.0.2

"""Unit tests for audit_service.py logic that does not require a real database."""

import json
from datetime import datetime

import pytest

from audit_service import AuditService


@pytest.mark.unit
def test_build_filters_supports_workspace_user_date_and_tool():
    start = datetime(2026, 1, 1, 0, 0, 0)
    end = datetime(2026, 1, 31, 23, 59, 59)

    where_sql, params = AuditService._build_filters(
        workspace_id="ws-1",
        user_id="user-1",
        role="workspace_admin",
        tool_name="search_docs",
        event_type="tool_call",
        start_date=start,
        end_date=end,
    )

    assert "workspace_id = %s" in where_sql
    assert "user_id = %s" in where_sql
    assert "role = %s" in where_sql
    assert "tool_name = %s" in where_sql
    assert "event_type = %s" in where_sql
    assert "timestamp >= %s" in where_sql
    assert "timestamp <= %s" in where_sql
    assert params == ["ws-1", "user-1", "workspace_admin", "search_docs", "tool_call", start, end]


@pytest.mark.unit
def test_to_csv_serializes_nested_payloads():
    events = [
        {
            "event_id": "evt-1",
            "event_type": "request",
            "timestamp": "2026-03-01T10:00:00Z",
            "request_id": "req-1",
            "workspace_id": "ws-1",
            "user_id": "user-1",
            "tool_name": "search_docs",
            "endpoint": "/v1/mcp",
            "method": "POST",
            "status_code": 200,
            "duration_ms": 12.5,
            "request_payload": {"action": "call_tool"},
            "response_payload": {"ok": True},
            "metadata": {"source": "unit-test"},
        }
    ]

    csv_data = AuditService._to_csv(events)

    assert "event_id,event_type,timestamp,request_id" in csv_data
    assert "evt-1,request,2026-03-01T10:00:00Z,req-1" in csv_data
    assert '"{""action"": ""call_tool""}"' in csv_data
    assert '"{""ok"": true}"' in csv_data


@pytest.mark.unit
def test_export_events_json_uses_list_events_result(monkeypatch):
    service = AuditService.__new__(AuditService)

    def _fake_list_events(**kwargs):
        assert kwargs["workspace_id"] == "workspace-a"
        assert kwargs["user_id"] == "user-a"
        assert kwargs["role"] == "workspace_reader"
        assert kwargs["tool_name"] == "tool-a"
        return {
            "status": "success",
            "total_events": 2,
            "count": 1,
            "events": [{"event_id": "evt-1"}],
        }

    monkeypatch.setattr(service, "list_events", _fake_list_events)

    result = service.export_events(
        export_format="json",
        workspace_id="workspace-a",
        user_id="user-a",
        role="workspace_reader",
        tool_name="tool-a",
        limit=25,
        offset=5,
    )

    assert result["status"] == "success"
    assert result["format"] == "json"
    assert result["total_events"] == 2
    assert result["count"] == 1
    assert result["events"] == [{"event_id": "evt-1"}]
    assert result["filters"]["workspace_id"] == "workspace-a"
    assert result["filters"]["user_id"] == "user-a"
    assert result["filters"]["role"] == "workspace_reader"
    assert result["filters"]["tool_name"] == "tool-a"


@pytest.mark.unit
def test_export_events_csv_returns_csv_payload(monkeypatch):
    service = AuditService.__new__(AuditService)

    monkeypatch.setattr(
        service,
        "list_events",
        lambda **kwargs: {
            "status": "success",
            "total_events": 1,
            "count": 1,
            "events": [
                {
                    "event_id": "evt-csv",
                    "event_type": "tool_call",
                    "timestamp": "2026-03-01T00:00:00+00:00",
                    "request_id": "req-csv",
                    "workspace_id": "ws-csv",
                    "user_id": "user-csv",
                    "tool_name": "notion.search",
                    "endpoint": "/internal/mcp/tools/call",
                    "method": "POST",
                    "status_code": 200,
                    "duration_ms": 20.0,
                    "request_payload": {"tool_name": "notion.search"},
                    "response_payload": {"ok": True},
                    "metadata": {"ok": True},
                }
            ],
        },
    )

    result = service.export_events(export_format="csv")

    assert result["status"] == "success"
    assert result["format"] == "csv"
    assert result["total_events"] == 1
    assert "csv_data" in result
    assert "evt-csv,tool_call" in result["csv_data"]


@pytest.mark.unit
def test_export_events_rejects_unknown_format():
    service = AuditService.__new__(AuditService)
    with pytest.raises(ValueError, match="export_format must be one of: json, csv"):
        service.export_events(export_format="xml")


@pytest.mark.unit
def test_add_event_redacts_sensitive_values_before_insert() -> None:
    service = AuditService.__new__(AuditService)
    captured = {}

    class _FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, query, params):
            if "INSERT INTO audit_events" in query:
                captured["params"] = params

        def fetchone(self):
            return ("evt-redacted", datetime(2026, 3, 1, 0, 0, 0))

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
        event_type="request",
        request_id="trace-alice@example.com",
        endpoint="/v1/rag/query",
        method="POST",
        status_code=200,
        workspace_id="ws-redaction",
        user_id="alice@example.com",
        role="viewer",
        tool_name="contacts.lookup",
        duration_ms=12.5,
        request_payload={
            "email": "alice@example.com",
            "token": "sk-secretvalue12345",
        },
        response_payload={"client_ip": "203.0.113.10"},
        metadata={"phone": "+1 415-555-1212"},
        event_id="evt-fixed",
        timestamp=datetime(2026, 3, 1, 0, 0, 0),
    )

    assert result["status"] == "success"
    assert captured.get("committed") is True
    params = captured["params"]

    assert "alice@example.com" not in str(params)
    assert "sk-secretvalue12345" not in str(params)
    assert "203.0.113.10" not in str(params)
    assert "415-555-1212" not in str(params)

    request_payload = json.loads(params[12])
    response_payload = json.loads(params[13])
    metadata = json.loads(params[14])

    assert request_payload["email"] == "[REDACTED_SECRET]"
    assert request_payload["token"] == "[REDACTED_SECRET]"
    assert response_payload["client_ip"] == "[REDACTED_SECRET]"
    assert "415-555-1212" not in metadata["phone"]
    assert "[REDACTED_SECRET]" in metadata["phone"]
