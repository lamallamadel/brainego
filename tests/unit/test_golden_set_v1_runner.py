"""Unit tests for S0-4 golden_set_v1 runner."""

import importlib.util
import json
from pathlib import Path

RUNNER_PATH = Path("scripts/golden_set_v1_runner.py")
SPEC = importlib.util.spec_from_file_location("golden_set_v1_runner", RUNNER_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_compute_metrics_core_values() -> None:
    cases = [
        {"id": "c1", "answerable": True},
        {"id": "c2", "answerable": True},
        {"id": "c3", "answerable": False},
    ]
    outputs = {
        "c1": {"supported_answer": True, "false_citation": False},
        "c2": {"supported_answer": False, "false_citation": True},
        "c3": {
            "false_citation": False,
            "missing_context": {
                "targeted_questions": ["Q?"],
                "ingestion_suggestion": "ingest this",
            },
        },
    }

    metrics, counts = MODULE.compute_metrics(cases, outputs)

    assert metrics["grounded_accuracy_answerable"] == 0.5
    assert metrics["false_citation_rate"] == round(1 / 3, 4)
    assert metrics["missing_context_actionable_rate"] == 1.0
    assert counts["answerable_total"] == 2


def test_golden_set_fixture_has_50_cases() -> None:
    golden_path = Path("tests/contract/fixtures/golden_set_v1.json")
    payload = json.loads(golden_path.read_text(encoding="utf-8"))
    assert payload["version"] == "golden_set_v1"
    assert len(payload["cases"]) == 50
