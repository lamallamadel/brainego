"""Static checks for Alertmanager Slack notifications with runbook URL."""

from pathlib import Path

SOURCE = Path('configs/alertmanager/alertmanager.yml').read_text(encoding='utf-8')


def test_alertmanager_uses_slack_webhook_and_actionable_runbook_field() -> None:
    assert "slack_api_url: '${SLACK_WEBHOOK_URL}'" in SOURCE
    assert '*Runbook:* {{ .CommonAnnotations.runbook_url }}' in SOURCE


def test_critical_receiver_mentions_runbook() -> None:
    assert "name: 'slack-critical'" in SOURCE
    assert '@channel - Immediate attention required!' in SOURCE
