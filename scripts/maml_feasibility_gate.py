#!/usr/bin/env python3
"""Evidence-gated MAML feasibility harness.

This script compares two adaptation configurations:
- baseline (LoRA-only),
- candidate (LoRA + MAML),

and produces a decision report indicating whether enabling MAML is justified
by multi-project adaptation-speed evidence and bounded cost/risk.

Usage:
  python scripts/maml_feasibility_gate.py --input /path/to/maml_spike.json
  python scripts/maml_feasibility_gate.py --input /path/to/maml_spike.json --enforce-enable
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List


@dataclass(frozen=True)
class ProjectAdaptation:
    """Adaptation profile for one project."""

    project: str
    steps_to_target: float
    target_accuracy: float
    final_accuracy: float


@dataclass(frozen=True)
class ExperimentRun:
    """Result summary for one adaptation strategy."""

    label: str
    per_project_adaptation: List[ProjectAdaptation]
    train_minutes: float
    meta_train_minutes: float = 0.0


@dataclass(frozen=True)
class CostProfile:
    """Cost assumptions used for incremental MAML cost estimation."""

    gpu_hour_usd: float = 2.5


@dataclass(frozen=True)
class FeasibilityThresholds:
    """Evidence and cost thresholds for the MAML decision gate."""

    min_projects: int = 3
    trigger_mean_steps: float = 4.0
    trigger_max_steps: float = 7.0
    min_mean_step_reduction: float = 1.5
    min_relative_step_reduction: float = 0.25
    max_mean_accuracy_regression_pp: float = 1.0
    max_training_overhead_pct: float = 50.0
    max_extra_gpu_cost_usd_per_run: float = 2.0


def _infer_points_scale(score_values: List[float]) -> float:
    if not score_values:
        return 1.0
    max_abs = max(abs(value) for value in score_values)
    return 100.0 if max_abs <= 1.0 else 1.0


def _to_points(value: float, scale: float) -> float:
    return value * scale


def _round4(value: float) -> float:
    return round(value, 4)


def _parse_project_adaptation(raw_entries: List[Dict[str, Any]]) -> List[ProjectAdaptation]:
    parsed: List[ProjectAdaptation] = []
    for entry in raw_entries:
        parsed.append(
            ProjectAdaptation(
                project=str(entry["project"]),
                steps_to_target=float(entry["steps_to_target"]),
                target_accuracy=float(entry["target_accuracy"]),
                final_accuracy=float(entry.get("final_accuracy", entry["target_accuracy"])),
            )
        )
    return parsed


def _parse_experiment_run(raw: Dict[str, Any], default_label: str) -> ExperimentRun:
    return ExperimentRun(
        label=str(raw.get("label", default_label)),
        per_project_adaptation=_parse_project_adaptation(raw.get("per_project_adaptation", [])),
        train_minutes=float(raw["train_minutes"]),
        meta_train_minutes=float(raw.get("meta_train_minutes", 0.0)),
    )


def _summarize_run(run: ExperimentRun, score_scale: float) -> Dict[str, Any]:
    steps_values = [entry.steps_to_target for entry in run.per_project_adaptation]
    accuracy_values_pp = [_to_points(entry.final_accuracy, score_scale) for entry in run.per_project_adaptation]

    project_count = len(steps_values)
    mean_steps = sum(steps_values) / project_count if project_count else 0.0
    max_steps = max(steps_values) if steps_values else 0.0
    mean_accuracy_pp = sum(accuracy_values_pp) / project_count if project_count else 0.0

    return {
        "label": run.label,
        "project_count": project_count,
        "mean_steps_to_target": _round4(mean_steps),
        "max_steps_to_target": _round4(max_steps),
        "mean_final_accuracy_pp": _round4(mean_accuracy_pp),
        "train_minutes": _round4(run.train_minutes),
        "meta_train_minutes": _round4(run.meta_train_minutes),
    }


def evaluate_feasibility(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate MAML feasibility from LoRA-only vs LoRA+MAML payload."""
    thresholds = FeasibilityThresholds(**payload.get("thresholds", {}))
    cost_profile = CostProfile(**payload.get("cost_profile", {}))
    baseline = _parse_experiment_run(payload["baseline"], default_label="lora_only")
    candidate = _parse_experiment_run(payload["candidate"], default_label="lora_plus_maml")

    baseline_map = {entry.project: entry for entry in baseline.per_project_adaptation}
    candidate_map = {entry.project: entry for entry in candidate.per_project_adaptation}
    common_projects = [name for name in baseline_map if name in candidate_map]

    score_values: List[float] = []
    for name in common_projects:
        base_entry = baseline_map[name]
        cand_entry = candidate_map[name]
        score_values.extend([base_entry.target_accuracy, base_entry.final_accuracy, cand_entry.target_accuracy, cand_entry.final_accuracy])

    score_scale = _infer_points_scale(score_values)
    score_scale_name = "ratio_to_percentage_points" if score_scale == 100.0 else "percentage_points"

    aligned_baseline = ExperimentRun(
        label=baseline.label,
        per_project_adaptation=[baseline_map[name] for name in common_projects],
        train_minutes=baseline.train_minutes,
        meta_train_minutes=baseline.meta_train_minutes,
    )
    aligned_candidate = ExperimentRun(
        label=candidate.label,
        per_project_adaptation=[candidate_map[name] for name in common_projects],
        train_minutes=candidate.train_minutes,
        meta_train_minutes=candidate.meta_train_minutes,
    )

    baseline_summary = _summarize_run(aligned_baseline, score_scale)
    candidate_summary = _summarize_run(aligned_candidate, score_scale)

    mean_step_reduction = baseline_summary["mean_steps_to_target"] - candidate_summary["mean_steps_to_target"]
    relative_step_reduction = (
        mean_step_reduction / baseline_summary["mean_steps_to_target"] if baseline_summary["mean_steps_to_target"] > 0 else 0.0
    )
    mean_accuracy_regression_pp = max(
        0.0,
        baseline_summary["mean_final_accuracy_pp"] - candidate_summary["mean_final_accuracy_pp"],
    )

    extra_training_minutes = max(0.0, (candidate.train_minutes + candidate.meta_train_minutes) - baseline.train_minutes)
    training_overhead_pct = (
        (extra_training_minutes / baseline.train_minutes) * 100.0 if baseline.train_minutes > 0 else 0.0
    )
    extra_gpu_cost_usd = (extra_training_minutes / 60.0) * cost_profile.gpu_hour_usd

    adaptation_triggered = (
        baseline_summary["mean_steps_to_target"] >= thresholds.trigger_mean_steps
        or baseline_summary["max_steps_to_target"] >= thresholds.trigger_max_steps
    )
    effectiveness_ok = (
        mean_step_reduction >= thresholds.min_mean_step_reduction
        and relative_step_reduction >= thresholds.min_relative_step_reduction
    )
    accuracy_ok = mean_accuracy_regression_pp <= thresholds.max_mean_accuracy_regression_pp
    cost_ok = (
        training_overhead_pct <= thresholds.max_training_overhead_pct
        and extra_gpu_cost_usd <= thresholds.max_extra_gpu_cost_usd_per_run
    )
    enough_projects = len(common_projects) >= thresholds.min_projects

    checks = {
        "enough_projects": enough_projects,
        "adaptation_triggered": adaptation_triggered,
        "effectiveness_ok": effectiveness_ok,
        "accuracy_ok": accuracy_ok,
        "cost_ok": cost_ok,
    }

    if not enough_projects:
        decision = "collect_more_evidence"
        maml_recommended = False
        reasons = [
            f"Need at least {thresholds.min_projects} common projects; found {len(common_projects)}."
        ]
    elif not adaptation_triggered:
        decision = "defer_maml_fast_enough"
        maml_recommended = False
        reasons = ["LoRA-only adaptation is already within acceptable step thresholds."]
    elif adaptation_triggered and not effectiveness_ok:
        decision = "defer_maml_low_effect"
        maml_recommended = False
        reasons = ["MAML candidate does not reduce adaptation steps enough."]
    elif adaptation_triggered and effectiveness_ok and not accuracy_ok:
        decision = "defer_maml_accuracy_penalty"
        maml_recommended = False
        reasons = ["MAML harms mean final accuracy beyond allowed regression."]
    elif adaptation_triggered and effectiveness_ok and accuracy_ok and not cost_ok:
        decision = "defer_maml_cost_too_high"
        maml_recommended = False
        reasons = ["MAML overhead exceeds defined training cost budget."]
    else:
        decision = "enable_maml"
        maml_recommended = True
        reasons = ["Adaptation is slow, MAML meaningfully reduces steps, and cost/risk is acceptable."]

    per_project: List[Dict[str, Any]] = []
    for name in common_projects:
        base_entry = baseline_map[name]
        cand_entry = candidate_map[name]
        per_project.append(
            {
                "project": name,
                "baseline_steps_to_target": _round4(base_entry.steps_to_target),
                "candidate_steps_to_target": _round4(cand_entry.steps_to_target),
                "step_reduction": _round4(base_entry.steps_to_target - cand_entry.steps_to_target),
                "baseline_final_accuracy_pp": _round4(_to_points(base_entry.final_accuracy, score_scale)),
                "candidate_final_accuracy_pp": _round4(_to_points(cand_entry.final_accuracy, score_scale)),
            }
        )

    return {
        "decision": decision,
        "maml_recommended": maml_recommended,
        "score_scale": score_scale_name,
        "thresholds": asdict(thresholds),
        "project_alignment": {
            "baseline_projects": [entry.project for entry in baseline.per_project_adaptation],
            "candidate_projects": [entry.project for entry in candidate.per_project_adaptation],
            "common_projects": common_projects,
            "common_project_count": len(common_projects),
        },
        "baseline": baseline_summary,
        "candidate": candidate_summary,
        "comparison": {
            "mean_step_reduction": _round4(mean_step_reduction),
            "relative_step_reduction": _round4(relative_step_reduction),
            "mean_accuracy_regression_pp": _round4(mean_accuracy_regression_pp),
            "per_project": per_project,
        },
        "cost": {
            "extra_training_minutes": _round4(extra_training_minutes),
            "training_overhead_pct": _round4(training_overhead_pct),
            "extra_gpu_cost_usd_per_run": _round4(extra_gpu_cost_usd),
            "assumptions": asdict(cost_profile),
        },
        "checks": checks,
        "reasons": reasons,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evidence-gated MAML feasibility harness")
    parser.add_argument("--input", required=True, type=Path, help="Path to spike input JSON")
    parser.add_argument("--output", type=Path, help="Optional report output path")
    parser.add_argument(
        "--enforce-enable",
        action="store_true",
        help="Exit with code 1 unless decision is enable_maml",
    )
    args = parser.parse_args()

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    report = evaluate_feasibility(payload)

    rendered = json.dumps(report, indent=2, sort_keys=False)
    print(rendered)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")

    if args.enforce_enable and report["decision"] != "enable_maml":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
