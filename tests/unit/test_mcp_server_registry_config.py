# Needs: python-package:pytest>=9.0.2

from pathlib import Path


CONFIG_PATH = Path(__file__).resolve().parents[2] / "configs" / "mcp-servers.yaml"


def test_github_notion_linear_jira_servers_registered_and_enabled() -> None:
    content = CONFIG_PATH.read_text(encoding="utf-8")

    assert "mcp-github:" in content
    assert "@modelcontextprotocol/server-github" in content

    assert "mcp-notion:" in content
    assert "@modelcontextprotocol/server-notion" in content

    assert "mcp-linear:" in content
    assert "@modelcontextprotocol/server-linear" in content

    assert "mcp-jira:" in content
    assert "@modelcontextprotocol/server-jira" in content



def test_github_notion_linear_jira_credentials_are_wired_in_env() -> None:
    content = CONFIG_PATH.read_text(encoding="utf-8")

    assert 'GITHUB_TOKEN: "${GITHUB_TOKEN}"' in content
    assert 'NOTION_API_KEY: "${NOTION_API_KEY}"' in content
    assert 'LINEAR_API_KEY: "${LINEAR_API_KEY}"' in content
    assert 'JIRA_BASE_URL: "${JIRA_BASE_URL}"' in content
    assert 'JIRA_EMAIL: "${JIRA_EMAIL}"' in content
    assert 'JIRA_API_TOKEN: "${JIRA_API_TOKEN}"' in content


def test_github_server_is_configured_as_read_only_in_v1() -> None:
    content = CONFIG_PATH.read_text(encoding="utf-8")
    assert '"github_create_issue"' not in content
    assert "allowed_operations:" in content
