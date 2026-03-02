# Needs: python-package:pytest>=9.0.2
"""Static wiring checks for AFR-120 redaction-first audit/telemetry persistence."""

from pathlib import Path


API_SERVER_SOURCE = Path("api_server.py").read_text(encoding="utf-8")


def test_audit_redaction_helper_uses_sensitive_redactor() -> None:
    assert "def _redact_value_for_audit(value: Any) -> Tuple[Any, int]:" in API_SERVER_SOURCE
    assert "return redact_sensitive(value)" in API_SERVER_SOURCE


def test_audit_middleware_redacts_query_params_before_persistence() -> None:
    assert "safe_query_params, query_redactions = _redact_value_for_audit(dict(request.query_params))" in API_SERVER_SOURCE
    assert '"query_redactions": query_redactions' in API_SERVER_SOURCE


def test_metering_events_are_redacted_before_db_write() -> None:
    assert 'safe_request_id, _ = _redact_value_for_audit(request_id or "")' in API_SERVER_SOURCE
    assert "safe_metadata, _ = _redact_value_for_audit(metadata or {})" in API_SERVER_SOURCE
    assert "request_id=safe_request_id or None" in API_SERVER_SOURCE
    assert "metadata=safe_metadata" in API_SERVER_SOURCE


def test_telemetry_labels_and_user_metering_apply_sensitive_redaction() -> None:
    assert "redacted_value, _ = redact_sensitive_in_text(value.strip())" in API_SERVER_SOURCE
    assert "redacted_value, _ = redact_sensitive_in_text(normalized)" in API_SERVER_SOURCE
