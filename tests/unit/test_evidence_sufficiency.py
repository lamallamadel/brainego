"""Static tests for Evidence Sufficiency Score integration."""

from pathlib import Path


ESS_SOURCE = Path("evidence_sufficiency.py").read_text(encoding="utf-8")
API_SERVER_SOURCE = Path("api_server.py").read_text(encoding="utf-8")


def test_ess_module_exposes_compute_function() -> None:
    assert "def compute_evidence_sufficiency" in ESS_SOURCE
    assert "return round(max(0.0, min(1.0, ess)), 4)" in ESS_SOURCE


def test_api_server_exposes_ess_thresholds_and_histogram() -> None:
    assert 'ESS_THRESHOLD_LOW = float(os.getenv("ESS_THRESHOLD_LOW", "0.35"))' in API_SERVER_SOURCE
    assert 'ESS_THRESHOLD_HIGH = float(os.getenv("ESS_THRESHOLD_HIGH", "0.60"))' in API_SERVER_SOURCE
    assert '"ess_histogram": self._build_ess_histogram()' in API_SERVER_SOURCE


def test_rag_paths_record_ess_in_retrieval_stats() -> None:
    assert "ess_score = compute_evidence_sufficiency" in API_SERVER_SOURCE
    assert "metrics.record_ess(ess_score)" in API_SERVER_SOURCE
    assert '"ess": ess_score' in API_SERVER_SOURCE
    assert '"ess_threshold_low": ESS_THRESHOLD_LOW' in API_SERVER_SOURCE
    assert '"ess_threshold_high": ESS_THRESHOLD_HIGH' in API_SERVER_SOURCE
