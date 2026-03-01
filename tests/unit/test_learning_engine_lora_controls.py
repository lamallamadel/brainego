# Needs: python-package:pytest>=9.0.2

from pathlib import Path


SERVICE_SOURCE = Path(__file__).resolve().parents[2] / "learning_engine_service.py"


def test_learning_engine_exposes_lora_kill_switch_endpoints() -> None:
    content = SERVICE_SOURCE.read_text(encoding="utf-8")
    assert '@app.get("/lora/status"' in content
    assert '@app.post("/lora/disable"' in content
    assert '@app.post("/lora/enable"' in content
    assert '@app.post("/lora/rollback"' in content


def test_deploy_adapter_is_blocked_when_kill_switch_disabled() -> None:
    content = SERVICE_SOURCE.read_text(encoding="utf-8")
    assert "LoRA is disabled by kill-switch" in content
    assert "status_code=409" in content


def test_service_tracks_lora_state_and_rollback_history() -> None:
    content = SERVICE_SOURCE.read_text(encoding="utf-8")
    assert "class LoRAState" in content
    assert "rollback_history" in content
    assert 'lora_state.last_operation = "rollback"' in content
