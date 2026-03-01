import importlib.util
import subprocess
import sys
from pathlib import Path



REPO_ROOT = Path(__file__).resolve().parents[2]
HARNESS_PATH = REPO_ROOT / "scripts" / "lora_non_regression.py"
SUITE_PATH = REPO_ROOT / "tests" / "contract" / "fixtures" / "lora_regression_prompts.ndjson"
BASELINE_PATH = REPO_ROOT / "tests" / "contract" / "fixtures" / "lora_baseline_outputs.ndjson"
GOOD_PATH = REPO_ROOT / "tests" / "contract" / "fixtures" / "lora_candidate_outputs_good.ndjson"
BAD_PATH = REPO_ROOT / "tests" / "contract" / "fixtures" / "lora_candidate_outputs_bad.ndjson"


def _load_harness_module():
    spec = importlib.util.spec_from_file_location("lora_non_regression", HARNESS_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_compare_with_baseline_passes_for_good_candidate():
    harness = _load_harness_module()

    suite = harness.load_prompt_suite(SUITE_PATH)
    baseline = harness.evaluate_outputs(suite, harness._load_outputs(BASELINE_PATH))
    candidate = harness.evaluate_outputs(suite, harness._load_outputs(GOOD_PATH))

    approved, comparison = harness.compare_with_baseline(
        baseline,
        candidate,
        max_regressions=1,
        max_mean_score_drop=0.15,
        min_pass_rate=0.85,
    )

    assert approved is True
    assert comparison["regressed_cases"] <= 1


def test_cli_returns_non_zero_when_candidate_regresses():
    result = subprocess.run(
        [
            sys.executable,
            str(HARNESS_PATH),
            "--suite",
            str(SUITE_PATH),
            "--baseline-output",
            str(BASELINE_PATH),
            "--candidate-output",
            str(BAD_PATH),
            "--max-regressions",
            "1",
            "--max-mean-score-drop",
            "0.15",
            "--min-pass-rate",
            "0.85",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert '"approved": false' in result.stdout


def test_cli_returns_zero_for_candidate_within_thresholds():
    result = subprocess.run(
        [
            sys.executable,
            str(HARNESS_PATH),
            "--suite",
            str(SUITE_PATH),
            "--baseline-output",
            str(BASELINE_PATH),
            "--candidate-output",
            str(GOOD_PATH),
            "--max-regressions",
            "1",
            "--max-mean-score-drop",
            "0.15",
            "--min-pass-rate",
            "0.85",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert '"approved": true' in result.stdout
