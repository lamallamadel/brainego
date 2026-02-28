# Needs: python-package:pytest>=9.0.2

from pathlib import Path


SOURCE = Path(__file__).resolve().parents[2] / "agent_router.py"


def test_intent_classifier_has_code_fence_heuristic() -> None:
    content = SOURCE.read_text(encoding="utf-8")
    assert 'if "```" in text:' in content
    assert "code_matches += 2" in content


def test_intent_classifier_has_reasoning_phrase_heuristic() -> None:
    content = SOURCE.read_text(encoding="utf-8")
    assert '"step by step"' in content
    assert "reasoning_matches += 1" in content
