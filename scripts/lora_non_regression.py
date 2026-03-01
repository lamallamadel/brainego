#!/usr/bin/env python3
"""LoRA non-regression harness.

Usage:
  python scripts/lora_non_regression.py \
    --suite tests/contract/fixtures/lora_regression_prompts.ndjson \
    --baseline-output tests/contract/fixtures/lora_baseline_outputs.ndjson \
    --candidate-output /tmp/new_lora_outputs.json

The script exits with code 1 when promotion must be blocked.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class PromptCase:
    case_id: str
    prompt: str
    must_include: List[str]
    must_not_include: List[str]
    category: str
    severity: str


@dataclass(frozen=True)
class CaseEvaluation:
    case_id: str
    passed: bool
    score: float
    details: str


@dataclass(frozen=True)
class EvalSummary:
    total: int
    passed: int
    failed: int
    pass_rate: float
    mean_score: float
    cases: List[CaseEvaluation]


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def load_prompt_suite(path: Path) -> List[PromptCase]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    cases = []
    for item in raw["cases"]:
        cases.append(
            PromptCase(
                case_id=item["id"],
                prompt=item["prompt"],
                must_include=item.get("must_include", []),
                must_not_include=item.get("must_not_include", []),
                category=item.get("category", "general"),
                severity=item.get("severity", "medium"),
            )
        )
    return cases


def evaluate_single_case(case: PromptCase, response: str) -> CaseEvaluation:
    normalized = _normalize(response)

    include_hits = sum(1 for token in case.must_include if _normalize(token) in normalized)
    include_total = max(len(case.must_include), 1)
    include_score = include_hits / include_total

    forbidden_hits = [token for token in case.must_not_include if _normalize(token) in normalized]
    forbidden_penalty = 1.0 if forbidden_hits else 0.0

    score = max(0.0, include_score - forbidden_penalty)
    passed = include_hits == len(case.must_include) and not forbidden_hits

    details = (
        f"include={include_hits}/{len(case.must_include)}; "
        f"forbidden_hits={','.join(forbidden_hits) if forbidden_hits else 'none'}"
    )

    return CaseEvaluation(case_id=case.case_id, passed=passed, score=round(score, 4), details=details)


def evaluate_outputs(cases: List[PromptCase], outputs: Dict[str, str]) -> EvalSummary:
    evaluations: List[CaseEvaluation] = []
    for case in cases:
        response = outputs.get(case.case_id, "")
        evaluations.append(evaluate_single_case(case, response))

    total = len(evaluations)
    passed = sum(1 for case in evaluations if case.passed)
    failed = total - passed
    mean_score = sum(case.score for case in evaluations) / total if total else 0.0
    pass_rate = passed / total if total else 0.0

    return EvalSummary(
        total=total,
        passed=passed,
        failed=failed,
        pass_rate=round(pass_rate, 4),
        mean_score=round(mean_score, 4),
        cases=evaluations,
    )


def compare_with_baseline(
    baseline: EvalSummary,
    candidate: EvalSummary,
    max_regressions: int,
    max_mean_score_drop: float,
    min_pass_rate: float,
) -> Tuple[bool, Dict[str, float]]:
    regressed_cases = sum(1 for b, c in zip(baseline.cases, candidate.cases) if b.passed and not c.passed)
    mean_score_drop = baseline.mean_score - candidate.mean_score

    approved = (
        regressed_cases <= max_regressions
        and mean_score_drop <= max_mean_score_drop
        and candidate.pass_rate >= min_pass_rate
    )

    return approved, {
        "regressed_cases": regressed_cases,
        "baseline_pass_rate": baseline.pass_rate,
        "candidate_pass_rate": candidate.pass_rate,
        "baseline_mean_score": baseline.mean_score,
        "candidate_mean_score": candidate.mean_score,
        "mean_score_drop": round(mean_score_drop, 4),
    }


def _load_outputs(path: Path) -> Dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "outputs" in data:
        return data["outputs"]
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="LoRA non-regression gate")
    parser.add_argument("--suite", required=True, type=Path)
    parser.add_argument("--baseline-output", required=True, type=Path)
    parser.add_argument("--candidate-output", required=True, type=Path)
    parser.add_argument("--max-regressions", type=int, default=1)
    parser.add_argument("--max-mean-score-drop", type=float, default=0.15)
    parser.add_argument("--min-pass-rate", type=float, default=0.85)
    args = parser.parse_args()

    suite = load_prompt_suite(args.suite)
    baseline_outputs = _load_outputs(args.baseline_output)
    candidate_outputs = _load_outputs(args.candidate_output)

    baseline_summary = evaluate_outputs(suite, baseline_outputs)
    candidate_summary = evaluate_outputs(suite, candidate_outputs)
    approved, comparison = compare_with_baseline(
        baseline_summary,
        candidate_summary,
        max_regressions=args.max_regressions,
        max_mean_score_drop=args.max_mean_score_drop,
        min_pass_rate=args.min_pass_rate,
    )

    report = {
        "approved": approved,
        "thresholds": {
            "max_regressions": args.max_regressions,
            "max_mean_score_drop": args.max_mean_score_drop,
            "min_pass_rate": args.min_pass_rate,
        },
        "comparison": comparison,
        "candidate_failures": [c.__dict__ for c in candidate_summary.cases if not c.passed],
    }
    print(json.dumps(report, indent=2))

    return 0 if approved else 1


if __name__ == "__main__":
    raise SystemExit(main())
