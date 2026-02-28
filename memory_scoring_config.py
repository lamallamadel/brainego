#!/usr/bin/env python3
"""Memory scoring profile configuration helpers."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict

logger = logging.getLogger(__name__)

DEFAULT_PROFILE_NAME = "balanced"

SCORING_PROFILES: Dict[str, Dict[str, float]] = {
    "balanced": {
        "temporal_decay_factor": 0.10,
        "cosine_weight": 0.70,
        "temporal_weight": 0.30,
    },
    "history_heavy": {
        "temporal_decay_factor": 0.05,
        "cosine_weight": 0.82,
        "temporal_weight": 0.18,
    },
    "recent_context_heavy": {
        "temporal_decay_factor": 0.18,
        "cosine_weight": 0.58,
        "temporal_weight": 0.42,
    },
}


def _to_float(value: Any, fallback: float) -> float:
    """Parse float values defensively with fallback."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def load_memory_scoring_config() -> Dict[str, float]:
    """Resolve memory scoring knobs from selected profile + env overrides."""
    profile_name = os.getenv("MEMORY_SCORING_PROFILE", DEFAULT_PROFILE_NAME)
    if profile_name not in SCORING_PROFILES:
        logger.warning(
            "Unknown MEMORY_SCORING_PROFILE='%s'; falling back to %s",
            profile_name,
            DEFAULT_PROFILE_NAME,
        )
        profile_name = DEFAULT_PROFILE_NAME

    config = dict(SCORING_PROFILES[profile_name])

    # env overrides (highest precedence)
    config["temporal_decay_factor"] = _to_float(
        os.getenv("MEMORY_TEMPORAL_DECAY_FACTOR"), config["temporal_decay_factor"]
    )
    config["cosine_weight"] = _to_float(
        os.getenv("MEMORY_COSINE_WEIGHT"), config["cosine_weight"]
    )
    config["temporal_weight"] = _to_float(
        os.getenv("MEMORY_TEMPORAL_WEIGHT"), config["temporal_weight"]
    )

    return config
