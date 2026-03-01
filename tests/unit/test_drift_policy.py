import importlib.util
import sys
from pathlib import Path


def _load_drift_policy_module():
    module_path = Path(__file__).resolve().parents[2] / "drift_policy.py"
    spec = importlib.util.spec_from_file_location("drift_policy", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_load_thresholds_prefers_drift_policy_section() -> None:
    drift_policy = _load_drift_policy_module()
    config = {
        "thresholds": {
            "kl_threshold": 0.5,
            "psi_threshold": 0.6,
            "accuracy_min": 0.7,
        },
        "drift_policy": {
            "thresholds": {
                "kl_threshold": 0.11,
                "psi_threshold": 0.22,
                "accuracy_min": 0.83,
            }
        },
    }

    thresholds = drift_policy.load_thresholds(config)

    assert thresholds.kl_threshold == 0.11
    assert thresholds.psi_threshold == 0.22
    assert thresholds.accuracy_min == 0.83


def test_load_alert_event_policies_uses_defaults() -> None:
    drift_policy = _load_drift_policy_module()
    policies = drift_policy.load_alert_event_policies({})

    assert policies["drift_detected"].enabled is True
    assert policies["drift_detected"].severity == "warning"
    assert policies["accuracy_drop"].enabled is True
    assert policies["accuracy_drop"].severity == "critical"
    assert policies["accuracy_drop"].min_drop == 0.10


def test_load_severity_policies_from_config() -> None:
    drift_policy = _load_drift_policy_module()
    policies = drift_policy.load_severity_policies({
        "alerts": {
            "severity": {
                "critical": {"kl_multiplier": 2.5, "psi_multiplier": 2.3, "accuracy_delta": 0.2},
                "warning": {"kl_multiplier": 1.7, "psi_multiplier": 1.6, "accuracy_delta": 0.11},
            }
        }
    })

    assert policies["critical"].kl_multiplier == 2.5
    assert policies["critical"].psi_multiplier == 2.3
    assert policies["critical"].accuracy_delta == 0.2
    assert policies["warning"].kl_multiplier == 1.7
    assert policies["warning"].psi_multiplier == 1.6
    assert policies["warning"].accuracy_delta == 0.11
    assert policies["info"].accuracy_delta == 0.05
