"""Grounding intent classifier for truth-contract routing decisions."""

from __future__ import annotations

from enum import Enum


class GroundingIntent(str, Enum):
    """Grounding policy classes for incoming requests."""

    MUST_GROUND = "must_ground"
    SHOULD_GROUND = "should_ground"
    FREEFORM = "freeform"


_GREETINGS = {
    "hello",
    "hi",
    "hey",
    "bonjour",
    "salut",
    "good morning",
    "good afternoon",
    "good evening",
}

_BRAINSTORM_TERMS = {
    "brainstorm",
    "ideas",
    "idées",
    "creative",
    "imagine",
    "hypothesis",
    "hypothèse",
}

_FACTUAL_TERMS = {
    "what",
    "when",
    "where",
    "who",
    "which",
    "combien",
    "pourquoi",
    "status",
    "policy",
    "chiffre",
    "metric",
    "preuve",
    "source",
}

_SUMMARY_TERMS = {
    "summarize",
    "summary",
    "résume",
    "résumé",
    "tl;dr",
}

_DOC_TERMS = {
    "doc",
    "document",
    "readme",
    "spec",
    "contrat",
    "wiki",
    "repo",
    "repository",
    "notion",
}


class GroundingIntentClassifier:
    """Heuristic classifier for must/should/freeform grounded answering."""

    def classify(self, text: str) -> GroundingIntent:
        normalized = (text or "").strip().lower()
        if not normalized:
            return GroundingIntent.FREEFORM

        if normalized in _GREETINGS:
            return GroundingIntent.FREEFORM

        if any(term in normalized for term in _BRAINSTORM_TERMS):
            return GroundingIntent.FREEFORM

        has_summary = any(term in normalized for term in _SUMMARY_TERMS)
        has_doc_ref = any(term in normalized for term in _DOC_TERMS)
        has_factual = any(term in normalized for term in _FACTUAL_TERMS) or "?" in normalized

        if (has_summary and has_doc_ref) or (has_factual and has_doc_ref):
            return GroundingIntent.MUST_GROUND
        if has_summary or has_factual:
            return GroundingIntent.SHOULD_GROUND
        return GroundingIntent.FREEFORM
