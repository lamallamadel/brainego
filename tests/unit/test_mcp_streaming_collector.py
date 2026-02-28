import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

"""Unit tests for MCP streaming collector signal extraction."""

from data_collectors.mcp_streaming_collector import MCPStreamingCollector


def test_extract_messages_from_mcp_result_supports_messages_key() -> None:
    collector = MCPStreamingCollector(config_path="configs/mcp-servers.yaml")
    result = {
        "content": [
            {
                "type": "text",
                "text": '{"messages":[{"text":"Decision: we will launch","channel_id":"C123","ts":"1710000000.0"}]}'
            }
        ]
    }

    messages = collector._extract_messages_from_mcp_result(result)

    assert len(messages) == 1
    assert messages[0]["channel_id"] == "C123"


def test_extract_signals_detects_decisions_todos_and_important_keywords() -> None:
    collector = MCPStreamingCollector(config_path="configs/mcp-servers.yaml")
    text = (
        "Decision: we will merge this tomorrow. "
        "Action item: assign owner and set deadline. "
        "This is urgent and critical due to blocker risk."
    )

    signals = collector._extract_signals(text)

    assert "decision" in signals["decisions"]
    assert "we will" in signals["decisions"]
    assert "action item" in signals["todos"]
    assert "deadline" in signals["todos"]
    assert "urgent" in signals["important"]
    assert "critical" in signals["important"]


def test_build_signal_document_text_includes_signal_sections() -> None:
    collector = MCPStreamingCollector(config_path="configs/mcp-servers.yaml")
    text = collector._build_signal_document_text(
        text="Original slack message",
        signals={
            "decisions": ["decision"],
            "todos": ["action item"],
            "important": ["urgent"],
        },
    )

    assert "## Extracted signals" in text
    assert "Decisions: decision" in text
    assert "TODOs: action item" in text
    assert "Important: urgent" in text
    assert "## Original message" in text
