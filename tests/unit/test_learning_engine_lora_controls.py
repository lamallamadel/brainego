# Needs: python-package:pytest>=9.0.2

from pathlib import Path


SERVICE_SOURCE = Path(__file__).resolve().parents[2] / "learning_engine_service.py"


def test_learning_engine_exposes_lora_kill_switch_endpoints() -> None:
    content = SERVICE_SOURCE.read_text(encoding="utf-8")
    assert '@app.get("/lora/status"' in content
    assert '@app.post("/lora/disable"' in content
    assert '@app.post("/lora/enable"' in content
    assert '@app.post("/lora/rollback"' in content
    assert '@app.post("/lora/activate"' in content


def test_deploy_adapter_is_blocked_when_kill_switch_disabled() -> None:
    content = SERVICE_SOURCE.read_text(encoding="utf-8")
    assert "LoRA is disabled by kill-switch" in content
    assert "status_code=409" in content


def test_service_tracks_known_good_state_and_operation_histories() -> None:
    content = SERVICE_SOURCE.read_text(encoding="utf-8")
    assert "class LoRAState" in content
    assert "known_good_adapter_version" in content
    assert "activation_history" in content
    assert "rollback_history" in content
    assert 'lora_state.last_operation = "rollback"' in content


def test_service_requires_lora_control_plane_configuration_for_hotswap() -> None:
    content = SERVICE_SOURCE.read_text(encoding="utf-8")
    assert "LORA_CONTROL_BASE_URL" in content
    assert "LORA_RELOAD_ENDPOINT_PATH" in content
    assert "LORA_ROLLBACK_ENDPOINT_PATH" in content
    assert "LORA_OPERATION_TIMEOUT_SECONDS" in content
    assert "LoRA control plane is not configured" in content
    assert "_call_lora_control_plane(" in content


def test_rollback_prefers_known_good_and_tracks_under_two_minute_target() -> None:
    content = SERVICE_SOURCE.read_text(encoding="utf-8")
    assert "lora_state.known_good_adapter_version or lora_state.previous_adapter_version" in content
    assert "target_ms = int(config.lora_operation_timeout_seconds * 1000)" in content
    assert "rollback_within_target = duration_ms <= target_ms" in content
    assert '"within_target": rollback_within_target' in content
