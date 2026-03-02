from pathlib import Path


TRAINER_SOURCE = Path("learning_engine/trainer.py").read_text(encoding="utf-8")


def test_trainer_declares_golden_validation_controls() -> None:
    assert "golden_suite_path: Optional[str] = None" in TRAINER_SOURCE
    assert "golden_baseline_output_path: Optional[str] = None" in TRAINER_SOURCE
    assert "golden_candidate_output_path: Optional[str] = None" in TRAINER_SOURCE
    assert "golden_validation_required: Optional[bool] = None" in TRAINER_SOURCE
    assert "golden_validation_enabled: Optional[bool] = None" in TRAINER_SOURCE
    assert "golden_thresholds: Optional[Dict[str, Any]] = None" in TRAINER_SOURCE


def test_trainer_records_validation_metrics_and_provenance() -> None:
    assert "GoldenSetValidator" in TRAINER_SOURCE
    assert '"validation_metrics": merged_validation_metrics' in TRAINER_SOURCE
    assert '"provenance": provenance' in TRAINER_SOURCE
    assert "def validate_golden_set(" in TRAINER_SOURCE
    assert "golden_validation_runs_total.labels(" in TRAINER_SOURCE
