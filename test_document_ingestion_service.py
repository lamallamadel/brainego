#!/usr/bin/env python3
"""Tests for document ingestion and chunking service."""

import pytest

from document_ingestion_service import DocumentIngestionService


def test_ingest_text_creates_overlapping_chunks():
    """Ensure text is chunked with expected overlap and metadata."""
    service = DocumentIngestionService(chunk_size=10, chunk_overlap=2)
    text = "abcdefghijklmnopqrstuvwxyz"

    result = service.ingest_text(
        text=text,
        source="unit-test",
        project="afr-17",
        created_at="2026-01-01T00:00:00",
        metadata={"kind": "sample"},
    )

    chunks = result["chunks"]
    assert result["chunks_created"] == 4
    assert chunks[0]["text"] == "abcdefghij"
    assert chunks[1]["text"] == "ijklmnopqr"
    assert chunks[0]["metadata"]["source"] == "unit-test"
    assert chunks[0]["metadata"]["project"] == "afr-17"
    assert chunks[0]["metadata"]["created_at"] == "2026-01-01T00:00:00"


def test_ingest_file_decodes_utf8_bom_and_attaches_filename():
    """Ensure file bytes are normalized to UTF-8 and filename metadata is present."""
    service = DocumentIngestionService(chunk_size=1000, chunk_overlap=100)
    file_bytes = "\ufeffhello\r\nworld".encode("utf-8")

    result = service.ingest_file(
        file_bytes=file_bytes,
        filename="note.txt",
        source="upload",
        project="afr-17",
    )

    assert result["text"] == "hello\nworld"
    assert result["metadata"]["filename"] == "note.txt"
    assert result["metadata"]["source"] == "upload"
    assert result["metadata"]["project"] == "afr-17"
    assert result["chunks_created"] == 1


def test_ingest_text_rejects_empty_inputs_and_invalid_created_at():
    """Ensure ingestion fails fast for invalid input fields."""
    service = DocumentIngestionService()

    with pytest.raises(ValueError, match="source is required"):
        service.ingest_text(text="hello", source="", project="demo")

    with pytest.raises(ValueError, match="text cannot be empty"):
        service.ingest_text(text="", source="upload", project="demo")

    with pytest.raises(ValueError, match="created_at must be a valid ISO-8601"):
        service.ingest_text(
            text="hello",
            source="upload",
            project="demo",
            created_at="not-a-date",
        )


def test_ingest_text_defaults_created_at_to_utc_iso8601():
    """Ensure created_at defaults to a normalized UTC timestamp when omitted."""
    service = DocumentIngestionService()

    result = service.ingest_text(text="hello", source="upload", project="demo")

    assert result["metadata"]["created_at"].endswith("Z")
