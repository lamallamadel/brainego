# Memory Scoring Profile Evaluation (AFR-46)

This document captures a lightweight internal evaluation for memory scoring defaults.

## Goal

Tune these knobs for profile-specific defaults:
- `cosine_weight`
- `temporal_weight`
- `temporal_decay_factor`

## Profiles

- `balanced`: general purpose baseline
- `history_heavy`: prioritize semantically relevant older memories
- `recent_context_heavy`: prioritize recency for fast conversations

## Evaluation command

```bash
python scripts/evaluate_memory_scoring_profiles.py
```

## Interpretation

The synthetic evaluation set contains two preference cases:
1. **history-preference**: old high-similarity memory should win
2. **recent-preference**: very recent medium-similarity memory should win

Expected outcomes from current defaults:
- `history_heavy` should satisfy history-preference
- `recent_context_heavy` should satisfy recent-preference
- `balanced` should be a compromise profile and may miss one edge case

## Recommended defaults

- Keep `balanced` as default (`0.70/0.30`, decay `0.10`)
- Use `history_heavy` (`0.82/0.18`, decay `0.05`) for long-running assistant threads
- Use `recent_context_heavy` (`0.58/0.42`, decay `0.18`) for rapid back-and-forth chat

## Operational knobs

```bash
export MEMORY_SCORING_PROFILE=balanced
# or history_heavy / recent_context_heavy

# optional explicit overrides
export MEMORY_COSINE_WEIGHT=0.70
export MEMORY_TEMPORAL_WEIGHT=0.30
export MEMORY_TEMPORAL_DECAY_FACTOR=0.10
```
