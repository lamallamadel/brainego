"""Overlay rules store with versioning and rollback."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List


OVERLAY_STORE_PATH = Path(os.getenv("OVERLAY_STORE_PATH", "data/overlay_rules.json"))


class OverlayRulesStore:
    def __init__(self, path: Path = OVERLAY_STORE_PATH):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text(json.dumps({"versions": [], "active_version": None}), encoding="utf-8")

    def _load(self) -> Dict[str, Any]:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, payload: Dict[str, Any]) -> None:
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def create_version(self, *, rules: List[Dict[str, Any]], workspace_id: str) -> int:
        payload = self._load()
        versions = payload.get("versions", [])
        next_version = (max((item.get("version", 0) for item in versions), default=0) + 1)
        versions.append(
            {
                "version": next_version,
                "workspace_id": workspace_id,
                "enabled": True,
                "created_at": int(time.time()),
                "rules": rules,
            }
        )
        payload["versions"] = versions
        payload["active_version"] = next_version
        self._save(payload)
        return next_version

    def set_enabled(self, *, version: int, enabled: bool) -> None:
        payload = self._load()
        for item in payload.get("versions", []):
            if int(item.get("version", -1)) == int(version):
                item["enabled"] = bool(enabled)
        self._save(payload)

    def rollback(self, version: int) -> None:
        payload = self._load()
        payload["active_version"] = int(version)
        self._save(payload)

    def get_active_rules(self, workspace_id: str) -> List[Dict[str, Any]]:
        payload = self._load()
        active_version = payload.get("active_version")
        for item in payload.get("versions", []):
            if (
                int(item.get("version", -1)) == int(active_version)
                and item.get("workspace_id") == workspace_id
                and bool(item.get("enabled", True))
            ):
                return list(item.get("rules", []))
        return []
