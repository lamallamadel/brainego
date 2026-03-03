"""Static tests for grounding intent classifier module content."""

from pathlib import Path


SOURCE = Path("grounding_intent_classifier.py").read_text(encoding="utf-8")


def test_classifier_exposes_required_intents() -> None:
    assert 'MUST_GROUND = "must_ground"' in SOURCE
    assert 'SHOULD_GROUND = "should_ground"' in SOURCE
    assert 'FREEFORM = "freeform"' in SOURCE


def test_classifier_covers_required_prompt_families() -> None:
    assert "bonjour" in SOURCE
    assert "brainstorm" in SOURCE
    assert "summarize" in SOURCE
    assert "document" in SOURCE


def test_classifier_has_must_should_freeform_decision_flow() -> None:
    assert "return GroundingIntent.MUST_GROUND" in SOURCE
    assert "return GroundingIntent.SHOULD_GROUND" in SOURCE
    assert "return GroundingIntent.FREEFORM" in SOURCE
