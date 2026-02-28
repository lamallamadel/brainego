# Needs: python-package:pytest>=9.0.2

from pathlib import Path


SOURCE = Path(__file__).resolve().parents[2] / "data_collectors" / "mcp_context_ingestion.py"


def test_notion_ingestor_uses_mcp_gateway_endpoint() -> None:
    content = SOURCE.read_text(encoding="utf-8")
    assert "class MCPNotionKnowledgeIngestor" in content
    assert '"server_id": "mcp-notion"' in content
    assert '"tool_name": "notion_search"' in content


def test_notion_ingestor_emits_knowledge_metadata() -> None:
    content = SOURCE.read_text(encoding="utf-8")
    assert '"source": "mcp-notion"' in content
    assert 'collect_knowledge_base' in content
