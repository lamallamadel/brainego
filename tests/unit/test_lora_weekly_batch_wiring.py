"""Static checks for S5-3 weekly LoRA batch orchestration script."""

from pathlib import Path

SOURCE = Path("scripts/learning/lora_weekly_batch.sh").read_text(encoding="utf-8")


def test_script_contains_canary_and_rollback_hooks() -> None:
    assert "CANARY_TIMEOUT_SEC" in SOURCE
    assert "ROLLBACK_CMD" in SOURCE
    assert "Canary failed -> rollback" in SOURCE


def test_script_triggers_train_jsonl_endpoint() -> None:
    assert '/train/jsonl' in SOURCE
    assert '"mode":"lora_weekly"' in SOURCE
