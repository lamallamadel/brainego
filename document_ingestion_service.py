#!/usr/bin/env python3
"""Document ingestion and chunking utilities."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional


class DocumentIngestionService:
    """Service that normalizes text/file inputs and creates overlapping chunks."""

    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 100):
        if chunk_size <= 0:
            raise ValueError("chunk_size must be greater than 0")
        if chunk_overlap < 0:
            raise ValueError("chunk_overlap must be >= 0")
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")

        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def ingest_text(
        self,
        text: str,
        source: str,
        project: str,
        created_at: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Normalize raw text and split it into chunks with metadata."""
        self._validate_required_field("source", source)
        self._validate_required_field("project", project)

        normalized_text = self._normalize_text(text)
        if not normalized_text:
            raise ValueError("text cannot be empty after normalization")

        return self._build_chunked_document(
            normalized_text=normalized_text,
            source=source,
            project=project,
            created_at=created_at,
            metadata=metadata,
        )

    def ingest_file(
        self,
        file_bytes: bytes,
        filename: str,
        source: str,
        project: str,
        created_at: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Decode file bytes into UTF-8 text and split into chunks with metadata."""
        self._validate_required_field("source", source)
        self._validate_required_field("project", project)
        self._validate_required_field("filename", filename)

        decoded_text = self._decode_bytes_to_utf8(file_bytes)
        if not decoded_text:
            raise ValueError("file content cannot be empty after normalization")

        effective_metadata = dict(metadata or {})
        effective_metadata.setdefault("filename", filename)

        return self._build_chunked_document(
            normalized_text=decoded_text,
            source=source,
            project=project,
            created_at=created_at,
            metadata=effective_metadata,
        )

    def _validate_required_field(self, field_name: str, value: str) -> None:
        """Validate required metadata fields."""
        if not value or not value.strip():
            raise ValueError(f"{field_name} is required")

    def _decode_bytes_to_utf8(self, file_bytes: bytes) -> str:
        """Decode bytes and guarantee a UTF-8-safe Python string."""
        if not file_bytes:
            return ""

        for encoding in ("utf-8-sig", "utf-8"):
            try:
                return self._normalize_text(file_bytes.decode(encoding))
            except UnicodeDecodeError:
                continue

        return self._normalize_text(file_bytes.decode("utf-8", errors="replace"))

    def _normalize_text(self, text: str) -> str:
        """Normalize text to UTF-8-safe representation and canonical newlines."""
        utf8_safe = text.encode("utf-8", errors="replace").decode("utf-8")
        return utf8_safe.replace("\r\n", "\n").replace("\r", "\n")

    def _normalize_created_at(self, created_at: Optional[str]) -> str:
        """Normalize created_at to ISO-8601, defaulting to current UTC time."""
        if not created_at:
            return datetime.utcnow().isoformat() + "Z"

        normalized = created_at.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"

        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as error:
            raise ValueError("created_at must be a valid ISO-8601 datetime") from error

        return parsed.isoformat()

    def _build_chunked_document(
        self,
        normalized_text: str,
        source: str,
        project: str,
        created_at: Optional[str],
        metadata: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Create chunk payload with required metadata fields."""
        base_metadata = dict(metadata or {})
        base_metadata.update(
            {
                "source": source,
                "project": project,
                "created_at": self._normalize_created_at(created_at),
            }
        )

        chunk_step = self.chunk_size - self.chunk_overlap
        chunks: List[Dict[str, Any]] = []

        start = 0
        chunk_index = 0
        while start < len(normalized_text):
            end = min(start + self.chunk_size, len(normalized_text))
            chunk_metadata = dict(base_metadata)
            chunk_metadata.update(
                {
                    "chunk_index": chunk_index,
                    "chunk_start": start,
                    "chunk_end": end,
                    "document_length": len(normalized_text),
                }
            )
            chunks.append({"text": normalized_text[start:end], "metadata": chunk_metadata})
            start += chunk_step
            chunk_index += 1

        return {
            "document_id": str(uuid.uuid4()),
            "text": normalized_text,
            "metadata": base_metadata,
            "chunks": chunks,
            "chunks_created": len(chunks),
        }
