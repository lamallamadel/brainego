"""Heuristic detectors for jailbreak and prompt-injection attempts."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Sequence


_PATTERN_GROUPS = {
    "ignore_previous_instructions": [
        r"\bignore\s+(all\s+)?(previous|prior|above)\s+instructions\b",
        r"\b(disregard|forget)\s+(all\s+)?(previous|prior|above)\s+instructions\b",
        r"\boverride\s+(the\s+)?(system|developer)\s+prompt\b",
    ],
    "prompt_self_reference": [
        r"\breveal\s+(the\s+)?(system|developer)\s+prompt\b",
        r"\bshow\s+me\s+your\s+(system|hidden)\s+instructions\b",
        r"\bwhat\s+are\s+your\s+(hidden|internal)\s+instructions\b",
    ],
    "role_play_abuse": [
        r"\byou\s+are\s+now\s+(dan|developer\s+mode|jailbroken)\b",
        r"\bpretend\s+to\s+be\s+(an?\s+)?(unrestricted|unfiltered)\s+assistant\b",
        r"\bact\s+as\s+(an?\s+)?(evil|malicious|unrestricted)\b",
    ],
    "camouflage": [
        r"\b(base64|rot13|hex)\b.{0,40}\b(decode|encoded?)\b",
        r"\b(decode|encoded?)\b.{0,40}\b(base64|rot13|hex)\b",
        r"\buse\s+unicode\s+to\s+bypass\b",
        r"\binvisible\s+(characters|unicode)\b",
        r"\bobfuscate\s+the\s+prompt\b",
    ],
}


def detect_prompt_injection_patterns(messages: Sequence[Any]) -> Dict[str, Any]:
    """Return heuristic security metadata for a chat request."""
    user_contents: List[str] = []
    for msg in messages:
        role = getattr(msg, "role", None)
        content = getattr(msg, "content", "")
        if isinstance(msg, dict):
            role = msg.get("role")
            content = msg.get("content", "")
        if role == "user" and isinstance(content, str):
            user_contents.append(content)

    target_text = "\n".join(user_contents).lower()

    matches: List[Dict[str, str]] = []
    for category, patterns in _PATTERN_GROUPS.items():
        for pattern in patterns:
            if re.search(pattern, target_text, flags=re.IGNORECASE | re.DOTALL):
                matches.append({"category": category, "pattern": pattern})
                break

    categories = sorted({m["category"] for m in matches})
    score = len(categories)

    return {
        "suspicious": score > 0,
        "risk_score": score,
        "matched_categories": categories,
        "match_count": len(matches),
    }
