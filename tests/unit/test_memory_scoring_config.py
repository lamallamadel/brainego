"""Unit tests for memory scoring profile config resolution."""

from memory_scoring_config import load_memory_scoring_config


def test_loads_balanced_profile_by_default(monkeypatch):
    monkeypatch.delenv("MEMORY_SCORING_PROFILE", raising=False)
    monkeypatch.delenv("MEMORY_COSINE_WEIGHT", raising=False)
    monkeypatch.delenv("MEMORY_TEMPORAL_WEIGHT", raising=False)
    monkeypatch.delenv("MEMORY_TEMPORAL_DECAY_FACTOR", raising=False)

    cfg = load_memory_scoring_config()

    assert cfg["cosine_weight"] == 0.70
    assert cfg["temporal_weight"] == 0.30
    assert cfg["temporal_decay_factor"] == 0.10


def test_profile_selection_and_env_overrides(monkeypatch):
    monkeypatch.setenv("MEMORY_SCORING_PROFILE", "history_heavy")
    monkeypatch.setenv("MEMORY_COSINE_WEIGHT", "0.80")
    monkeypatch.setenv("MEMORY_TEMPORAL_WEIGHT", "0.20")
    monkeypatch.setenv("MEMORY_TEMPORAL_DECAY_FACTOR", "0.05")

    cfg = load_memory_scoring_config()

    assert cfg["cosine_weight"] == 0.80
    assert cfg["temporal_weight"] == 0.20
    assert cfg["temporal_decay_factor"] == 0.05
