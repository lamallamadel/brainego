"""Static wiring tests for safety gateway checks on chat endpoints."""

from pathlib import Path


API_SERVER_SOURCE = Path("api_server.py").read_text(encoding="utf-8")


def test_safety_gateway_configuration_and_verdict_helpers_exist():
    assert "SAFETY_GATEWAY_ENABLED" in API_SERVER_SOURCE
    assert "DEFAULT_SAFETY_WARN_TERMS" in API_SERVER_SOURCE
    assert "DEFAULT_SAFETY_BLOCK_TERMS" in API_SERVER_SOURCE
    assert "SAFETY_DECISION_VERSION = \"v2\"" in API_SERVER_SOURCE
    assert "def evaluate_safety_text(" in API_SERVER_SOURCE
    assert "def enforce_safety_gateway(" in API_SERVER_SOURCE
    assert "Safety gateway verdict endpoint=%s workspace=%s verdict=%s" in API_SERVER_SOURCE


def test_chat_and_rag_endpoints_invoke_safety_gateway_before_core_pipeline():
    assert 'endpoint="/v1/chat/completions"' in API_SERVER_SOURCE
    assert 'endpoint="/v1/chat"' in API_SERVER_SOURCE
    assert 'endpoint="/v1/rag/query"' in API_SERVER_SOURCE
    assert "if SAFETY_GATEWAY_ENABLED:" in API_SERVER_SOURCE
    assert "enforce_safety_gateway(safety_verdict)" in API_SERVER_SOURCE


def test_safety_prometheus_metrics_include_endpoint_and_workspace_labels():
    assert "api_safety_verdicts_total" in API_SERVER_SOURCE
    assert "api_safety_blocked_categories_total" in API_SERVER_SOURCE
    assert '["workspace_id", "endpoint", "verdict"]' in API_SERVER_SOURCE
    assert '["workspace_id", "endpoint", "category"]' in API_SERVER_SOURCE
    assert "usage_metering.record_safety_verdict(" in API_SERVER_SOURCE
def test_structured_verdict_includes_reason_codes_and_schema_version():
    assert "class SafetyVerdictResponse(BaseModel):" in API_SERVER_SOURCE
    assert "reason_code: str = Field(..., description=\"Primary machine-readable safety reason code\")" in API_SERVER_SOURCE
    assert "reason_codes: List[str] = Field(" in API_SERVER_SOURCE
    assert "decision_version: str = Field(" in API_SERVER_SOURCE
    assert "reason_code = SAFETY_REASON_SAFE" in API_SERVER_SOURCE
    assert "SAFETY_REASON_PAYLOAD_TOO_LARGE" in API_SERVER_SOURCE
    assert "SAFETY_REASON_BLOCKED_TERMS" in API_SERVER_SOURCE
    assert "SAFETY_REASON_WARNING_TERMS" in API_SERVER_SOURCE


def test_chat_and_rag_responses_expose_structured_safety_metadata():
    assert "routing_metadata[\"safety\"] = safety_verdict.model_dump()" in API_SERVER_SOURCE
    assert "response_data[\"x-safety-metadata\"] = safety_verdict.model_dump()" in API_SERVER_SOURCE
    assert "retrieval_stats[\"safety\"] = safety_verdict.model_dump()" in API_SERVER_SOURCE
    assert "stream_headers[\"X-Safety-Verdict\"] = safety_verdict.verdict" in API_SERVER_SOURCE
    assert "stream_headers[\"X-Safety-Reason-Codes\"] = \",\".join(safety_verdict.reason_codes)" in API_SERVER_SOURCE


def test_metrics_store_tracks_reason_code_distribution():
    assert "self.safety_reason_code_counts: Dict[str, int] = {}" in API_SERVER_SOURCE
    assert "def record_safety_verdict(self, verdict: str, reason_codes: Optional[List[str]] = None):" in API_SERVER_SOURCE
    assert "self.safety_reason_code_counts.get(normalized_reason, 0) + 1" in API_SERVER_SOURCE
    assert "\"reason_code_counts\": dict(sorted(self.safety_reason_code_counts.items()))" in API_SERVER_SOURCE
