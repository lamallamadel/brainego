"""Static tests for dangerous command output guardrails in api_server.py."""

from pathlib import Path


API_SERVER_SOURCE = Path("api_server.py").read_text(encoding="utf-8")


def test_output_guardrail_patterns_cover_shell_and_sql_destructive_commands():
    assert "OUTPUT_GUARDRAIL_PATTERNS" in API_SERVER_SOURCE
    assert '"shell.rm_rf"' in API_SERVER_SOURCE
    assert '"shell.disk_wipe"' in API_SERVER_SOURCE
    assert '"shell.system_shutdown"' in API_SERVER_SOURCE
    assert '"sql.drop_database"' in API_SERVER_SOURCE
    assert '"sql.drop_table"' in API_SERVER_SOURCE


def test_output_guardrails_rewrite_response_with_warning_and_metadata():
    assert "def apply_output_guardrails(generated_text: str)" in API_SERVER_SOURCE
    assert "I can’t provide potentially destructive shell or database commands" in API_SERVER_SOURCE
    assert '"reason": "dangerous_code_or_commands"' in API_SERVER_SOURCE
    assert '"matched_patterns": unique_patterns' in API_SERVER_SOURCE


def test_output_guardrails_are_applied_after_generation_in_chat_and_rag_endpoints():
    assert API_SERVER_SOURCE.count("apply_output_guardrails(generated_text)") >= 3
    assert 'routing_metadata["output_guardrail"] = guardrail_metadata' in API_SERVER_SOURCE
