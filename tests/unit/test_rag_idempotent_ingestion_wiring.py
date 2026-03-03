"""Static wiring checks for S4-4 idempotent ingestion (chunk hash + upsert)."""

from pathlib import Path


SOURCE = Path("rag_service.py").read_text(encoding="utf-8")


def test_rag_service_contains_idempotent_chunk_hash_helpers() -> None:
    assert "def _stable_chunk_hash(" in SOURCE
    assert "def _build_idempotent_point_id(" in SOURCE


def test_upsert_points_uses_deterministic_point_id_and_chunk_hash_payload() -> None:
    assert "chunk_hash = _stable_chunk_hash(text)" in SOURCE
    assert "point_id = _build_idempotent_point_id(" in SOURCE
    assert 'metadata_payload["chunk_hash"] = chunk_hash' in SOURCE
