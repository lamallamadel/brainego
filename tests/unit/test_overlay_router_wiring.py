"""Static wiring checks for S3-4 overlay router in inference path."""

from pathlib import Path


SOURCE = Path("api_server.py").read_text(encoding="utf-8")


def test_chat_completions_applies_overlay_before_generation() -> None:
    assert "overlay_rules_store.get_active_rules(workspace_id)" in SOURCE
    assert "pick_overlay_match(" in SOURCE
    assert '"overlay_applied": True' in SOURCE

    assert "\"overlay_rule_id\": overlay_match.get(\"rule_id\")" in SOURCE
    assert "\"overlay_rule_priority\": overlay_match.get(\"priority\")" in SOURCE
