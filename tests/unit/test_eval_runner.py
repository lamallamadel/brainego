# Needs: python-package:pytest
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = REPO_ROOT / "scripts" / "eval_runner.py"
SUITE_PATH = REPO_ROOT / "tests" / "contract" / "fixtures" / "eval_runner_suite.ndjson"
GOOD_OUTPUTS_PATH = REPO_ROOT / "tests" / "contract" / "fixtures" / "eval_runner_outputs_good.ndjson"
BAD_OUTPUTS_PATH = REPO_ROOT / "tests" / "contract" / "fixtures" / "eval_runner_outputs_bad.ndjson"


def _load_runner_module():
    spec = importlib.util.spec_from_file_location("eval_runner", RUNNER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_score_answer_rewards_similarity_and_keywords():
    runner = _load_runner_module()

    expected = "RAG combine recuperation de documents puis generation ancree."
    good_answer = "RAG combine une recuperation de documents puis une generation ancree."
    bad_answer = "Je parle d'un sujet sans rapport."
    keywords = ["recuperation", "documents", "generation"]

    good_score, good_details = runner.score_answer(expected, good_answer, keywords)
    bad_score, bad_details = runner.score_answer(expected, bad_answer, keywords)

    assert good_score > bad_score
    assert good_details["keyword_recall"] > bad_details["keyword_recall"]


def test_set_f1_reports_missing_and_unexpected_values():
    runner = _load_runner_module()

    score, precision, recall, details = runner._set_f1(
        expected=["retriever.search", "llm.generate"],
        observed=["llm.generate", "search.web"],
    )

    assert round(score, 4) == 0.5
    assert round(precision, 4) == 0.5
    assert round(recall, 4) == 0.5
    assert details["missing"] == ["retriever.search"]
    assert details["unexpected"] == ["search.web"]


def test_build_report_tracks_orphan_outputs_and_gate():
    runner = _load_runner_module()

    cases = runner.load_suite(SUITE_PATH)
    outputs = runner.load_outputs(GOOD_OUTPUTS_PATH)
    outputs["orphan-case"] = runner.ModelOutput(answer="unused")

    report = runner.build_report(
        cases,
        outputs,
        thresholds=runner.ScoreThresholds(
            min_answer_score=0.5,
            min_tool_score=0.5,
            min_citation_score=0.5,
            min_overall_score=0.7,
            min_pass_rate=1.0,
            min_mean_overall_score=0.8,
        ),
        weights=runner.ScoreWeights(answer=0.6, tools=0.2, citations=0.2),
        suite_path=SUITE_PATH,
        outputs_path=GOOD_OUTPUTS_PATH,
    )

    assert report["gate"]["passed"] is True
    assert report["summary"]["orphan_outputs"] == ["orphan-case"]
    assert report["summary"]["failed_cases"] == 0


def test_cli_returns_zero_for_good_outputs(tmp_path: Path):
    output_report = tmp_path / "eval_report_good.json"
    result = subprocess.run(
        [
            sys.executable,
            str(RUNNER_PATH),
            "--suite",
            str(SUITE_PATH),
            "--outputs",
            str(GOOD_OUTPUTS_PATH),
            "--output",
            str(output_report),
            "--min-pass-rate",
            "1.0",
            "--min-mean-overall-score",
            "0.85",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    report = json.loads(output_report.read_text(encoding="utf-8"))
    assert report["gate"]["passed"] is True
    assert report["summary"]["failed_cases"] == 0


def test_cli_returns_non_zero_for_bad_outputs(tmp_path: Path):
    output_report = tmp_path / "eval_report_bad.json"
    result = subprocess.run(
        [
            sys.executable,
            str(RUNNER_PATH),
            "--suite",
            str(SUITE_PATH),
            "--outputs",
            str(BAD_OUTPUTS_PATH),
            "--output",
            str(output_report),
            "--min-pass-rate",
            "1.0",
            "--min-mean-overall-score",
            "0.85",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    report = json.loads(output_report.read_text(encoding="utf-8"))
    assert report["gate"]["passed"] is False
    assert report["summary"]["failed_cases"] >= 1
