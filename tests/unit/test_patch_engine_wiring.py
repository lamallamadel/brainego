"""Static wiring tests for S3-3 patch engine integration."""

from pathlib import Path


SOURCE = Path("api_server.py").read_text(encoding="utf-8")


def test_api_exposes_learning_promote_endpoint() -> None:
    assert '@app.post("/v1/learning/promote")' in SOURCE
    assert "promote_learning_events(" in SOURCE
    assert "learning_events_store.list_workspace" in SOURCE
