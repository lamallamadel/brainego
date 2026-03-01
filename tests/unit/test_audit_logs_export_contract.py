# Needs: python-package:pytest>=9.0.2

"""Contract tests for AFR-99 audit schema wiring."""

from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_api_server_wires_audit_service_and_request_middleware() -> None:
    api_server = _read("api_server.py")

    assert "from audit_service import AuditService" in api_server
    assert "audit_service = None" in api_server
    assert "def get_audit_service() -> AuditService:" in api_server
    assert '@app.middleware("http")' in api_server
    assert "async def audit_request_middleware(request: Request, call_next):" in api_server
    assert 'event_type="request_event"' in api_server
    assert "get_audit_service().add_event(" in api_server


def test_audit_export_endpoint_supports_required_filters_and_formats() -> None:
    api_server = _read("api_server.py")

    assert '@app.get("/audit", response_model=AuditExportResponse)' in api_server
    assert 'format: str = Query("json", pattern="^(json|csv)$"' in api_server
    assert "workspace_id: Optional[str] = Query(None, description=\"Filter by workspace identifier\")" in api_server
    assert "user_id: Optional[str] = Query(None, description=\"Filter by user identifier\")" in api_server
    assert "role: Optional[str] = Query(None, description=\"Filter by resolved role\")" in api_server
    assert "model: Optional[str] = Query(None, description=\"Filter by model identifier\")" in api_server
    assert "status: Optional[str] = Query(None, description=\"Filter by event status\")" in api_server
    assert "tool_name: Optional[str] = Query(None, description=\"Filter by tool name\")" in api_server
    assert "pattern=AUDIT_EVENT_TYPE_QUERY_PATTERN" in api_server
    assert "_normalize_audit_event_type(event_type or query_params.get(\"type\"))" in api_server
    assert "start_date: Optional[str] = Query(None, description=\"Start date (ISO-8601)\")" in api_server
    assert "end_date: Optional[str] = Query(None, description=\"End date (ISO-8601)\")" in api_server
    assert "service.export_events(" in api_server
    assert 'media_type="text/csv"' in api_server


def test_tool_call_routes_emit_dedicated_audit_events() -> None:
    api_server = _read("api_server.py")

    assert "def _record_tool_call_audit(" in api_server
    assert 'event_type="tool_event"' in api_server
    assert "async def internal_mcp_tool_call(request: MCPToolProxyRequest, raw_request: Request):" in api_server
    assert "async def proxy_mcp_gateway(request: MCPGatewayRequest, raw_request: Request):" in api_server
    assert "_record_tool_call_audit(" in api_server
    assert "\"event_schema\": \"tool_event.v1\"" in api_server
    assert '"role": auth_role' in api_server


def test_init_sql_declares_audit_table_and_indexes() -> None:
    init_sql = _read("init-scripts/postgres/init.sql")

    assert "CREATE TABLE IF NOT EXISTS audit_events" in init_sql
    assert "event_type IN ('request_event', 'tool_event', 'request', 'tool_call', 'mcp_tool_call')" in init_sql
    assert "workspace_id VARCHAR(255)" in init_sql
    assert "user_id VARCHAR(255)" in init_sql
    assert "role VARCHAR(64)" in init_sql
    assert "model VARCHAR(255)" in init_sql
    assert "status VARCHAR(32)" in init_sql
    assert "tool_name VARCHAR(255)" in init_sql
    assert "tool_calls JSONB DEFAULT '[]'::JSONB" in init_sql
    assert "latency_ms DOUBLE PRECISION" in init_sql
    assert "redacted_arguments JSONB DEFAULT '{}'::JSONB" in init_sql
    assert "CREATE INDEX IF NOT EXISTS idx_audit_events_workspace_id ON audit_events(workspace_id);" in init_sql
    assert "CREATE INDEX IF NOT EXISTS idx_audit_events_user_id ON audit_events(user_id);" in init_sql
    assert "CREATE INDEX IF NOT EXISTS idx_audit_events_role ON audit_events(role);" in init_sql
    assert "CREATE INDEX IF NOT EXISTS idx_audit_events_model ON audit_events(model);" in init_sql
    assert "CREATE INDEX IF NOT EXISTS idx_audit_events_status ON audit_events(status);" in init_sql
    assert "CREATE INDEX IF NOT EXISTS idx_audit_events_tool_name ON audit_events(tool_name);" in init_sql
