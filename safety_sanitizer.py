"""Utilities for redacting secrets and sanitizing untrusted retrieved context."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

REDACTION_TOKEN = "[REDACTED_SECRET]"
INJECTION_REMOVAL_TOKEN = "[Context removed: potential prompt-injection content]"

SECRET_PATTERNS = [
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{10,}\b"),
    re.compile(r"\b(?:ghp|gho|ghu|ghs|github_pat)_[A-Za-z0-9_]{20,}\b"),
    re.compile(
        r"(?i)\b(api[_ -]?key|token|secret|password|client_secret|aws_secret_access_key)\b"
        r"\s*[:=]\s*[\"']?[A-Za-z0-9_\-\/+=]{6,}[\"']?"
    ),
]

UNTRUSTED_CONTEXT_INJECTION_PATTERNS = [
    re.compile(
        r"(?i)\b(ignore|disregard|forget)\b.{0,120}\b(previous|prior|above|system|developer|instructions?)\b"
    ),
    re.compile(r"(?i)\b(you are now|new system prompt|developer mode|jailbreak)\b"),
    re.compile(
        r"(?i)\b(reveal|print|show)\b.{0,140}\b(system prompt|hidden prompt|secret|api key|token|password)\b"
    ),
    re.compile(r"(?i)\b(override|bypass)\b.{0,80}\b(policy|safety|guardrail|system)\b"),
]


def redact_secrets_in_text(text: str) -> Tuple[str, int]:
    """Redact secret-like substrings from a string."""
    if not isinstance(text, str) or not text:
        return text, 0

    redacted = text
    redaction_count = 0
    for pattern in SECRET_PATTERNS:
        redacted, applied = pattern.subn(REDACTION_TOKEN, redacted)
        redaction_count += applied
    return redacted, redaction_count


def redact_secrets(value: Any) -> Tuple[Any, int]:
    """Recursively redact secret-like values in nested Python objects."""
    if isinstance(value, str):
        return redact_secrets_in_text(value)

    if isinstance(value, dict):
        total = 0
        sanitized: Dict[Any, Any] = {}
        for key, item in value.items():
            sanitized_item, count = redact_secrets(item)
            sanitized[key] = sanitized_item
            total += count
        return sanitized, total

    if isinstance(value, list):
        total = 0
        sanitized_list: List[Any] = []
        for item in value:
            sanitized_item, count = redact_secrets(item)
            sanitized_list.append(sanitized_item)
            total += count
        return sanitized_list, total

    if isinstance(value, tuple):
        total = 0
        sanitized_items: List[Any] = []
        for item in value:
            sanitized_item, count = redact_secrets(item)
            sanitized_items.append(sanitized_item)
            total += count
        return tuple(sanitized_items), total

    return value, 0


def sanitize_untrusted_context_text(text: str) -> Tuple[str, Dict[str, Any]]:
    """Drop prompt-injection lines and redact secrets in untrusted context text."""
    if not isinstance(text, str) or not text:
        return text, {
            "injection_detected": False,
            "dropped_injection_lines": 0,
            "secret_redactions": 0,
        }

    kept_lines: List[str] = []
    dropped_lines = 0
    for line in text.splitlines():
        if any(pattern.search(line) for pattern in UNTRUSTED_CONTEXT_INJECTION_PATTERNS):
            dropped_lines += 1
            continue
        kept_lines.append(line)

    sanitized = "\n".join(kept_lines).strip()
    if dropped_lines > 0 and not sanitized:
        sanitized = INJECTION_REMOVAL_TOKEN

    sanitized, redaction_count = redact_secrets_in_text(sanitized)
    metadata = {
        "injection_detected": dropped_lines > 0,
        "dropped_injection_lines": dropped_lines,
        "secret_redactions": redaction_count,
    }
    return sanitized, metadata


def sanitize_retrieved_context_chunks(
    chunks: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Sanitize retrieved context chunks and return aggregate sanitization stats."""
    sanitized_chunks: List[Dict[str, Any]] = []
    chunks_with_injection = 0
    dropped_injection_lines = 0
    secret_redactions = 0

    for chunk in chunks or []:
        safe_chunk = dict(chunk)

        text_value = chunk.get("text")
        if isinstance(text_value, str):
            sanitized_text, text_meta = sanitize_untrusted_context_text(text_value)
            safe_chunk["text"] = sanitized_text
            if text_meta["injection_detected"]:
                chunks_with_injection += 1
            dropped_injection_lines += int(text_meta["dropped_injection_lines"])
            secret_redactions += int(text_meta["secret_redactions"])

        metadata_value = chunk.get("metadata")
        if metadata_value is not None:
            safe_metadata, metadata_redactions = redact_secrets(metadata_value)
            safe_chunk["metadata"] = safe_metadata
            secret_redactions += metadata_redactions

        sanitized_chunks.append(safe_chunk)

    stats = {
        "chunks_processed": len(chunks or []),
        "chunks_with_injection": chunks_with_injection,
        "dropped_injection_lines": dropped_injection_lines,
        "secret_redactions": secret_redactions,
    }
    return sanitized_chunks, stats
