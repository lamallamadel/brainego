# Needs: python-package:pytest>=9.0.2

"""Static wiring checks for AFR-92 usage metering."""

import json
from pathlib import Path


API_SERVER_SOURCE = Path("api_server.py").read_text(encoding="utf-8")
USAGE_DASHBOARD_PATH = Path("configs/grafana/dashboards/usage-metering.json")
USAGE_DASHBOARD_SOURCE = USAGE_DASHBOARD_PATH.read_text(encoding="utf-8")


def test_prometheus_usage_metering_metrics_are_declared() -> None:
    assert "api_usage_requests_total" in API_SERVER_SOURCE
    assert "api_usage_tokens_total" in API_SERVER_SOURCE
    assert "api_usage_tool_calls_total" in API_SERVER_SOURCE
    assert "api_usage_errors_total" in API_SERVER_SOURCE
    assert "api_usage_latency_seconds" in API_SERVER_SOURCE


def test_metrics_endpoint_exposes_prometheus_and_json_compat() -> None:
    assert "@app.get(\"/metrics\")" in API_SERVER_SOURCE
    assert "return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)" in API_SERVER_SOURCE
    assert "@app.get(\"/metrics/json\")" in API_SERVER_SOURCE
    assert "\"per_model_metrics\": metrics.get_model_stats()" in API_SERVER_SOURCE


def test_usage_metering_is_recorded_for_requests_tokens_and_tool_calls() -> None:
    assert "usage_metering.record_request(" in API_SERVER_SOURCE
    assert "usage_metering.record_tokens(" in API_SERVER_SOURCE
    assert "usage_metering.record_tool_call(" in API_SERVER_SOURCE
    assert 'meter_key="tokens.input"' in API_SERVER_SOURCE
    assert 'meter_key="tokens.output"' in API_SERVER_SOURCE
    assert 'meter_key="http.error"' in API_SERVER_SOURCE
    assert "user_id=user_id" in API_SERVER_SOURCE


def test_usage_metering_dashboard_exists_and_references_new_metrics() -> None:
    dashboard = json.loads(USAGE_DASHBOARD_SOURCE)
    assert dashboard["uid"] == "usage-metering"
    assert dashboard["title"] == "Usage Metering (Workspace/User)"
    assert "api_usage_requests_total" in USAGE_DASHBOARD_SOURCE
    assert "api_usage_tokens_total" in USAGE_DASHBOARD_SOURCE
    assert "api_usage_tool_calls_total" in USAGE_DASHBOARD_SOURCE
    assert "api_usage_errors_total" in USAGE_DASHBOARD_SOURCE
    assert "api_usage_latency_seconds_bucket" in USAGE_DASHBOARD_SOURCE
    assert "workspace_id" in USAGE_DASHBOARD_SOURCE
    assert "user_id" in USAGE_DASHBOARD_SOURCE


def test_metering_summary_endpoint_supports_user_scope_filter() -> None:
    assert 'user_id: Optional[str] = Query(None, description="Optional user scope for metering summary")' in API_SERVER_SOURCE
    assert "user_filter = user_id or raw_request.query_params.get(\"user\")" in API_SERVER_SOURCE
    assert "user_id=user_filter" in API_SERVER_SOURCE
