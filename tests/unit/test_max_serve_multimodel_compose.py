# Needs: python-package:pytest>=9.0.2

from pathlib import Path


SOURCE = Path(__file__).resolve().parents[2] / "docker-compose.max-serve.yaml"


def test_compose_declares_qwen_and_deepseek_services() -> None:
    content = SOURCE.read_text(encoding="utf-8")
    assert "max-serve-qwen:" in content
    assert "max-serve-deepseek:" in content


def test_compose_has_model_paths_for_qwen_and_deepseek() -> None:
    content = SOURCE.read_text(encoding="utf-8")
    assert "MAX_SERVE_QWEN_MODEL_PATH" in content
    assert "MAX_SERVE_DEEPSEEK_MODEL_PATH" in content
