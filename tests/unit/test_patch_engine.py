"""Static checks for patch engine promotion module."""

from pathlib import Path


SOURCE = Path("patch_engine.py").read_text(encoding="utf-8")


def test_patch_engine_has_promotion_function_and_quality_filter() -> None:
    assert "def promote_learning_events(" in SOURCE
    assert "secret_check" in SOURCE
    assert "overlay_rules_promoted" in SOURCE
    assert "recipes_promoted" in SOURCE
