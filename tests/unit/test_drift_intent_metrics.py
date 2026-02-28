"""Unit tests for intent PSI drift utilities."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from drift_intent_metrics import (
    calculate_population_stability_index,
    get_intent_distribution,
)


def test_get_intent_distribution_uses_known_categories_and_unknown_bucket() -> None:
    feedback = [
        {"intent": "code"},
        {"intent": "Code"},
        {"intent": "general"},
        {"intent": "other"},
        {"intent": None},
        {},
    ]

    distribution = get_intent_distribution(
        feedback,
        categories=["code", "reasoning", "general"],
    )

    assert distribution == {
        "code": 2,
        "reasoning": 0,
        "general": 1,
        "unknown": 3,
    }


def test_calculate_population_stability_index_is_zero_for_identical_distributions() -> None:
    reference = {"code": 40, "reasoning": 30, "general": 30}
    current = {"code": 40, "reasoning": 30, "general": 30}

    psi = calculate_population_stability_index(reference, current)

    assert psi == 0.0


def test_calculate_population_stability_index_detects_distribution_shift() -> None:
    reference = {"code": 70, "reasoning": 20, "general": 10}
    current = {"code": 20, "reasoning": 30, "general": 50}

    psi = calculate_population_stability_index(reference, current)

    assert psi > 0.2
