# Needs: python-package:pytest>=9.0.2

from pathlib import Path


SOURCE = Path(__file__).resolve().parents[2] / "mcp_client.py"


def test_mcp_client_call_tool_redacts_arguments_and_errors_in_logs() -> None:
    content = SOURCE.read_text(encoding="utf-8")
    assert "from safety_sanitizer import redact_secrets" in content
    assert 'safe_arguments_payload, argument_redactions = redact_secrets({"arguments": arguments or {}})' in content
    assert "safe_error, error_redactions = redact_secrets(str(e))" in content
