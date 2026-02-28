# Needs: python-package:pytest>=9.0.2

from pathlib import Path


SOURCE = Path(__file__).resolve().parents[2] / "data_collectors" / "mcp_context_ingestion.py"


def test_slack_streaming_source_uses_mcp_tool() -> None:
    content = SOURCE.read_text(encoding="utf-8")
    assert "class MCPSlackStreamingSource" in content
    assert '"server_id": "mcp-slack"' in content
    assert '"tool_name": "slack_get_channel_history"' in content


def test_slack_streaming_source_adds_channel_metadata() -> None:
    content = SOURCE.read_text(encoding="utf-8")
    assert '"source": "mcp-slack"' in content
    assert '"channel_id": channel_id' in content
