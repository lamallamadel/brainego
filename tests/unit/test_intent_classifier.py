from pathlib import Path
import sys

"""Unit tests for lightweight intent classifier module."""

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from intent_classifier import Intent, IntentClassifier


CONFIG = {
    "code_keywords": ["python", "function", "debug"],
    "reasoning_keywords": ["why", "analyze", "logic"],
    "thresholds": {"low": 0.2, "medium": 0.4, "high": 0.7},
}


def test_classify_code_intent() -> None:
    classifier = IntentClassifier(CONFIG)
    intent, confidence = classifier.classify("python debug function code")

    assert intent == Intent.CODE
    assert confidence >= CONFIG["thresholds"]["medium"]


def test_classify_reasoning_intent() -> None:
    classifier = IntentClassifier(CONFIG)
    intent, confidence = classifier.classify("analyze why this logic reasoning")

    assert intent == Intent.REASONING
    assert confidence >= CONFIG["thresholds"]["medium"]


def test_classify_general_when_no_matches() -> None:
    classifier = IntentClassifier(CONFIG)
    intent, confidence = classifier.classify("Hello there")

    assert intent == Intent.GENERAL
    assert 0.0 <= confidence <= 1.0
