"""Contract tests for eval-first drift trigger and incident opening."""

from pathlib import Path


def test_eval_score_drop_is_primary_drift_trigger() -> None:
    source = Path("drift_monitor.py").read_text(encoding="utf-8")

    assert "eval_drop_detected = eval_score_drop >= self.config.eval_score_drop_min" in source
    assert "drift_detected = eval_drop_detected" in source
    assert '"eval_score_drop": eval_score_drop' in source
    assert '"retraining_recommended": retraining_recommended' in source


def test_incident_opening_and_api_endpoint_exist() -> None:
    source = Path("drift_monitor.py").read_text(encoding="utf-8")

    assert "def open_drift_incident(" in source
    assert "INSERT INTO drift_incidents" in source
    assert '@app.get("/drift/incidents")' in source


def test_eval_and_incident_config_contract_present() -> None:
    config_yaml = Path("configs/drift-monitor.yaml").read_text(encoding="utf-8")

    assert "drift_policy:" in config_yaml
    assert "eval:" in config_yaml
    assert "metric_name:" in config_yaml
    assert "drop_min:" in config_yaml
    assert "incidents:" in config_yaml
    assert "open_on_eval_drift:" in config_yaml


def test_drift_incidents_schema_contract_present() -> None:
    sql = Path("init-scripts/postgres/init.sql").read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS drift_incidents" in sql
    assert "recommendation TEXT NOT NULL" in sql
    assert "GRANT ALL PRIVILEGES ON TABLE drift_incidents TO ai_user;" in sql
