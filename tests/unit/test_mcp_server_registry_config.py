# Needs: python-package:pytest>=9.0.2

from pathlib import Path


CONFIG_PATH = Path(__file__).resolve().parents[2] / "configs" / "mcp-servers.yaml"


def test_github_and_notion_servers_registered_and_enabled() -> None:
    content = CONFIG_PATH.read_text(encoding="utf-8")

    assert "mcp-github:" in content
    assert "@modelcontextprotocol/server-github" in content

    assert "mcp-notion:" in content
    assert "@modelcontextprotocol/server-notion" in content



def test_github_and_notion_credentials_are_wired_in_env() -> None:
    content = CONFIG_PATH.read_text(encoding="utf-8")

    assert 'GITHUB_TOKEN: "${GITHUB_TOKEN}"' in content
    assert 'NOTION_API_KEY: "${NOTION_API_KEY}"' in content
