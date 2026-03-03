"""Unit tests for overlay rules store versioning and rollback."""

import importlib.util
import tempfile
from pathlib import Path

MODULE_PATH = Path("overlay_rules_store.py")
SPEC = importlib.util.spec_from_file_location("overlay_rules_store", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_overlay_versioning_enable_disable_and_rollback() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = MODULE.OverlayRulesStore(path=Path(tmp) / "overlay.json")
        v1 = store.create_version(rules=[{"intent": "greeting", "response": "Bonjour"}], workspace_id="ws1")
        v2 = store.create_version(rules=[{"intent": "greeting", "response": "Salut"}], workspace_id="ws1")
        assert v2 > v1
        assert store.get_active_rules("ws1")[0]["response"] == "Salut"
        store.set_enabled(version=v2, enabled=False)
        assert store.get_active_rules("ws1") == []
        store.set_enabled(version=v2, enabled=True)
        store.rollback(v1)
        assert store.get_active_rules("ws1")[0]["response"] == "Bonjour"
