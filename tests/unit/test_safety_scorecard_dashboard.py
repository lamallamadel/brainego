# Needs: python-package:pytest>=9.0.2

"""Static dashboard wiring checks for AFR-128 safety scorecard."""

import json
from pathlib import Path


SCORECARD_DASHBOARD_PATH = Path("configs/grafana/dashboards/safety-scorecard.json")
SCORECARD_DASHBOARD_SOURCE = SCORECARD_DASHBOARD_PATH.read_text(encoding="utf-8")


def test_safety_scorecard_dashboard_exists_with_expected_identity() -> None:
    dashboard = json.loads(SCORECARD_DASHBOARD_SOURCE)
    assert dashboard["uid"] == "safety-scorecard"
    assert dashboard["title"] == "Safety Scorecard"
    assert "safety" in dashboard["tags"]
    assert "scorecard" in dashboard["tags"]


def test_safety_scorecard_queries_cover_required_metrics() -> None:
    assert "Tool Abuse Blocked % (5m)" in SCORECARD_DASHBOARD_SOURCE
    assert "False Positive Rate (Manual Tag, 5m)" in SCORECARD_DASHBOARD_SOURCE
    assert "Top Policy Triggers ($__range)" in SCORECARD_DASHBOARD_SOURCE
    assert 'guardrail_requests_total{policy_category=\\"tool_abuse\\",decision=\\"blocked\\"' in SCORECARD_DASHBOARD_SOURCE
    assert 'guardrail_manual_review_total{tag=\\"false_positive\\"' in SCORECARD_DASHBOARD_SOURCE
    assert "guardrail_policy_triggers_total or guardrail_policy_trigger_total" in SCORECARD_DASHBOARD_SOURCE
