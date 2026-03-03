"""Workspace-scoped retrieval recipes store with versioning/rollback."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List


RECIPES_STORE_PATH = Path(os.getenv("RETRIEVAL_RECIPES_STORE_PATH", "data/retrieval_recipes.json"))


class RetrievalRecipesStore:
    def __init__(self, path: Path = RECIPES_STORE_PATH):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text(json.dumps({"versions": [], "active_version": None}), encoding="utf-8")

    def _load(self) -> Dict[str, Any]:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, payload: Dict[str, Any]) -> None:
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def create_version(self, *, workspace_id: str, recipes: List[Dict[str, Any]]) -> int:
        payload = self._load()
        versions = payload.get("versions", [])
        next_version = max((v.get("version", 0) for v in versions), default=0) + 1
        versions.append(
            {
                "version": next_version,
                "workspace_id": workspace_id,
                "recipes": recipes,
                "enabled": True,
                "created_at": int(time.time()),
            }
        )
        payload["versions"] = versions
        payload["active_version"] = next_version
        self._save(payload)
        return next_version

    def rollback(self, version: int) -> None:
        payload = self._load()
        payload["active_version"] = int(version)
        self._save(payload)

    def set_enabled(self, *, version: int, enabled: bool) -> None:
        payload = self._load()
        for item in payload.get("versions", []):
            if int(item.get("version", -1)) == int(version):
                item["enabled"] = bool(enabled)
        self._save(payload)

    def get_active_recipes(self, workspace_id: str) -> List[Dict[str, Any]]:
        payload = self._load()
        active_version = payload.get("active_version")
        for item in payload.get("versions", []):
            if (
                int(item.get("version", -1)) == int(active_version)
                and item.get("workspace_id") == workspace_id
                and bool(item.get("enabled", True))
            ):
                return list(item.get("recipes", []))
        return []


def apply_retrieval_recipe(query: str, recipes: List[Dict[str, Any]], default_top_k: int) -> Dict[str, Any]:
    """Apply first matching recipe by keyword to produce rewritten query and retrieval params."""
    normalized_query = str(query)
    for recipe in recipes:
        keyword = str(recipe.get("match_keyword", "")).strip().lower()
        if keyword and keyword in normalized_query.lower():
            rewrite_prefix = str(recipe.get("rewrite_prefix", "")).strip()
            rewritten_query = f"{rewrite_prefix} {normalized_query}".strip() if rewrite_prefix else normalized_query
            return {
                "query": rewritten_query,
                "top_k": int(recipe.get("top_k", default_top_k) or default_top_k),
                "filters": dict(recipe.get("filters", {})),
                "recipe_applied": True,
            }
    return {"query": normalized_query, "top_k": default_top_k, "filters": {}, "recipe_applied": False}
