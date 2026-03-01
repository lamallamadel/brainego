# Needs: python-package:pytest>=9.0.2

from pathlib import Path


CONFIG_PATH = Path(__file__).resolve().parents[2] / "configs" / "mcp-acl.yaml"


def test_developer_acl_enables_issue_tracker_write_and_github_read_only() -> None:
    content = CONFIG_PATH.read_text(encoding="utf-8")

    assert "mcp-linear:" in content
    assert "linear_create_issue" in content
    assert "linear_update_issue" in content

    assert "mcp-jira:" in content
    assert "jira_create_issue" in content
    assert "jira_update_issue" in content

    assert "github_create_issue" not in content
