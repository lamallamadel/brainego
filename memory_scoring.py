#!/usr/bin/env python3
"""Utilities for ranking memory retrieval results."""

from __future__ import annotations

import math
from typing import Tuple


def normalize_weights(similarity_weight: float, recency_weight: float) -> Tuple[float, float]:
    """Normalize similarity and recency weights so they sum to 1.0."""
    total = similarity_weight + recency_weight
    if total <= 0:
        return 0.7, 0.3
    return similarity_weight / total, recency_weight / total


def exponential_recency_score(age_hours: float, temporal_decay_factor: float) -> float:
    """Compute recency score with exponential decay over elapsed hours."""
    if age_hours <= 0:
        return 1.0
    return math.exp(-temporal_decay_factor * age_hours / 24)


def combined_memory_score(
    cosine_similarity: float,
    age_hours: float,
    temporal_decay_factor: float,
    similarity_weight: float,
    recency_weight: float,
) -> Tuple[float, float, float]:
    """Compute final ranking score from cosine similarity and recency decay."""
    similarity_weight, recency_weight = normalize_weights(similarity_weight, recency_weight)
    recency_score = exponential_recency_score(age_hours, temporal_decay_factor)
    combined_score = (cosine_similarity * similarity_weight) + (recency_score * recency_weight)
    return combined_score, cosine_similarity, recency_score
