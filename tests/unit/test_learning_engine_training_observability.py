"""Unit tests for learning engine observability instrumentation."""

from pathlib import Path


def test_trainer_records_run_metadata_fields():
    """Trainer should track dataset, thresholds, decision, and loss deltas."""
    content = Path("learning_engine/trainer.py").read_text(encoding="utf-8")

    required_snippets = [
        '"dataset_id"',
        '"dataset_size"',
        '"thresholds"',
        '"decision"',
        '"initial_loss"',
        '"final_loss"',
        '"last_run"',
        'learning_engine.training.completed',
        'learning_engine.training.failed',
        'learning_engine.training.skipped',
    ]

    for snippet in required_snippets:
        assert snippet in content, f"Expected snippet not found: {snippet}"


def test_training_runs_counter_supports_skipped_status():
    """Counter usage should include the skipped status for decision visibility."""
    content = Path("learning_engine/trainer.py").read_text(encoding="utf-8")

    assert 'status="skipped"' in content
    assert 'training_runs_total.labels(' in content
