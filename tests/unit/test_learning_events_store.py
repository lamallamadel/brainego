"""Unit tests for learning events store."""

import importlib.util
import tempfile
from pathlib import Path

MODULE_PATH = Path("learning_events_store.py")
SPEC = importlib.util.spec_from_file_location("learning_events_store", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_store_append_and_list_workspace() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = MODULE.LearningEventsStore(path=Path(tmp) / "events.jsonl")
        store.append(workspace_id="ws1", event={"trigger": "x"})
        rows = store.list_workspace("ws1")
        assert len(rows) == 1
        assert rows[0]["workspace_id"] == "ws1"


def test_store_retention_keeps_last_n_for_workspace() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = MODULE.LearningEventsStore(path=Path(tmp) / "events.jsonl")
        for i in range(5):
            store.append(workspace_id="ws1", event={"i": i})
        store.retain_workspace_last_n("ws1", 2)
        rows = store.list_workspace("ws1")
        assert len(rows) == 2
