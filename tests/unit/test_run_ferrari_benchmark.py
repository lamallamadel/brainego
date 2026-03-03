import importlib.util
import json
import sys
from pathlib import Path


MODULE_PATH = Path("scripts/eval/run_ferrari_benchmark.py")
spec = importlib.util.spec_from_file_location("run_ferrari_benchmark", MODULE_PATH)
run_ferrari_benchmark = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = run_ferrari_benchmark
spec.loader.exec_module(run_ferrari_benchmark)


def test_missing_context_actionable_contract():
    assert run_ferrari_benchmark._is_actionable_missing_context(
        {
            "targeted_questions": ["q1", "q2", "q3"],
            "ingestion_suggestion": "ingest files",
        }
    )
    assert not run_ferrari_benchmark._is_actionable_missing_context({"targeted_questions": [], "ingestion_suggestion": "x"})


def test_evaluate_cases_metrics_shape():
    cases = [
        {"id": "a1", "answerable": True, "workspace_id": "ws-a"},
        {"id": "m1", "answerable": False, "workspace_id": "ws-a"},
    ]
    outputs = {
        "a1": {
            "id": "a1",
            "supported_answer": True,
            "sources": [{"path": "api_server.py", "commit": "a" * 40, "workspace_id": "ws-a"}],
            "retrieval_stats": {"total_time_ms": 120.0},
        },
        "m1": {
            "id": "m1",
            "response": json.dumps(
                {
                    "type": "missing_context",
                    "targeted_questions": ["q1", "q2"],
                    "ingestion_suggestion": "Ingest docs",
                }
            ),
            "sources": [],
            "retrieval_stats": {"total_time_ms": 80.0},
        },
    }

    report = run_ferrari_benchmark._evaluate_cases(cases, outputs)
    assert report["metrics"]["grounded_accuracy_answerable"] == 1.0
    assert report["metrics"]["missing_context_actionable_rate"] == 1.0
    assert report["metrics"]["false_citation_rate"] == 0.0
    assert report["metrics"]["leakage"] == 0
