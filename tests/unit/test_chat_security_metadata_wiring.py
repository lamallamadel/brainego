"""Static checks for prompt-injection security metadata wiring in API endpoint."""

from pathlib import Path


API_SERVER_SOURCE = Path("api_server.py").read_text(encoding="utf-8")


def test_chat_completions_runs_prompt_injection_heuristics() -> None:
    assert "from security_heuristics import detect_prompt_injection_patterns" in API_SERVER_SOURCE
    assert "security_metadata = detect_prompt_injection_patterns(request.messages)" in API_SERVER_SOURCE
    assert "Suspicious prompt pattern detected" in API_SERVER_SOURCE


def test_chat_completions_exposes_security_metadata_in_response_and_routing() -> None:
    assert 'routing_metadata["security"] = security_metadata' in API_SERVER_SOURCE
    assert '"x-security-metadata": security_metadata' in API_SERVER_SOURCE
