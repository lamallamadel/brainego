"""Static wiring tests for S2-3 recovery planner integration."""

from pathlib import Path


SOURCE = Path("api_server.py").read_text(encoding="utf-8")


def test_recovery_metrics_and_config_present() -> None:
    assert "RECOVERY_MAX_ATTEMPTS" in SOURCE
    assert "recovery_success_rate" in SOURCE
    assert "record_recovery_attempt" in SOURCE


def test_rag_query_uses_recovery_planner() -> None:
    assert "run_recovery_attempts(" in SOURCE
    assert '"grounded_after_recovery"' in SOURCE
    assert '"recovery_succeeded"' in SOURCE
