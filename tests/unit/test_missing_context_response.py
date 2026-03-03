"""Static tests for missing-context response module wiring."""

from pathlib import Path


SOURCE = Path("missing_context_response.py").read_text(encoding="utf-8")
API_SERVER_SOURCE = Path("api_server.py").read_text(encoding="utf-8")


def test_missing_context_module_exposes_policy_and_builder() -> None:
    assert "def should_return_missing_context" in SOURCE
    assert "def build_missing_context_payload" in SOURCE
    assert '"type": "missing_context"' in SOURCE


def test_missing_context_integration_short_circuits_before_llm() -> None:
    assert "if should_return_missing_context(grounding_intent, ess_score, ESS_THRESHOLD_HIGH):" in API_SERVER_SOURCE
    assert '"response_mode": "missing_context"' in API_SERVER_SOURCE
    assert "metrics.record_missing_context_response()" in API_SERVER_SOURCE
