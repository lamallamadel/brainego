# LoRA Non-Regression Gate

This project now includes an automated non-regression harness for LoRA promotion decisions.

## Critical prompt suite

The prompt suite lives in:

- `tests/contract/fixtures/lora_regression_prompts.ndjson`

It contains a small but high-impact set of checks covering:

- Safety refusal behavior
- Secret leakage refusal
- RAG source-grounded wording
- PII masking
- Instruction-following format
- Hallucination guardrails

## Run the gate

Evaluate a candidate LoRA against baseline outputs:

```bash
python scripts/lora_non_regression.py \
  --suite tests/contract/fixtures/lora_regression_prompts.ndjson \
  --baseline-output tests/contract/fixtures/lora_baseline_outputs.ndjson \
  --candidate-output /path/to/candidate_outputs.json \
  --max-regressions 1 \
  --max-mean-score-drop 0.15 \
  --min-pass-rate 0.85
```

### Output contract

The harness prints a JSON report with:

- `approved`: `true`/`false`
- `comparison`: pass-rate and score deltas
- `candidate_failures`: case-level failures

The process exits with:

- `0` when promotion is allowed
- `1` when promotion must be blocked

Use this exit code in CI/CD promotion pipelines.

## Make target

A default run is available with:

```bash
make test-lora-regression
```
