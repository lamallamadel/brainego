"""Regression checks for scoped drift metrics support."""

from pathlib import Path


def test_drift_metrics_schema_includes_scope_columns() -> None:
    sql = Path("init-scripts/postgres/init.sql").read_text(encoding="utf-8")

    assert "scope_type VARCHAR(50)" in sql
    assert "scope_value VARCHAR(255)" in sql
    assert "ALTER TABLE drift_metrics ADD COLUMN IF NOT EXISTS scope_type" in sql
    assert "CREATE INDEX IF NOT EXISTS idx_drift_metrics_scope" in sql


def test_drift_monitor_exposes_scoped_results() -> None:
    source = Path("drift_monitor.py").read_text(encoding="utf-8")

    assert "def list_monitoring_scopes" in source
    assert '"scope_results": per_scope_results' in source
    assert '"checked_scopes": len(scopes)' in source
    assert "scope_type: Optional[str] = None, scope_value: Optional[str] = None" in source
