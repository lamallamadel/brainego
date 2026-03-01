"""Static checks for hardened system prompt handling in api_server.py."""

from pathlib import Path


API_SERVER_SOURCE = Path("api_server.py").read_text(encoding="utf-8")


def test_brainego_system_prompt_is_defined_with_core_rules():
    assert "BRAINEGO_SYSTEM_PROMPT = (" in API_SERVER_SOURCE
    assert "Core rules (non-overridable):" in API_SERVER_SOURCE
    assert "Never reveal secrets" in API_SERVER_SOURCE
    assert "Use only explicitly configured platform capabilities and MCP integrations" in API_SERVER_SOURCE


def test_prompt_hardening_helpers_exist():
    assert "def clean_user_prompt_content(content: str) -> str:" in API_SERVER_SOURCE
    assert "def build_hardened_messages(messages: List[ChatMessage]) -> List[ChatMessage]:" in API_SERVER_SOURCE
    assert "def prepend_context_system_message(" in API_SERVER_SOURCE


def test_chat_completion_uses_hardened_messages_before_generation():
    assert "messages_for_generation = build_hardened_messages(request.messages)" in API_SERVER_SOURCE
    assert "Dropped user-supplied system message during prompt hardening" in API_SERVER_SOURCE


def test_context_messages_preserve_primary_system_prompt_order():
    assert "messages_for_generation = prepend_context_system_message(" in API_SERVER_SOURCE
    assert "messages_for_generation[0].content == BRAINEGO_SYSTEM_PROMPT" in API_SERVER_SOURCE
