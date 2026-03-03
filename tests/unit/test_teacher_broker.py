"""Unit tests for teacher broker redaction and guard behavior."""

import importlib.util
from pathlib import Path

MODULE_PATH = Path("teacher_broker.py")
SPEC = importlib.util.spec_from_file_location("teacher_broker", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_teacher_request_blocks_raw_chunk_markers() -> None:
    broker = MODULE.TeacherBroker(timeout_seconds=0.1)
    request, blocked = broker.build_request(
        question="q",
        metadata={"workspace_id": "ws", "grounding_intent": "must_ground", "ess": 0.2},
        redacted_summaries=["<<<BEGIN_CONTEXT_CHUNK>>> secret", "safe summary"],
    )
    assert blocked is True
    assert len(request["summaries"]) == 1


def test_teacher_request_includes_no_raw_chunk_markers() -> None:
    broker = MODULE.TeacherBroker(timeout_seconds=0.1)
    request, _ = broker.build_request(
        question="hello",
        metadata={"workspace_id": "ws"},
        redacted_summaries=["safe text"],
    )
    assert all("BEGIN_CONTEXT" not in s for s in request["summaries"])
