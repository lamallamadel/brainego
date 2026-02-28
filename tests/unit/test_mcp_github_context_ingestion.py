# Needs: python-package:pytest>=9.0.2

from pathlib import Path


SOURCE = Path(__file__).resolve().parents[2] / "data_collectors" / "mcp_context_ingestion.py"


def test_github_ingestor_uses_mcp_gateway_endpoint() -> None:
    content = SOURCE.read_text(encoding="utf-8")
    assert "class MCPGitHubContextIngestor" in content
    assert '"server_id": "mcp-github"' in content
    assert '"tool_name": "github_search_repositories"' in content
    assert 'f"{self.gateway_url}/mcp"' in content


def test_github_ingestor_emits_project_context_metadata() -> None:
    content = SOURCE.read_text(encoding="utf-8")
    assert '"source": "mcp-github"' in content
    assert '"query": query' in content
