"""Lightweight learning events store with workspace-scoped retention."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List


LEARNING_EVENTS_PATH = Path(os.getenv("LEARNING_EVENTS_PATH", "data/learning_events.jsonl"))
LEARNING_EVENTS_VERSION = 1


class LearningEventsStore:
    def __init__(self, path: Path = LEARNING_EVENTS_PATH):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _redact(value: Any) -> Any:
        text = str(value)
        lowered = text.lower()
        if "api_key" in lowered or "password" in lowered or "token=" in lowered:
            return "[REDACTED_SECRET]"
        return value

    def append(self, *, workspace_id: str, event: Dict[str, Any]) -> None:
        payload = {
            "version": LEARNING_EVENTS_VERSION,
            "workspace_id": workspace_id,
            "created_at": int(time.time()),
            "event": {k: self._redact(v) for k, v in dict(event).items()},
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def list_workspace(self, workspace_id: str) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: List[Dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            if item.get("workspace_id") == workspace_id:
                rows.append(item)
        return rows

    def retain_workspace_last_n(self, workspace_id: str, n: int) -> None:
        if not self.path.exists():
            return
        all_rows: List[Dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                all_rows.append(json.loads(line))
        ws_rows = [row for row in all_rows if row.get("workspace_id") == workspace_id]
        keep_ws = ws_rows[-max(0, n):]
        keep_set = {json.dumps(row, sort_keys=True) for row in keep_ws}
        filtered: List[Dict[str, Any]] = []
        for row in all_rows:
            if row.get("workspace_id") != workspace_id:
                filtered.append(row)
            elif json.dumps(row, sort_keys=True) in keep_set:
                filtered.append(row)
        with self.path.open("w", encoding="utf-8") as f:
            for row in filtered:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
