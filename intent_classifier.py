"""Intent classification primitives used for model routing."""

from __future__ import annotations

import re
from enum import Enum
from typing import Any, Dict, Tuple


class Intent(str, Enum):
    """Intent classification types used by the router."""

    CODE = "code"
    REASONING = "reasoning"
    GENERAL = "general"


class IntentClassifier:
    """Classify user intent based on lightweight keyword scoring."""

    def __init__(self, config: Dict[str, Any]):
        self.code_keywords = set(config["code_keywords"])
        self.reasoning_keywords = set(config["reasoning_keywords"])
        self.thresholds = config["thresholds"]

        self.code_pattern = re.compile(
            r"\b(" + "|".join(map(re.escape, self.code_keywords)) + r")\b",
            re.IGNORECASE,
        )
        self.reasoning_pattern = re.compile(
            r"\b(" + "|".join(map(re.escape, self.reasoning_keywords)) + r")\b",
            re.IGNORECASE,
        )

    def classify(self, text: str) -> Tuple[Intent, float]:
        """Return an ``(intent, confidence)`` tuple for incoming text."""
        text_lower = text.lower()

        code_matches = len(self.code_pattern.findall(text))
        reasoning_matches = len(self.reasoning_pattern.findall(text))

        total_words = len(text_lower.split())
        if total_words == 0:
            return Intent.GENERAL, 1.0

        code_score = min(code_matches / max(total_words * 0.1, 1), 1.0)
        reasoning_score = min(reasoning_matches / max(total_words * 0.1, 1), 1.0)

        if code_score >= self.thresholds["medium"] and code_score >= reasoning_score:
            return Intent.CODE, code_score
        if reasoning_score >= self.thresholds["medium"]:
            return Intent.REASONING, reasoning_score
        return Intent.GENERAL, 1.0 - max(code_score, reasoning_score)

