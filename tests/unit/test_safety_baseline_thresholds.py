"""Static checks for AFR-127 safety baseline thresholds."""

from pathlib import Path


ALERTS_SOURCE = Path("configs/prometheus/rules/alerts.yml").read_text(encoding="utf-8")
DASHBOARD_SOURCE = Path("configs/grafana/dashboards/safety-guardrails-overview.json").read_text(encoding="utf-8")


def test_prometheus_alerts_include_zero_tolerance_safety_baselines() -> None:
    assert "- alert: SafetySecretLeakIncident" in ALERTS_SOURCE
    assert "api_safety_blocked_categories_total" in ALERTS_SOURCE
    assert "threshold: 0 incidents in 15m" in ALERTS_SOURCE

    assert "- alert: UnauthorizedToolWriteDenied" in ALERTS_SOURCE
    assert "api_usage_tool_calls_total" in ALERTS_SOURCE
    assert "threshold: 0 denied writes in 15m" in ALERTS_SOURCE


def test_safety_dashboard_tracks_baseline_incidents_and_trend() -> None:
    assert "Secret Leak Incidents ($__range)" in DASHBOARD_SOURCE
    assert "Unauthorized Tool Write Denials ($__range)" in DASHBOARD_SOURCE
    assert "Safety Baseline Incidents Over Time" in DASHBOARD_SOURCE
