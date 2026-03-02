import importlib.util
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "maml_feasibility_gate.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("maml_feasibility_gate", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _base_payload() -> dict:
    return {
        "baseline": {
            "label": "lora_only",
            "per_project_adaptation": [
                {
                    "project": "project-a",
                    "steps_to_target": 8,
                    "target_accuracy": 0.80,
                    "final_accuracy": 0.81,
                },
                {
                    "project": "project-b",
                    "steps_to_target": 7,
                    "target_accuracy": 0.78,
                    "final_accuracy": 0.79,
                },
                {
                    "project": "project-c",
                    "steps_to_target": 6,
                    "target_accuracy": 0.76,
                    "final_accuracy": 0.77,
                },
            ],
            "train_minutes": 45.0,
        },
        "candidate": {
            "label": "lora_plus_maml",
            "per_project_adaptation": [
                {
                    "project": "project-a",
                    "steps_to_target": 5,
                    "target_accuracy": 0.80,
                    "final_accuracy": 0.805,
                },
                {
                    "project": "project-b",
                    "steps_to_target": 4,
                    "target_accuracy": 0.78,
                    "final_accuracy": 0.785,
                },
                {
                    "project": "project-c",
                    "steps_to_target": 4,
                    "target_accuracy": 0.76,
                    "final_accuracy": 0.765,
                },
            ],
            "train_minutes": 55.0,
            "meta_train_minutes": 8.0,
        },
        "cost_profile": {
            "gpu_hour_usd": 2.0,
        },
        "thresholds": {
            "min_projects": 3,
            "trigger_mean_steps": 4.0,
            "trigger_max_steps": 7.0,
            "min_mean_step_reduction": 1.5,
            "min_relative_step_reduction": 0.25,
            "max_mean_accuracy_regression_pp": 1.0,
            "max_training_overhead_pct": 50.0,
            "max_extra_gpu_cost_usd_per_run": 2.0,
        },
    }


def test_gate_recommends_enabling_maml_when_adaptation_is_slow_and_maml_is_effective():
    module = _load_module()
    report = module.evaluate_feasibility(_base_payload())

    assert report["decision"] == "enable_maml"
    assert report["maml_recommended"] is True
    assert report["checks"]["adaptation_triggered"] is True
    assert report["checks"]["effectiveness_ok"] is True
    assert report["checks"]["cost_ok"] is True
    assert report["checks"]["accuracy_ok"] is True


def test_gate_defers_maml_when_lora_only_is_already_fast_enough():
    module = _load_module()
    payload = _base_payload()
    payload["baseline"]["per_project_adaptation"] = [
        {"project": "project-a", "steps_to_target": 3, "target_accuracy": 0.80, "final_accuracy": 0.81},
        {"project": "project-b", "steps_to_target": 3, "target_accuracy": 0.78, "final_accuracy": 0.79},
        {"project": "project-c", "steps_to_target": 3, "target_accuracy": 0.76, "final_accuracy": 0.77},
    ]

    report = module.evaluate_feasibility(payload)

    assert report["decision"] == "defer_maml_fast_enough"
    assert report["maml_recommended"] is False
    assert report["checks"]["adaptation_triggered"] is False


def test_gate_defers_maml_when_effect_size_is_too_small():
    module = _load_module()
    payload = _base_payload()
    payload["candidate"]["per_project_adaptation"] = [
        {"project": "project-a", "steps_to_target": 7.5, "target_accuracy": 0.80, "final_accuracy": 0.805},
        {"project": "project-b", "steps_to_target": 6.5, "target_accuracy": 0.78, "final_accuracy": 0.785},
        {"project": "project-c", "steps_to_target": 5.5, "target_accuracy": 0.76, "final_accuracy": 0.765},
    ]

    report = module.evaluate_feasibility(payload)

    assert report["decision"] == "defer_maml_low_effect"
    assert report["maml_recommended"] is False
    assert report["checks"]["effectiveness_ok"] is False


def test_gate_collects_more_evidence_when_too_few_common_projects():
    module = _load_module()
    payload = _base_payload()
    payload["candidate"]["per_project_adaptation"] = [
        {"project": "project-a", "steps_to_target": 5, "target_accuracy": 0.80, "final_accuracy": 0.805},
    ]

    report = module.evaluate_feasibility(payload)

    assert report["decision"] == "collect_more_evidence"
    assert report["maml_recommended"] is False
    assert report["checks"]["enough_projects"] is False


def test_cli_enforce_enable_returns_non_zero_when_decision_is_not_enable(tmp_path):
    payload = _base_payload()
    payload["baseline"]["per_project_adaptation"] = [
        {"project": "project-a", "steps_to_target": 3, "target_accuracy": 0.80, "final_accuracy": 0.81},
        {"project": "project-b", "steps_to_target": 3, "target_accuracy": 0.78, "final_accuracy": 0.79},
        {"project": "project-c", "steps_to_target": 3, "target_accuracy": 0.76, "final_accuracy": 0.77},
    ]

    input_path = tmp_path / "spike.json"
    input_path.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--input",
            str(input_path),
            "--enforce-enable",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert '"decision": "defer_maml_fast_enough"' in result.stdout


def test_cli_enforce_enable_returns_zero_when_decision_is_enable(tmp_path):
    input_path = tmp_path / "spike.json"
    input_path.write_text(json.dumps(_base_payload()), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--input",
            str(input_path),
            "--enforce-enable",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert '"decision": "enable_maml"' in result.stdout
