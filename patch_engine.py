"""Patch engine to promote learning events into overlays and retrieval recipes."""

from __future__ import annotations

from typing import Any, Dict, List

from overlay_rules_store import OverlayRulesStore
from retrieval_recipes_store import RetrievalRecipesStore


def promote_learning_events(
    *,
    workspace_id: str,
    learning_events: List[Dict[str, Any]],
    overlay_store: OverlayRulesStore,
    recipes_store: RetrievalRecipesStore,
) -> Dict[str, Any]:
    """Promote validated events into overlay rules and retrieval recipes."""
    overlay_rules: List[Dict[str, Any]] = []
    recipes: List[Dict[str, Any]] = []

    for row in learning_events:
        event = row.get("event", row)
        if not isinstance(event, dict):
            continue
        # quality filter
        if event.get("outcome") not in {"teacher_guidance_attached", "grounded_after_recovery", "missing_context"}:
            continue
        if str(event.get("secret_check", "pass")) != "pass":
            continue

        trigger = str(event.get("trigger", ""))
        if trigger in {"missing_context", "graph_missing_context"}:
            overlay_rules.append(
                {
                    "intent": "freeform",
                    "contains": "bonjour",
                    "response": "Bonjour ! Je peux aider avec ton workspace.",
                    "enabled": True,
                }
            )
        if trigger in {"missing_context", "support_check"}:
            recipes.append(
                {
                    "match_keyword": "policy",
                    "rewrite_prefix": "internal documentation",
                    "top_k": 8,
                    "filters": {},
                }
            )

    overlay_version = overlay_store.create_version(workspace_id=workspace_id, rules=overlay_rules) if overlay_rules else None
    recipes_version = recipes_store.create_version(workspace_id=workspace_id, recipes=recipes) if recipes else None

    return {
        "overlay_version": overlay_version,
        "recipes_version": recipes_version,
        "overlay_rules_promoted": len(overlay_rules),
        "recipes_promoted": len(recipes),
    }
