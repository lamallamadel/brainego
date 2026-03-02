# AFR-141 — MAML feasibility spike (evidence-gated)

## Objective

Determine whether MAML should be enabled on top of LoRA for multi-project adaptation, based on measurable adaptation-step reduction with explicit quality and cost constraints.

This spike provides:

1. a reproducible evidence gate (`scripts/maml_feasibility_gate.py`),
2. explicit success criteria for enabling MAML,
3. an operating cost model (extra training + meta-training overhead).

## Why an evidence gate is needed

MAML introduces additional training complexity and overhead. It should only be enabled when:

- there is adaptation-speed pain on LoRA-only,
- MAML materially reduces steps to target,
- quality remains within baseline thresholds,
- cost increase is within budget.

## Input contract

The harness expects a JSON payload with:

- `baseline`: LoRA-only run,
- `candidate`: LoRA + MAML run,
- `cost_profile`: GPU pricing assumptions,
- `thresholds`: gate thresholds.

Minimal example:

```json
{
  "baseline": {
    "label": "lora_only",
    "per_project_adaptation": [
      {"project": "project-a", "steps_to_target": 8, "target_accuracy": 0.80, "final_accuracy": 0.81},
      {"project": "project-b", "steps_to_target": 7, "target_accuracy": 0.78, "final_accuracy": 0.79},
      {"project": "project-c", "steps_to_target": 6, "target_accuracy": 0.76, "final_accuracy": 0.77}
    ],
    "train_minutes": 45.0
  },
  "candidate": {
    "label": "lora_plus_maml",
    "per_project_adaptation": [
      {"project": "project-a", "steps_to_target": 5, "target_accuracy": 0.80, "final_accuracy": 0.805},
      {"project": "project-b", "steps_to_target": 4, "target_accuracy": 0.78, "final_accuracy": 0.785},
      {"project": "project-c", "steps_to_target": 4, "target_accuracy": 0.76, "final_accuracy": 0.765}
    ],
    "train_minutes": 55.0,
    "meta_train_minutes": 8.0
  }
}
```

Notes:

- Accuracy scores can be in `[0,1]` ratio form (auto-converted to percentage points),
- or directly in percentage points.

## Gate logic

The harness computes:

- baseline adaptation speed (`mean_steps_to_target`, `max_steps_to_target`),
- candidate adaptation speed and reduction vs baseline,
- mean final-accuracy regression,
- incremental cost:
  - `extra_training_minutes`,
  - `training_overhead_pct`,
  - `extra_gpu_cost_usd_per_run`.

Decision outcomes:

- `enable_maml`
- `defer_maml_fast_enough`
- `defer_maml_low_effect`
- `defer_maml_accuracy_penalty`
- `defer_maml_cost_too_high`
- `collect_more_evidence`

## Success criteria for enabling MAML

Default thresholds (overridable in payload):

- at least `3` common projects,
- adaptation trigger reached on baseline:
  - mean steps to target >= `4.0`, or
  - max steps to target >= `7.0`,
- MAML effectiveness:
  - mean step reduction >= `1.5`,
  - relative step reduction >= `25%`,
- quality guard:
  - mean final-accuracy regression <= `1.0pp`,
- cost guard:
  - training overhead <= `50%`,
  - extra GPU cost <= `$2.0` per run.

## Cost model

Given:

- `baseline_train_minutes`
- `candidate_train_minutes`
- `candidate_meta_train_minutes`
- `gpu_hour_usd`

The harness computes:

- `extra_training_minutes = max(0, (candidate_train + candidate_meta_train) - baseline_train)`
- `training_overhead_pct = extra_training_minutes / baseline_train * 100`
- `extra_gpu_cost_usd_per_run = extra_training_minutes / 60 * gpu_hour_usd`

## Run commands

Generate report:

```bash
python scripts/maml_feasibility_gate.py --input /path/to/maml_spike.json
```

Enforce decision as a gate (non-zero exit unless `enable_maml`):

```bash
python scripts/maml_feasibility_gate.py --input /path/to/maml_spike.json --enforce-enable
```

Write report to disk:

```bash
python scripts/maml_feasibility_gate.py \
  --input /path/to/maml_spike.json \
  --output /path/to/maml_report.json
```

## Expected AFR-141 output

For each spike run, store:

- input payload,
- generated decision report,
- short interpretation:
  - whether MAML is recommended now,
  - which check failed if deferred,
  - adaptation and cost deltas.

This keeps MAML adoption evidence-backed instead of assumption-driven.
