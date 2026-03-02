from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
GOLDEN_SET_PATH = REPO_ROOT / "tests" / "contract" / "fixtures" / "repo_rag_golden_set.ndjson"
DEMO_REPO_INDEX_PATH = REPO_ROOT / "scripts" / "pilot" / "demo_repo_index.py"


def _load_fixture() -> dict:
    return json.loads(GOLDEN_SET_PATH.read_text(encoding="utf-8"))


def _load_default_index_files() -> set[str]:
    spec = importlib.util.spec_from_file_location("demo_repo_index", DEMO_REPO_INDEX_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return set(module.DEFAULT_FILES)


def test_repo_rag_golden_set_contains_exactly_20_cases() -> None:
    suite = _load_fixture()
    cases = suite["cases"]

    assert len(cases) == 20
    assert suite["metadata"]["total_cases"] == 20


def test_repo_rag_golden_set_has_required_case_fields() -> None:
    suite = _load_fixture()
    ids = set()

    for case in suite["cases"]:
        case_id = case["id"]
        assert case_id not in ids
        ids.add(case_id)

        assert isinstance(case["question"], str) and case["question"].strip()
        assert isinstance(case["expected_sources"], list) and case["expected_sources"]
        assert isinstance(case["expected_answer_keywords"], list) and case["expected_answer_keywords"]

        assert case["citation_required"] is True
        assert case["citation_format"] == "[source:<path>]"
        assert isinstance(case["citation_anchors"], list) and case["citation_anchors"]


def test_repo_rag_golden_set_sources_align_with_pilot_index_defaults() -> None:
    suite = _load_fixture()
    expected_default_sources = _load_default_index_files()

    metadata_sources = set(suite["metadata"]["indexed_source_set"])
    assert metadata_sources == expected_default_sources

    covered_sources: set[str] = set()
    for case in suite["cases"]:
        for source in case["expected_sources"]:
            assert source in expected_default_sources
            covered_sources.add(source)

    assert covered_sources == expected_default_sources


def test_repo_rag_golden_set_declares_eval_axes() -> None:
    suite = _load_fixture()
    axes = set(suite["metadata"]["evaluation_axes"])
    assert "retrieval_relevance" in axes
    assert "citation_correctness" in axes
