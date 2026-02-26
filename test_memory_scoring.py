#!/usr/bin/env python3
"""Tests for memory scoring utilities."""

import math
import unittest

from memory_scoring import (
    combined_memory_score,
    exponential_recency_score,
    normalize_weights,
)


class MemoryScoringTests(unittest.TestCase):
    """Validate similarity + recency score behavior."""

    def test_normalize_weights(self) -> None:
        """Weights are normalized to a sum of one."""
        similarity_weight, recency_weight = normalize_weights(7, 3)
        self.assertAlmostEqual(similarity_weight, 0.7)
        self.assertAlmostEqual(recency_weight, 0.3)

    def test_normalize_weights_uses_defaults_for_invalid_input(self) -> None:
        """Invalid totals should fall back to default weighting."""
        similarity_weight, recency_weight = normalize_weights(0, 0)
        self.assertAlmostEqual(similarity_weight, 0.7)
        self.assertAlmostEqual(recency_weight, 0.3)

    def test_exponential_recency_score_decays_over_time(self) -> None:
        """Recency score should decline as age increases."""
        score_now = exponential_recency_score(age_hours=0, temporal_decay_factor=0.1)
        score_day_old = exponential_recency_score(age_hours=24, temporal_decay_factor=0.1)
        self.assertEqual(score_now, 1.0)
        self.assertLess(score_day_old, score_now)

    def test_combined_score_blends_similarity_and_recency(self) -> None:
        """Combined score should use both cosine and recency components."""
        combined, cosine_score, recency = combined_memory_score(
            cosine_similarity=0.8,
            age_hours=24,
            temporal_decay_factor=0.1,
            similarity_weight=0.7,
            recency_weight=0.3,
        )
        expected_recency = math.exp(-0.1)
        expected_combined = (0.8 * 0.7) + (expected_recency * 0.3)

        self.assertAlmostEqual(cosine_score, 0.8)
        self.assertAlmostEqual(recency, expected_recency)
        self.assertAlmostEqual(combined, expected_combined)


if __name__ == "__main__":
    unittest.main()
