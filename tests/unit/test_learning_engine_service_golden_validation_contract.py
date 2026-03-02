from pathlib import Path


SERVICE_SOURCE = Path("learning_engine_service.py").read_text(encoding="utf-8")


def test_training_request_supports_golden_validation_payload() -> None:
    assert "golden_validation_enabled" in SERVICE_SOURCE
    assert "golden_validation_required" in SERVICE_SOURCE
    assert "golden_suite_path" in SERVICE_SOURCE
    assert "golden_baseline_output_path" in SERVICE_SOURCE
    assert "golden_candidate_output_path" in SERVICE_SOURCE
    assert "golden_thresholds" in SERVICE_SOURCE


def test_service_exposes_golden_validation_endpoint() -> None:
    assert '@app.post("/validation/golden-set")' in SERVICE_SOURCE
    assert "class GoldenValidationRequest(BaseModel):" in SERVICE_SOURCE
    assert "trainer.validate_golden_set" in SERVICE_SOURCE
