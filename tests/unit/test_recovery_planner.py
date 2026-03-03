"""Unit tests for S2-3 recovery planner."""

import importlib.util
from pathlib import Path

MODULE_PATH = Path("recovery_planner.py")
SPEC = importlib.util.spec_from_file_location("recovery_planner", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class _FakeService:
    def __init__(self):
        self.calls = []

    def search_documents(self, query, limit, filters, workspace_id):
        self.calls.append(query)
        if "better" in query:
            return [{"id": "x", "text": "better support context", "score": 0.95}]
        return [{"id": "y", "text": "weak", "score": 0.1}]


def test_recovery_planner_returns_best_recovered_ess() -> None:
    service = _FakeService()
    best_results, best_ess, attempts = MODULE.run_recovery_attempts(
        service=service,
        candidate_queries=["weak", "better query"],
        workspace_id="ws",
        rag_filters={},
        initial_results=[{"id": "i", "text": "none", "score": 0.05}],
        initial_sources=[],
        max_attempts=2,
        top_k=3,
    )
    assert attempts == 2
    assert best_ess > 0.5
    assert best_results[0]["id"] == "x"
