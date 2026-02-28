#!/usr/bin/env python3
"""Small internal evaluation harness for memory scoring profiles."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from memory_scoring import combined_memory_score


@dataclass(frozen=True)
class CandidateMemory:
    label: str
    cosine_similarity: float
    age_hours: float


@dataclass(frozen=True)
class EvalCase:
    name: str
    expected_top: str
    candidates: List[CandidateMemory]


PROFILES: Dict[str, Dict[str, float]] = {
    "balanced": {"cosine_weight": 0.70, "temporal_weight": 0.30, "temporal_decay_factor": 0.10},
    "history_heavy": {"cosine_weight": 0.82, "temporal_weight": 0.18, "temporal_decay_factor": 0.05},
    "recent_context_heavy": {"cosine_weight": 0.58, "temporal_weight": 0.42, "temporal_decay_factor": 0.18},
}

EVAL_SET: List[EvalCase] = [
    EvalCase(
        name="history-preference",
        expected_top="old-but-high-similarity",
        candidates=[
            CandidateMemory("old-but-high-similarity", cosine_similarity=0.92, age_hours=24 * 14),
            CandidateMemory("newer-lower-similarity", cosine_similarity=0.74, age_hours=2),
        ],
    ),
    EvalCase(
        name="recent-preference",
        expected_top="very-recent-medium-similarity",
        candidates=[
            CandidateMemory("stale-high-similarity", cosine_similarity=0.89, age_hours=24 * 10),
            CandidateMemory("very-recent-medium-similarity", cosine_similarity=0.78, age_hours=0.5),
        ],
    ),
]


def rank_case(case: EvalCase, profile: Dict[str, float]) -> str:
    scored = []
    for candidate in case.candidates:
        combined, _, _ = combined_memory_score(
            cosine_similarity=candidate.cosine_similarity,
            age_hours=candidate.age_hours,
            temporal_decay_factor=profile["temporal_decay_factor"],
            similarity_weight=profile["cosine_weight"],
            recency_weight=profile["temporal_weight"],
        )
        scored.append((combined, candidate.label))

    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1]


def main() -> int:
    print("Memory scoring profile evaluation\n")
    for profile_name, profile in PROFILES.items():
        passed = 0
        print(f"Profile: {profile_name}")
        for case in EVAL_SET:
            top = rank_case(case, profile)
            ok = top == case.expected_top
            passed += int(ok)
            marker = "PASS" if ok else "MISS"
            print(f"  - {case.name}: {marker} (top={top}, expected={case.expected_top})")
        print(f"  Summary: {passed}/{len(EVAL_SET)} matched expected preferences\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
