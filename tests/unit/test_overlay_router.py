"""Unit tests for overlay router rule matching."""

import importlib.util
from pathlib import Path

MODULE_PATH = Path("overlay_router.py")
SPEC = importlib.util.spec_from_file_location("overlay_router", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_pick_overlay_response_matches_intent_and_contains() -> None:
    rules = [{"intent": "freeform", "contains": "bonjour", "response": "Bonjour 👋", "enabled": True}]
    out = MODULE.pick_overlay_response(intent="freeform", query="bonjour bot", rules=rules)
    assert out == "Bonjour 👋"


def test_pick_overlay_response_returns_none_when_no_match() -> None:
    rules = [{"intent": "must_ground", "contains": "policy", "response": "x", "enabled": True}]
    out = MODULE.pick_overlay_response(intent="freeform", query="hello", rules=rules)
    assert out is None


def test_pick_overlay_response_prefers_high_priority_rule() -> None:
    rules = [
        {"intent": "freeform", "contains": "policy", "response": "low", "priority": 1, "enabled": True},
        {"intent": "freeform", "contains": "policy", "response": "high", "priority": 10, "enabled": True},
    ]
    out = MODULE.pick_overlay_response(intent="freeform", query="policy please", rules=rules)
    assert out == "high"


def test_pick_overlay_match_handles_non_integer_priority() -> None:
    rules = [
        {"intent": "freeform", "contains": "policy", "response": "safe", "priority": "high", "enabled": True},
    ]
    out = MODULE.pick_overlay_match(intent="freeform", query="policy now", rules=rules)
    assert out is not None
    assert out["priority"] == 0


def test_pick_overlay_match_generates_default_rule_id_when_missing() -> None:
    rules = [
        {"intent": "freeform", "contains": "policy", "response": "safe", "enabled": True},
    ]
    out = MODULE.pick_overlay_match(intent="freeform", query="policy now", rules=rules)
    assert out is not None
    assert out["rule_id"].startswith("rule-")
