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


def test_policy_and_event_alerts_from_config_data() -> None:
    drift_policy = _load_drift_policy_module()
    data = {
        "thresholds": {
            "kl_threshold": 0.9,
            "psi_threshold": 0.8,
            "accuracy_min": 0.7,
        },
        "drift_policy": {
            "thresholds": {
                "kl_threshold": 0.12,
                "psi_threshold": 0.19,
                "accuracy_min": 0.81,
            }
        },
        "alerts": {
            "events": {
                "drift_detected": {
                    "enabled": True,
                    "severity": "warning",
                },
                "accuracy_drop": {
                    "enabled": True,
                    "severity": "critical",
                    "min_drop": 0.07,
                },
            }
        },
    }

    thresholds = drift_policy.load_thresholds(data)
    policies = drift_policy.load_alert_event_policies(data)

    assert thresholds.kl_threshold == 0.12
    assert thresholds.psi_threshold == 0.19
    assert thresholds.accuracy_min == 0.81
    assert policies["drift_detected"].severity == "warning"
    assert policies["accuracy_drop"].severity == "critical"
    assert policies["accuracy_drop"].min_drop == 0.07
