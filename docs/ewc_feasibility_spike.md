# AFR-140 — EWC feasibility spike (evidence-gated)

## Objective

Determine whether Elastic Weight Consolidation (EWC) should be enabled for multi-project continual learning, based on measurable forgetting and explicit cost constraints.

This spike provides:

1. a reproducible evidence gate (`scripts/ewc_feasibility_gate.py`),
2. explicit success criteria for enabling EWC,
3. an operating cost model (training overhead + GPU + storage).

## Why an evidence gate is needed

EWC adds complexity and runtime/storage overhead. It should only be enabled when:

- forgetting is materially harmful across projects,
- EWC actually reduces that forgetting,
- adaptation to the newest project remains acceptable,
- cost increase is within budget.

## Input contract

The harness expects a JSON payload with:

- `baseline`: usually a no-EWC run,
- `candidate`: usually a with-EWC run,
- `cost_profile`: GPU + storage assumptions,
- `thresholds`: gate thresholds.

Minimal example:

```json
{
  "baseline": {
    "label": "no_ewc",
    "per_project_retention": [
      {"project": "project-a", "before_score": 0.82, "after_score": 0.74},
      {"project": "project-b", "before_score": 0.79, "after_score": 0.72},
      {"project": "project-c", "before_score": 0.76, "after_score": 0.71}
    ],
    "new_project_score": 0.77,
    "train_minutes": 40.0
  },
  "candidate": {
    "label": "with_ewc",
    "per_project_retention": [
      {"project": "project-a", "before_score": 0.82, "after_score": 0.80},
      {"project": "project-b", "before_score": 0.79, "after_score": 0.78},
      {"project": "project-c", "before_score": 0.76, "after_score": 0.75}
    ],
    "new_project_score": 0.765,
    "train_minutes": 50.0,
    "fisher_minutes": 4.0,
    "fisher_size_gb": 1.0
  }
}
```

Notes:

- Scores can be in `[0,1]` ratio form (auto-converted to percentage points),
- or directly in percentage points.

## Gate logic

The harness computes:

- baseline forgetting (`mean_forgetting_pp`, `max_forgetting_pp`, projects above threshold),
- candidate forgetting and reduction vs baseline,
- new-project regression penalty,
- incremental cost:
  - `extra_training_minutes`,
  - `training_overhead_pct`,
  - `extra_gpu_cost_usd_per_run`,
  - `extra_storage_gb` and monthly storage cost.

Decision outcomes:

- `enable_ewc`
- `defer_ewc_low_forgetting`
- `defer_ewc_low_effect`
- `defer_ewc_plasticity_penalty`
- `defer_ewc_cost_too_high`
- `collect_more_evidence`

## Success criteria for enabling EWC

Default thresholds (overridable in payload):

- at least `3` common projects,
- forgetting trigger reached on baseline:
  - mean forgetting >= `3.0pp`, or
  - max forgetting >= `7.0pp`, or
  - at least `2` projects with forgetting >= `5.0pp`,
- EWC effectiveness:
  - mean forgetting reduction >= `1.5pp`,
  - relative reduction >= `25%`,
- plasticity guard:
  - new-project regression <= `1.0pp`,
- cost guard:
  - training overhead <= `40%`,
  - extra GPU cost <= `$1.5` per run,
  - extra storage <= `2.0 GB`.

## Cost model

Given:

- `baseline_train_minutes`
- `candidate_train_minutes`
- `candidate_fisher_minutes`
- `gpu_hour_usd`
- `storage_gb_month_usd`

The harness computes:

- `extra_training_minutes = max(0, (candidate_train + candidate_fisher) - baseline_train)`
- `training_overhead_pct = extra_training_minutes / baseline_train * 100`
- `extra_gpu_cost_usd_per_run = extra_training_minutes / 60 * gpu_hour_usd`
- `extra_storage_monthly_cost_usd = extra_storage_gb * storage_gb_month_usd`

## Run commands

Generate report:

```bash
python scripts/ewc_feasibility_gate.py --input /path/to/ewc_spike.json
```

Enforce decision as a gate (non-zero exit unless `enable_ewc`):

```bash
python scripts/ewc_feasibility_gate.py --input /path/to/ewc_spike.json --enforce-enable
```

Write report to disk:

```bash
python scripts/ewc_feasibility_gate.py \
  --input /path/to/ewc_spike.json \
  --output /path/to/ewc_report.json
```

## Expected AFR-140 output

For each spike run, store:

- input payload,
- generated decision report,
- short interpretation:
  - whether EWC is needed now,
  - which check failed if deferred,
  - cost delta and risk notes.

This converts EWC adoption from assumption to evidence-backed decision.
