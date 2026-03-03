"""Overlay routing helper applied before LLM generation."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def _parse_priority(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def pick_overlay_match(*, intent: str, query: str, rules: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Return metadata for the highest-priority matching overlay rule."""

    normalized_intent = (intent or "").strip().lower()
    normalized_query = (query or "").strip().lower()

    indexed_rules = list(enumerate(rules))
    indexed_rules.sort(key=lambda item: _parse_priority(item[1].get("priority", 0)), reverse=True)

    for index, rule in indexed_rules:
        if not bool(rule.get("enabled", True)):
            continue
        rule_intent = str(rule.get("intent", "")).strip().lower()
        if rule_intent and rule_intent != normalized_intent:
            continue
        contains = str(rule.get("contains", "")).strip().lower()
        if contains and contains not in normalized_query:
            continue
        response = str(rule.get("response", "")).strip()
        if response:
            return {
                "response": response,
                "rule_id": str(rule.get("rule_id", rule.get("id", f"rule-{index}"))),
                "priority": _parse_priority(rule.get("priority", 0)),
            }
    return None


def pick_overlay_response(*, intent: str, query: str, rules: List[Dict[str, Any]]) -> Optional[str]:
    """Backward-compatible helper returning only response text."""

    match = pick_overlay_match(intent=intent, query=query, rules=rules)
    return None if not match else str(match["response"])
