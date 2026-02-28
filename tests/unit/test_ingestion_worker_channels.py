import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

"""Unit tests for ingestion worker channel ID normalization."""

from data_collectors.ingestion_worker import _normalize_channel_ids


def test_normalize_channel_ids_from_csv() -> None:
    assert _normalize_channel_ids(" C1, C2 ,,C3 ") == ["C1", "C2", "C3"]


def test_normalize_channel_ids_from_list() -> None:
    assert _normalize_channel_ids([" C1 ", None, "", "C2"]) == ["C1", "C2"]
