# Needs: python-package:pytest>=9.0.2

from pathlib import Path


CONFIG_PATH = Path(__file__).resolve().parents[2] / "configs" / "tool-policy.yaml"


def test_default_workspace_allows_linear_and_jira_servers() -> None:
    content = CONFIG_PATH.read_text(encoding="utf-8")
    assert "- mcp-linear" in content
    assert "- mcp-jira" in content


def test_developer_write_scope_is_limited_to_issue_tracker_tools() -> None:
    content = CONFIG_PATH.read_text(encoding="utf-8")
    assert '"linear_create_issue"' in content
    assert '"linear_update_issue"' in content
    assert '"jira_create_issue"' in content
    assert '"jira_update_issue"' in content


def test_developer_write_requires_issue_tracker_policy_scope() -> None:
    content = CONFIG_PATH.read_text(encoding="utf-8")
    assert '"mcp.tool.write"' in content
    assert '"mcp.issue_tracker.write"' in content
