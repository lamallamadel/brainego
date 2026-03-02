import importlib.util
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "ewc_feasibility_gate.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("ewc_feasibility_gate", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _base_payload() -> dict:
    return {
        "baseline": {
            "label": "no_ewc",
            "per_project_retention": [
                {"project": "project-a", "before_score": 0.82, "after_score": 0.74},
                {"project": "project-b", "before_score": 0.79, "after_score": 0.72},
                {"project": "project-c", "before_score": 0.76, "after_score": 0.71},
            ],
            "new_project_score": 0.77,
            "train_minutes": 40.0,
        },
        "candidate": {
            "label": "with_ewc",
            "per_project_retention": [
                {"project": "project-a", "before_score": 0.82, "after_score": 0.80},
                {"project": "project-b", "before_score": 0.79, "after_score": 0.78},
                {"project": "project-c", "before_score": 0.76, "after_score": 0.75},
            ],
            "new_project_score": 0.765,
            "train_minutes": 50.0,
            "fisher_minutes": 4.0,
            "fisher_size_gb": 1.0,
        },
        "cost_profile": {
            "gpu_hour_usd": 2.0,
            "storage_gb_month_usd": 0.023,
        },
        "thresholds": {
            "min_projects": 3,
            "trigger_mean_forgetting_pp": 3.0,
            "trigger_max_forgetting_pp": 7.0,
            "trigger_project_forgetting_pp": 5.0,
            "trigger_project_count": 2,
            "min_mean_reduction_pp": 1.5,
            "min_relative_reduction": 0.25,
            "max_new_project_regression_pp": 1.0,
            "max_training_overhead_pct": 40.0,
            "max_extra_gpu_cost_usd_per_run": 1.5,
            "max_extra_storage_gb": 2.0,
        },
    }


def test_gate_recommends_enabling_ewc_when_forgetting_is_material_and_cost_is_acceptable():
    module = _load_module()
    report = module.evaluate_feasibility(_base_payload())

    assert report["decision"] == "enable_ewc"
    assert report["ewc_needed"] is True
    assert report["checks"]["forgetting_triggered"] is True
    assert report["checks"]["effectiveness_ok"] is True
    assert report["checks"]["cost_ok"] is True
    assert report["checks"]["plasticity_ok"] is True


def test_gate_defers_ewc_when_baseline_forgetting_is_low():
    module = _load_module()
    payload = _base_payload()
    payload["baseline"]["per_project_retention"] = [
        {"project": "project-a", "before_score": 0.82, "after_score": 0.81},
        {"project": "project-b", "before_score": 0.79, "after_score": 0.78},
        {"project": "project-c", "before_score": 0.76, "after_score": 0.75},
    ]
    payload["candidate"]["per_project_retention"] = payload["baseline"]["per_project_retention"]

    report = module.evaluate_feasibility(payload)

    assert report["decision"] == "defer_ewc_low_forgetting"
    assert report["ewc_needed"] is False
    assert report["checks"]["forgetting_triggered"] is False


def test_gate_defers_ewc_when_cost_budget_is_exceeded():
    module = _load_module()
    payload = _base_payload()
    payload["candidate"]["train_minutes"] = 70.0
    payload["candidate"]["fisher_minutes"] = 15.0
    payload["cost_profile"]["gpu_hour_usd"] = 4.0

    report = module.evaluate_feasibility(payload)

    assert report["decision"] == "defer_ewc_cost_too_high"
    assert report["ewc_needed"] is False
    assert report["checks"]["cost_ok"] is False
    assert report["checks"]["effectiveness_ok"] is True


def test_gate_collects_more_evidence_when_too_few_common_projects():
    module = _load_module()
    payload = _base_payload()
    payload["candidate"]["per_project_retention"] = [
        {"project": "project-a", "before_score": 0.82, "after_score": 0.80},
    ]
    report = module.evaluate_feasibility(payload)

    assert report["decision"] == "collect_more_evidence"
    assert report["ewc_needed"] is False
    assert report["checks"]["enough_projects"] is False


def test_cli_enforce_enable_returns_non_zero_when_decision_is_not_enable(tmp_path):
    payload = _base_payload()
    payload["baseline"]["per_project_retention"] = [
        {"project": "project-a", "before_score": 0.82, "after_score": 0.81},
        {"project": "project-b", "before_score": 0.79, "after_score": 0.78},
        {"project": "project-c", "before_score": 0.76, "after_score": 0.75},
    ]
    payload["candidate"]["per_project_retention"] = payload["baseline"]["per_project_retention"]

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
    assert '"decision": "defer_ewc_low_forgetting"' in result.stdout


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
    assert '"decision": "enable_ewc"' in result.stdout
