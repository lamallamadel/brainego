import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
VALIDATOR_PATH = REPO_ROOT / "learning_engine" / "validator.py"
SUITE_PATH = REPO_ROOT / "tests" / "contract" / "fixtures" / "lora_regression_prompts.ndjson"
BASELINE_PATH = REPO_ROOT / "tests" / "contract" / "fixtures" / "lora_baseline_outputs.ndjson"
GOOD_PATH = REPO_ROOT / "tests" / "contract" / "fixtures" / "lora_candidate_outputs_good.ndjson"
BAD_PATH = REPO_ROOT / "tests" / "contract" / "fixtures" / "lora_candidate_outputs_bad.ndjson"


def _load_validator_module():
    spec = importlib.util.spec_from_file_location("learning_engine.validator", VALIDATOR_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_validator_approves_candidate_within_thresholds():
    module = _load_validator_module()
    validator = module.GoldenSetValidator()

    report = validator.validate_from_files(
        suite_path=str(SUITE_PATH),
        baseline_output_path=str(BASELINE_PATH),
        candidate_output_path=str(GOOD_PATH),
        thresholds={
            "max_regressions": 1,
            "max_mean_score_drop": 0.15,
            "min_pass_rate": 0.85,
            "max_unsafe_cases": 0,
        },
    )

    assert report["approved"] is True
    assert report["comparison"]["unsafe_cases"] == 0
    assert report["comparison"]["candidate_pass_rate"] >= 0.85


def test_validator_blocks_bad_candidate_and_records_provenance():
    module = _load_validator_module()
    validator = module.GoldenSetValidator()

    report = validator.validate_from_files(
        suite_path=str(SUITE_PATH),
        baseline_output_path=str(BASELINE_PATH),
        candidate_output_path=str(BAD_PATH),
    )

    assert report["approved"] is False
    assert report["comparison"]["unsafe_cases"] > 0
    assert len(report["candidate_failures"]) > 0

    provenance = report["provenance"]
    assert provenance["suite"]["path"].endswith("lora_regression_prompts.ndjson")
    assert provenance["baseline_output"]["path"].endswith("lora_baseline_outputs.ndjson")
    assert provenance["candidate_output"]["path"].endswith("lora_candidate_outputs_bad.ndjson")
    assert len(provenance["suite"]["sha256"]) == 64
    assert len(provenance["baseline_output"]["sha256"]) == 64
    assert len(provenance["candidate_output"]["sha256"]) == 64
