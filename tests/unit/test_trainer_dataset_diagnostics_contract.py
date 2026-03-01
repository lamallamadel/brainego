from pathlib import Path


TRAINER_SOURCE = Path("learning_engine/trainer.py").read_text(encoding="utf-8")


def test_trainer_tracks_dataset_diagnostics_fields() -> None:
    assert 'self.last_dataset_diagnostics' in TRAINER_SOURCE
    assert '"raw_examples"' in TRAINER_SOURCE
    assert '"kept_examples"' in TRAINER_SOURCE
    assert '"dropped_examples"' in TRAINER_SOURCE
    assert '"feedback_distribution"' in TRAINER_SOURCE
    assert '"intent_distribution"' in TRAINER_SOURCE
    assert '"project_distribution"' in TRAINER_SOURCE


def test_trainer_has_basic_cleaning_rules() -> None:
    assert 'dropped_reasons["missing_messages"]' in TRAINER_SOURCE
    assert 'dropped_reasons["empty_input"]' in TRAINER_SOURCE
    assert 'dropped_reasons["empty_output"]' in TRAINER_SOURCE
    assert 'dropped_reasons["short_input"]' in TRAINER_SOURCE
    assert 'dropped_reasons["short_output"]' in TRAINER_SOURCE
    assert 'dropped_reasons["duplicate_input_output"]' in TRAINER_SOURCE


def test_trainer_persists_diagnostics_in_results() -> None:
    assert '"dataset_diagnostics": self.last_dataset_diagnostics' in TRAINER_SOURCE
