"""Drift policy helpers.

This module keeps policy parsing and event evaluation lightweight so it can be
unit-tested without importing the full drift monitor runtime dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class DriftPolicyThresholds:
    """Primary thresholds used to decide drift state."""

    kl_threshold: float = 0.1
    psi_threshold: float = 0.2
    accuracy_min: float = 0.75


@dataclass(frozen=True)
class DriftAlertEventPolicy:
    """Slack alert policy for a drift-related event."""

    enabled: bool = True
    severity: str = "warning"
    min_drop: float = 0.10


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def load_thresholds(config: Dict[str, Any]) -> DriftPolicyThresholds:
    """Load thresholds from `drift_policy.thresholds` with legacy fallback."""

    drift_policy = _as_dict(config.get("drift_policy"))
    policy_thresholds = _as_dict(drift_policy.get("thresholds"))
    legacy_thresholds = _as_dict(config.get("thresholds"))

    return DriftPolicyThresholds(
        kl_threshold=policy_thresholds.get(
            "kl_threshold", legacy_thresholds.get("kl_threshold", 0.1)
        ),
        psi_threshold=policy_thresholds.get(
            "psi_threshold", legacy_thresholds.get("psi_threshold", 0.2)
        ),
        accuracy_min=policy_thresholds.get(
            "accuracy_min", legacy_thresholds.get("accuracy_min", 0.75)
        ),
    )


def load_alert_event_policies(config: Dict[str, Any]) -> Dict[str, DriftAlertEventPolicy]:
    """Load event alert policies from YAML config with safe defaults."""

    events_config = _as_dict(_as_dict(config.get("alerts")).get("events"))

    drift_detected_cfg = _as_dict(events_config.get("drift_detected"))
    accuracy_drop_cfg = _as_dict(events_config.get("accuracy_drop"))

    return {
        "drift_detected": DriftAlertEventPolicy(
            enabled=drift_detected_cfg.get("enabled", True),
            severity=drift_detected_cfg.get("severity", "warning"),
            min_drop=0.0,
        ),
        "accuracy_drop": DriftAlertEventPolicy(
            enabled=accuracy_drop_cfg.get("enabled", True),
            severity=accuracy_drop_cfg.get("severity", "critical"),
            min_drop=accuracy_drop_cfg.get("min_drop", 0.10),
        ),
    }



@dataclass(frozen=True)
class DriftSeverityPolicy:
    """Severity multipliers used by drift_detected classification."""

    kl_multiplier: float = 1.0
    psi_multiplier: float = 1.0
    accuracy_delta: float = 0.05


def load_severity_policies(config: Dict[str, Any]) -> Dict[str, DriftSeverityPolicy]:
    """Load severity policy table from `alerts.severity` with defaults."""

    severity_cfg = _as_dict(_as_dict(config.get("alerts")).get("severity"))

    def _one(name: str, defaults: DriftSeverityPolicy) -> DriftSeverityPolicy:
        data = _as_dict(severity_cfg.get(name))
        return DriftSeverityPolicy(
            kl_multiplier=data.get("kl_multiplier", defaults.kl_multiplier),
            psi_multiplier=data.get("psi_multiplier", defaults.psi_multiplier),
            accuracy_delta=data.get("accuracy_delta", defaults.accuracy_delta),
        )

    return {
        "critical": _one("critical", DriftSeverityPolicy(kl_multiplier=2.0, psi_multiplier=2.0, accuracy_delta=0.15)),
        "warning": _one("warning", DriftSeverityPolicy(kl_multiplier=1.5, psi_multiplier=1.5, accuracy_delta=0.10)),
        "info": _one("info", DriftSeverityPolicy(kl_multiplier=1.0, psi_multiplier=1.0, accuracy_delta=0.05)),
    }
