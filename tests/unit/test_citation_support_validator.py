"""Static tests for S1-4 citation contract + anti-fake validator wiring."""

from pathlib import Path


SOURCE = Path("api_server.py").read_text(encoding="utf-8")


def test_citation_contract_path_commit_is_exposed() -> None:
    assert '"citation_contract": "path@commit"' in SOURCE
    assert 'RAG_CITATION_SECTION_HEADER = "Sources (path + commit):"' in SOURCE


def test_support_check_validator_is_wired() -> None:
    assert "def answer_supported_by_context(" in SOURCE
    assert "support_check_failed" in SOURCE
    assert "metrics.record_false_citation_event()" in SOURCE
    assert 'retrieval_stats["response_mode"] = "missing_context"' in SOURCE
