"""Unit tests for learning dataset builder from learning events."""

import importlib.util
import json
from pathlib import Path

MODULE_PATH = Path("learning_dataset_builder.py")
SPEC = importlib.util.spec_from_file_location("learning_dataset_builder", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_builder_exports_only_supported_and_redacted_safe_rows(tmp_path: Path) -> None:
    events = [
        {
            "workspace_id": "w1",
            "created_at": 1,
            "version": 1,
            "event": {"supported": True, "query": "How to deploy?", "answer": "Use rollout strategy", "evidence": ["doc1"]},
        },
        {
            "workspace_id": "w1",
            "created_at": 2,
            "version": 1,
            "event": {"supported": False, "query": "x", "answer": "y"},
        },
        {
            "workspace_id": "w1",
            "created_at": 3,
            "version": 1,
            "event": {"supported": True, "query": "api_key is 123", "answer": "oops"},
        },
    ]

    out = MODULE.build_versioned_dataset(events=events, output_dir=tmp_path)
    assert out["rows_written"] == 1
    assert out["rejected"]["unsupported"] == 1
    assert out["rejected"]["secret_leak"] == 1

    lines = Path(out["dataset_path"]).read_text(encoding="utf-8").splitlines()
    payload = json.loads(lines[0])
    assert payload["instruction"] == "How to deploy?"
    assert payload["output"] == "Use rollout strategy"


def test_builder_rejects_missing_fields(tmp_path: Path) -> None:
    events = [{"workspace_id": "w1", "event": {"supported": True, "query": "", "answer": ""}}]
    out = MODULE.build_versioned_dataset(events=events, output_dir=tmp_path)
    assert out["rows_written"] == 0
    assert out["rejected"]["missing_fields"] == 1


def test_quality_filter_rejects_samples_without_evidence() -> None:
    samples = [
        {"instruction": "q1", "output": "a1", "metadata": {"evidence_count": 0, "feedback_score": 0.9, "policy_pass": True}},
        {"instruction": "q2", "output": "a2", "metadata": {"evidence_count": 2, "feedback_score": 0.4, "policy_pass": True}},
        {"instruction": "q3", "output": "a3", "metadata": {"evidence_count": 2, "feedback_score": 0.9, "policy_pass": False}},
        {"instruction": "q4", "output": "a4", "metadata": {"evidence_count": 3, "feedback_score": 0.95, "policy_pass": True}},
    ]
    out = MODULE.apply_quality_filter(samples)
    assert out["kept_count"] == 1
    assert out["rejected"]["missing_evidence"] == 1
    assert out["rejected"]["low_feedback"] == 1
    assert out["rejected"]["policy_reject"] == 1


def test_quality_filter_precision_gate_flag() -> None:
    good_samples = [
        {"instruction": "q", "output": "a", "metadata": {"evidence_count": 2, "feedback_score": 1.0, "policy_pass": True}}
        for _ in range(20)
    ]
    out = MODULE.apply_quality_filter(good_samples)
    assert out["meets_precision_target"] is True
    assert out["precision_estimate"] >= 0.95
