"""Build versioned JSONL distillation datasets from learning events."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

SECRET_PATTERNS = [
    re.compile(r"api[_-]?key", re.IGNORECASE),
    re.compile(r"password", re.IGNORECASE),
    re.compile(r"token\s*=", re.IGNORECASE),
    re.compile(r"secret", re.IGNORECASE),
]


def _has_secret_leak(value: Any) -> bool:
    text = str(value or "")
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def _safe_text(value: Any) -> str:
    text = str(value or "").strip()
    return text


def _event_to_sample(row: Dict[str, Any]) -> Tuple[Dict[str, Any] | None, str | None]:
    event = row.get("event", row)
    if not isinstance(event, dict):
        return None, "invalid_event"

    # only validated, supported examples
    if not bool(event.get("supported", False)):
        return None, "unsupported"

    instruction = _safe_text(event.get("query") or event.get("prompt"))
    output = _safe_text(event.get("answer") or event.get("response"))
    evidence = event.get("evidence") or []

    if not instruction or not output:
        return None, "missing_fields"

    if _has_secret_leak(instruction) or _has_secret_leak(output) or _has_secret_leak(json.dumps(evidence, ensure_ascii=False)):
        return None, "secret_leak"

    sample = {
        "instruction": instruction,
        "input": "",
        "output": output,
        "metadata": {
            "workspace_id": row.get("workspace_id"),
            "created_at": row.get("created_at"),
            "evidence_count": len(evidence) if isinstance(evidence, list) else 0,
            "source": "learning_events",
            "version": row.get("version"),
            "feedback_score": event.get("feedback_score", 1.0),
            "policy_pass": bool(event.get("policy_pass", True)),
        },
    }
    return sample, None


def build_versioned_dataset(*, events: Iterable[Dict[str, Any]], output_dir: Path, dataset_prefix: str = "learning_distill") -> Dict[str, Any]:
    """Build a versioned JSONL dataset from validated learning events."""

    output_dir.mkdir(parents=True, exist_ok=True)
    version = int(time.time())
    dataset_path = output_dir / f"{dataset_prefix}_v{version}.jsonl"

    rows_written = 0
    rejected: Dict[str, int] = {}

    with dataset_path.open("w", encoding="utf-8") as f:
        for row in events:
            sample, reason = _event_to_sample(row)
            if sample is None:
                rejected[reason or "unknown"] = rejected.get(reason or "unknown", 0) + 1
                continue
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")
            rows_written += 1

    return {
        "dataset_path": str(dataset_path),
        "dataset_version": f"v{version}",
        "rows_written": rows_written,
        "rejected": rejected,
    }


def apply_quality_filter(samples: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Filter samples using supported evidence + feedback + policy gates."""

    kept: List[Dict[str, Any]] = []
    rejected: Dict[str, int] = {}

    for sample in samples:
        metadata = sample.get("metadata", {}) if isinstance(sample, dict) else {}
        feedback_score = metadata.get("feedback_score", 1.0)
        evidence_count = int(metadata.get("evidence_count", 0))
        policy_ok = bool(metadata.get("policy_pass", True))

        if evidence_count <= 0:
            rejected["missing_evidence"] = rejected.get("missing_evidence", 0) + 1
            continue
        try:
            score = float(feedback_score)
        except (TypeError, ValueError):
            score = 0.0
        if score < 0.6:
            rejected["low_feedback"] = rejected.get("low_feedback", 0) + 1
            continue
        if not policy_ok:
            rejected["policy_reject"] = rejected.get("policy_reject", 0) + 1
            continue

        kept.append(sample)

    audit_sample_size = len(kept) + sum(rejected.values())
    precision_estimate = (len(kept) / audit_sample_size) if audit_sample_size else 0.0

    return {
        "kept": kept,
        "kept_count": len(kept),
        "rejected": rejected,
        "precision_estimate": round(precision_estimate, 4),
        "meets_precision_target": precision_estimate >= 0.95,
    }
