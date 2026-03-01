"""Static wiring tests for safety gateway checks on chat endpoints."""

from pathlib import Path


API_SERVER_SOURCE = Path("api_server.py").read_text(encoding="utf-8")


def test_safety_gateway_configuration_and_verdict_helpers_exist():
    assert "SAFETY_GATEWAY_ENABLED" in API_SERVER_SOURCE
    assert "DEFAULT_SAFETY_WARN_TERMS" in API_SERVER_SOURCE
    assert "DEFAULT_SAFETY_BLOCK_TERMS" in API_SERVER_SOURCE
    assert "def evaluate_safety_text(" in API_SERVER_SOURCE
    assert "def enforce_safety_gateway(" in API_SERVER_SOURCE
    assert "Safety gateway verdict endpoint=%s verdict=%s" in API_SERVER_SOURCE


def test_chat_and_rag_endpoints_invoke_safety_gateway_before_core_pipeline():
    assert 'endpoint="/v1/chat/completions"' in API_SERVER_SOURCE
    assert 'endpoint="/v1/chat"' in API_SERVER_SOURCE
    assert 'endpoint="/v1/rag/query"' in API_SERVER_SOURCE
    assert "if SAFETY_GATEWAY_ENABLED:" in API_SERVER_SOURCE
    assert "enforce_safety_gateway(safety_verdict)" in API_SERVER_SOURCE
