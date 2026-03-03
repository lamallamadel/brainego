"""Teacher broker with strict redaction and safe timeout fallback."""

from __future__ import annotations

import asyncio
import re
from typing import Any, Dict, List, Tuple


RAW_CHUNK_MARKERS = ("<<<BEGIN_CONTEXT_CHUNK", "<<<END_CONTEXT_CHUNK", "BEGIN_CONTEXT")
_SECRET_PATTERNS = [
    re.compile(r"(?i)api[_-]?key\s*[:=]\s*\S+"),
    re.compile(r"(?i)password\s*[:=]\s*\S+"),
    re.compile(r"(?i)token\s*[:=]\s*\S+"),
]


def _redact_secrets(text: str) -> str:
    value = str(text)
    for pattern in _SECRET_PATTERNS:
        value = pattern.sub("[REDACTED_SECRET]", value)
    return value


class TeacherBroker:
    """Build sanitized teacher requests and return safe guidance payloads."""

    def __init__(self, timeout_seconds: float = 1.5):
        self.timeout_seconds = timeout_seconds

    def build_request(
        self,
        *,
        question: str,
        metadata: Dict[str, Any],
        redacted_summaries: List[str],
    ) -> Tuple[Dict[str, Any], bool]:
        blocked = False
        cleaned_summaries: List[str] = []
        for item in redacted_summaries[:5]:
            text = str(item)
            if any(marker in text for marker in RAW_CHUNK_MARKERS):
                blocked = True
                continue
            cleaned_summaries.append(_redact_secrets(text)[:400])

        request = {
            "question": _redact_secrets(str(question)),
            "metadata": {
                "workspace_id": str(metadata.get("workspace_id", "")),
                "grounding_intent": str(metadata.get("grounding_intent", "")),
                "ess": float(metadata.get("ess", 0.0) or 0.0),
            },
            "summaries": cleaned_summaries,
        }
        return request, blocked

    async def _fake_teacher(self, request: Dict[str, Any]) -> Dict[str, Any]:
        q = request.get("question", "")
        return {
            "clarifying_questions": [
                f"Quel document interne couvre précisément: '{str(q)[:80]}' ?",
                "As-tu le repository/path exact à indexer ?",
            ],
            "candidate_queries": [str(q)[:120]],
            "search_plan": ["search_internal_docs", "filter_workspace_sources"],
            "ingestion_suggestions": ["Indexer les documents manquants dans ce workspace puis relancer la question."],
            "hypotheses": ["Le corpus actuel ne contient pas la preuve attendue."],
        }

    async def call(self, request: Dict[str, Any]) -> Dict[str, Any]:
        return await asyncio.wait_for(self._fake_teacher(request), timeout=self.timeout_seconds)
