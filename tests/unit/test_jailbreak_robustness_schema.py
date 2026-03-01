"""Regression checks for jailbreak robustness score tracking schema."""

from pathlib import Path


def test_jailbreak_source_tables_exist() -> None:
    sql = Path("init-scripts/postgres/init.sql").read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS adversarial_test_results" in sql
    assert "evaluation_id VARCHAR(255) NOT NULL" in sql
    assert "blocked BOOLEAN NOT NULL" in sql
    assert "safely_handled BOOLEAN NOT NULL" in sql

    assert "CREATE TABLE IF NOT EXISTS safety_judge_results" in sql
    assert "is_safe BOOLEAN NOT NULL" in sql


def test_daily_robustness_view_is_defined_per_model_version() -> None:
    sql = Path("init-scripts/postgres/init.sql").read_text(encoding="utf-8")

    assert "CREATE MATERIALIZED VIEW IF NOT EXISTS jailbreak_robustness_daily AS" in sql
    assert "COALESCE(a.adapter_version, 'base') AS adapter_version" in sql
    assert "(a.blocked OR a.safely_handled) AND COALESCE(s.is_safe, false)" in sql
    assert "AS robustness_score" in sql


def test_refresh_function_persists_latest_robustness_metric() -> None:
    sql = Path("init-scripts/postgres/init.sql").read_text(encoding="utf-8")

    assert "CREATE OR REPLACE FUNCTION refresh_jailbreak_robustness()" in sql
    assert "'jailbreak_robustness'" in sql
    assert "jsonb_build_object('base_model', base_model, 'day', day)" in sql
    assert "GRANT EXECUTE ON FUNCTION refresh_jailbreak_robustness TO ai_user;" in sql
