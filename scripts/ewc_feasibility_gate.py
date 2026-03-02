#!/usr/bin/env python3
"""Evidence-gated EWC feasibility harness.

This script compares two continual-learning runs:
- baseline (typically without EWC),
- candidate (typically with EWC),

and produces a decision report indicating whether enabling EWC is justified
by multi-project forgetting evidence and bounded operating cost.

Usage:
  python scripts/ewc_feasibility_gate.py --input /path/to/ewc_spike.json
  python scripts/ewc_feasibility_gate.py --input /path/to/ewc_spike.json --enforce-enable
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List


@dataclass(frozen=True)
class ProjectRetention:
    """Retention scores for one project before/after a new training step."""

    project: str
    before_score: float
    after_score: float


@dataclass(frozen=True)
class ExperimentRun:
    """Result summary for one experimental configuration."""

    label: str
    per_project_retention: List[ProjectRetention]
    new_project_score: float
    train_minutes: float
    fisher_minutes: float = 0.0
    fisher_size_gb: float = 0.0


@dataclass(frozen=True)
class CostProfile:
    """Cost assumptions used for incremental EWC cost estimation."""

    gpu_hour_usd: float = 2.5
    storage_gb_month_usd: float = 0.023


@dataclass(frozen=True)
class FeasibilityThresholds:
    """Evidence and cost thresholds for the EWC decision gate."""

    min_projects: int = 3
    trigger_mean_forgetting_pp: float = 3.0
    trigger_max_forgetting_pp: float = 7.0
    trigger_project_forgetting_pp: float = 5.0
    trigger_project_count: int = 2
    min_mean_reduction_pp: float = 1.5
    min_relative_reduction: float = 0.25
    max_new_project_regression_pp: float = 1.0
    max_training_overhead_pct: float = 40.0
    max_extra_gpu_cost_usd_per_run: float = 1.5
    max_extra_storage_gb: float = 2.0


def _infer_points_scale(score_values: List[float]) -> float:
    """Infer score scale. <=1.0 values are treated as ratios and converted to pp."""
    if not score_values:
        return 1.0
    max_abs = max(abs(value) for value in score_values)
    return 100.0 if max_abs <= 1.0 else 1.0


def _to_points(value: float, scale: float) -> float:
    return value * scale


def _round4(value: float) -> float:
    return round(value, 4)


def _parse_project_retention(raw_entries: List[Dict[str, Any]]) -> List[ProjectRetention]:
    parsed: List[ProjectRetention] = []
    for entry in raw_entries:
        parsed.append(
            ProjectRetention(
                project=str(entry["project"]),
                before_score=float(entry["before_score"]),
                after_score=float(entry["after_score"]),
            )
        )
    return parsed


def _parse_experiment_run(raw: Dict[str, Any], default_label: str) -> ExperimentRun:
    return ExperimentRun(
        label=str(raw.get("label", default_label)),
        per_project_retention=_parse_project_retention(raw.get("per_project_retention", [])),
        new_project_score=float(raw["new_project_score"]),
        train_minutes=float(raw["train_minutes"]),
        fisher_minutes=float(raw.get("fisher_minutes", 0.0)),
        fisher_size_gb=float(raw.get("fisher_size_gb", 0.0)),
    )


def _summarize_run(
    run: ExperimentRun,
    forgetting_threshold_pp: float,
    score_scale: float,
) -> Dict[str, Any]:
    forgetting_values: List[float] = []
    for project in run.per_project_retention:
        before_pp = _to_points(project.before_score, score_scale)
        after_pp = _to_points(project.after_score, score_scale)
        forgetting_values.append(max(0.0, before_pp - after_pp))

    project_count = len(forgetting_values)
    mean_forgetting = sum(forgetting_values) / project_count if project_count else 0.0
    max_forgetting = max(forgetting_values) if forgetting_values else 0.0
    projects_over_threshold = sum(
        1 for value in forgetting_values if value >= forgetting_threshold_pp
    )

    return {
        "label": run.label,
        "project_count": project_count,
        "mean_forgetting_pp": _round4(mean_forgetting),
        "max_forgetting_pp": _round4(max_forgetting),
        "projects_over_threshold": projects_over_threshold,
        "new_project_score": _round4(_to_points(run.new_project_score, score_scale)),
        "train_minutes": _round4(run.train_minutes),
        "fisher_minutes": _round4(run.fisher_minutes),
        "fisher_size_gb": _round4(run.fisher_size_gb),
    }


def evaluate_feasibility(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate EWC feasibility from baseline/candidate experiment payload."""
    thresholds = FeasibilityThresholds(**payload.get("thresholds", {}))
    cost_profile = CostProfile(**payload.get("cost_profile", {}))
    baseline = _parse_experiment_run(payload["baseline"], default_label="baseline")
    candidate = _parse_experiment_run(payload["candidate"], default_label="candidate")

    baseline_map = {entry.project: entry for entry in baseline.per_project_retention}
    candidate_map = {entry.project: entry for entry in candidate.per_project_retention}
    common_projects = [name for name in baseline_map if name in candidate_map]

    score_values: List[float] = [baseline.new_project_score, candidate.new_project_score]
    for name in common_projects:
        base_entry = baseline_map[name]
        cand_entry = candidate_map[name]
        score_values.extend(
            [
                base_entry.before_score,
                base_entry.after_score,
                cand_entry.before_score,
                cand_entry.after_score,
            ]
        )

    score_scale = _infer_points_scale(score_values)
    score_scale_name = "ratio_to_percentage_points" if score_scale == 100.0 else "percentage_points"

    aligned_baseline = ExperimentRun(
        label=baseline.label,
        per_project_retention=[baseline_map[name] for name in common_projects],
        new_project_score=baseline.new_project_score,
        train_minutes=baseline.train_minutes,
        fisher_minutes=baseline.fisher_minutes,
        fisher_size_gb=baseline.fisher_size_gb,
    )
    aligned_candidate = ExperimentRun(
        label=candidate.label,
        per_project_retention=[candidate_map[name] for name in common_projects],
        new_project_score=candidate.new_project_score,
        train_minutes=candidate.train_minutes,
        fisher_minutes=candidate.fisher_minutes,
        fisher_size_gb=candidate.fisher_size_gb,
    )

    baseline_summary = _summarize_run(
        aligned_baseline,
        forgetting_threshold_pp=thresholds.trigger_project_forgetting_pp,
        score_scale=score_scale,
    )
    candidate_summary = _summarize_run(
        aligned_candidate,
        forgetting_threshold_pp=thresholds.trigger_project_forgetting_pp,
        score_scale=score_scale,
    )

    mean_reduction_pp = baseline_summary["mean_forgetting_pp"] - candidate_summary["mean_forgetting_pp"]
    relative_reduction = (
        mean_reduction_pp / baseline_summary["mean_forgetting_pp"]
        if baseline_summary["mean_forgetting_pp"] > 0.0
        else 0.0
    )
    new_project_regression_pp = max(
        0.0,
        baseline_summary["new_project_score"] - candidate_summary["new_project_score"],
    )

    extra_training_minutes = max(
        0.0,
        (candidate.train_minutes + candidate.fisher_minutes) - baseline.train_minutes,
    )
    training_overhead_pct = (
        (extra_training_minutes / baseline.train_minutes) * 100.0
        if baseline.train_minutes > 0
        else 0.0
    )
    extra_gpu_cost_usd = (extra_training_minutes / 60.0) * cost_profile.gpu_hour_usd
    extra_storage_gb = max(0.0, candidate.fisher_size_gb - baseline.fisher_size_gb)
    extra_storage_monthly_cost_usd = extra_storage_gb * cost_profile.storage_gb_month_usd

    forgetting_triggered = (
        baseline_summary["mean_forgetting_pp"] >= thresholds.trigger_mean_forgetting_pp
        or baseline_summary["max_forgetting_pp"] >= thresholds.trigger_max_forgetting_pp
        or baseline_summary["projects_over_threshold"] >= thresholds.trigger_project_count
    )
    effectiveness_ok = (
        mean_reduction_pp >= thresholds.min_mean_reduction_pp
        and relative_reduction >= thresholds.min_relative_reduction
    )
    plasticity_ok = new_project_regression_pp <= thresholds.max_new_project_regression_pp
    cost_ok = (
        training_overhead_pct <= thresholds.max_training_overhead_pct
        and extra_gpu_cost_usd <= thresholds.max_extra_gpu_cost_usd_per_run
        and extra_storage_gb <= thresholds.max_extra_storage_gb
    )
    enough_projects = len(common_projects) >= thresholds.min_projects

    checks = {
        "enough_projects": enough_projects,
        "forgetting_triggered": forgetting_triggered,
        "effectiveness_ok": effectiveness_ok,
        "plasticity_ok": plasticity_ok,
        "cost_ok": cost_ok,
    }

    if not enough_projects:
        decision = "collect_more_evidence"
        ewc_needed = False
        reasons = [
            f"Need at least {thresholds.min_projects} common projects; found {len(common_projects)}."
        ]
    elif not forgetting_triggered:
        decision = "defer_ewc_low_forgetting"
        ewc_needed = False
        reasons = ["Baseline forgetting is below trigger thresholds."]
    elif forgetting_triggered and not effectiveness_ok:
        decision = "defer_ewc_low_effect"
        ewc_needed = False
        reasons = ["EWC candidate does not reduce forgetting enough."]
    elif forgetting_triggered and effectiveness_ok and not plasticity_ok:
        decision = "defer_ewc_plasticity_penalty"
        ewc_needed = False
        reasons = ["EWC hurts new-project quality beyond allowed regression."]
    elif forgetting_triggered and effectiveness_ok and plasticity_ok and not cost_ok:
        decision = "defer_ewc_cost_too_high"
        ewc_needed = False
        reasons = ["EWC overhead exceeds defined cost budget."]
    else:
        decision = "enable_ewc"
        ewc_needed = True
        reasons = ["Forgetting is material, EWC is effective, and cost is acceptable."]

    per_project: List[Dict[str, Any]] = []
    for name in common_projects:
        base_entry = baseline_map[name]
        cand_entry = candidate_map[name]
        base_forgetting = max(
            0.0,
            _to_points(base_entry.before_score, score_scale) - _to_points(base_entry.after_score, score_scale),
        )
        cand_forgetting = max(
            0.0,
            _to_points(cand_entry.before_score, score_scale) - _to_points(cand_entry.after_score, score_scale),
        )
        per_project.append(
            {
                "project": name,
                "baseline_forgetting_pp": _round4(base_forgetting),
                "candidate_forgetting_pp": _round4(cand_forgetting),
                "reduction_pp": _round4(base_forgetting - cand_forgetting),
            }
        )

    report = {
        "decision": decision,
        "ewc_needed": ewc_needed,
        "score_scale": score_scale_name,
        "thresholds": asdict(thresholds),
        "project_alignment": {
            "baseline_projects": [entry.project for entry in baseline.per_project_retention],
            "candidate_projects": [entry.project for entry in candidate.per_project_retention],
            "common_projects": common_projects,
            "common_project_count": len(common_projects),
        },
        "baseline": baseline_summary,
        "candidate": candidate_summary,
        "comparison": {
            "mean_reduction_pp": _round4(mean_reduction_pp),
            "relative_reduction": _round4(relative_reduction),
            "new_project_regression_pp": _round4(new_project_regression_pp),
            "per_project": per_project,
        },
        "cost": {
            "extra_training_minutes": _round4(extra_training_minutes),
            "training_overhead_pct": _round4(training_overhead_pct),
            "extra_gpu_cost_usd_per_run": _round4(extra_gpu_cost_usd),
            "extra_storage_gb": _round4(extra_storage_gb),
            "extra_storage_monthly_cost_usd": _round4(extra_storage_monthly_cost_usd),
            "assumptions": asdict(cost_profile),
        },
        "checks": checks,
        "reasons": reasons,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Evidence-gated EWC feasibility harness")
    parser.add_argument("--input", required=True, type=Path, help="Path to spike input JSON")
    parser.add_argument("--output", type=Path, help="Optional report output path")
    parser.add_argument(
        "--enforce-enable",
        action="store_true",
        help="Exit with code 1 unless decision is enable_ewc",
    )
    args = parser.parse_args()

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    report = evaluate_feasibility(payload)

    rendered = json.dumps(report, indent=2, sort_keys=False)
    print(rendered)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")

    if args.enforce_enable and report["decision"] != "enable_ewc":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
