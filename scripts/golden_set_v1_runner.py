#!/usr/bin/env python3
"""Runner for S0-4 golden_set_v1 grounded metrics.

Computes:
- grounded_accuracy_answerable
- false_citation_rate
- missing_context_actionable_rate

Input outputs JSON can be a list or {"outputs": [...]} where each output item includes:
- id
- supported_answer (bool)
- false_citation (bool)
- missing_context: {targeted_questions: [...], ingestion_suggestion: str}
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _load_outputs(path: Path) -> Dict[str, Dict[str, Any]]:
    raw = _load_json(path)
    items: List[Dict[str, Any]]
    if isinstance(raw, dict):
        items = list(raw.get("outputs", []))
    elif isinstance(raw, list):
        items = list(raw)
    else:
        items = []
    out: Dict[str, Dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        case_id = str(item.get("id", "")).strip()
        if case_id:
            out[case_id] = item
    return out


def compute_metrics(golden_cases: List[Dict[str, Any]], outputs: Dict[str, Dict[str, Any]]) -> Tuple[Dict[str, float], Dict[str, int]]:
    answerable_total = 0
    answerable_supported = 0

    false_citation_total = 0
    false_citation_count = 0

    missing_context_total = 0
    missing_context_actionable = 0

    for case in golden_cases:
        case_id = str(case.get("id", "")).strip()
        if not case_id:
            continue
        output = outputs.get(case_id, {})
        answerable = _as_bool(case.get("answerable", False))

        if answerable:
            answerable_total += 1
            if _as_bool(output.get("supported_answer", False)):
                answerable_supported += 1

        if "false_citation" in output:
            false_citation_total += 1
            if _as_bool(output.get("false_citation", False)):
                false_citation_count += 1

        if not answerable:
            missing_context_total += 1
            mc = output.get("missing_context") or {}
            questions = mc.get("targeted_questions") if isinstance(mc, dict) else []
            suggestion = mc.get("ingestion_suggestion") if isinstance(mc, dict) else ""
            has_questions = isinstance(questions, list) and len([q for q in questions if str(q).strip()]) >= 1
            has_suggestion = isinstance(suggestion, str) and bool(suggestion.strip())
            if has_questions and has_suggestion:
                missing_context_actionable += 1

    metrics = {
        "grounded_accuracy_answerable": round(answerable_supported / answerable_total, 4) if answerable_total else 0.0,
        "false_citation_rate": round(false_citation_count / false_citation_total, 4) if false_citation_total else 0.0,
        "missing_context_actionable_rate": round(missing_context_actionable / missing_context_total, 4) if missing_context_total else 0.0,
    }
    counts = {
        "answerable_total": answerable_total,
        "answerable_supported": answerable_supported,
        "false_citation_total": false_citation_total,
        "false_citation_count": false_citation_count,
        "missing_context_total": missing_context_total,
        "missing_context_actionable": missing_context_actionable,
    }
    return metrics, counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Run S0-4 golden-set v1 metrics")
    parser.add_argument("--golden-set", required=True)
    parser.add_argument("--outputs", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    golden = _load_json(Path(args.golden_set))
    cases = golden.get("cases", []) if isinstance(golden, dict) else []
    outputs = _load_outputs(Path(args.outputs))

    metrics, counts = compute_metrics(cases, outputs)

    report = {
        "golden_set_version": golden.get("version", "unknown") if isinstance(golden, dict) else "unknown",
        "metrics": metrics,
        "counts": counts,
    }

    Path(args.report).write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("Golden set v1 report")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
