#!/usr/bin/env python3
"""Collectors for streaming sources exposed through MCP servers."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)


class MCPStreamingCollector:
    """Collects Slack/Gmail content through configured MCP servers."""

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or os.getenv("MCP_SERVERS_CONFIG", "configs/mcp-servers.yaml")

    async def collect_slack_signals_via_mcp(
        self,
        *,
        query: str,
        hours_back: int = 2,
        count: int = 50,
        channel_ids: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Collect Slack messages via MCP search and annotate extracted signals."""
        from mcp_client import MCPClientService

        servers_config = self._load_mcp_server_config()
        client = MCPClientService(servers_config)
        await client.initialize()

        try:
            search_args = {"query": query, "count": count}
            raw_result = await client.call_tool("mcp-slack", "slack_search_messages", search_args)
            messages = self._extract_messages_from_mcp_result(raw_result)

            if channel_ids:
                channel_filter = {cid for cid in channel_ids if cid}
                messages = [m for m in messages if str(m.get("channel_id") or m.get("channel", "")) in channel_filter]

            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
            documents: List[Dict[str, Any]] = []

            for message in messages:
                ts = self._parse_message_timestamp(message)
                if ts and ts < cutoff:
                    continue

                text = self._extract_text(message)
                if not text:
                    continue

                signals = self._extract_signals(text)
                if not any(signals.values()):
                    continue

                metadata = {
                    "source": "slack",
                    "ingestion_source": "mcp-slack",
                    "source_type": "message",
                    "channel_id": message.get("channel_id") or message.get("channel", ""),
                    "channel_name": message.get("channel_name") or message.get("channel", ""),
                    "thread_ts": message.get("thread_ts") or message.get("thread", ""),
                    "message_ts": str(message.get("ts") or ""),
                    "user_id": message.get("user") or message.get("user_id", "unknown"),
                    "collected_at": datetime.utcnow().isoformat(),
                    "created_at": ts.isoformat() if ts else datetime.utcnow().isoformat(),
                    "signal_decisions": signals["decisions"],
                    "signal_todos": signals["todos"],
                    "signal_important": signals["important"],
                    "signal_tags": [
                        tag
                        for tag, values in (
                            ("decision", signals["decisions"]),
                            ("todo", signals["todos"]),
                            ("important", signals["important"]),
                        )
                        if values
                    ],
                    "original_message": message,
                }

                documents.append(
                    {
                        "text": self._build_signal_document_text(text=text, signals=signals),
                        "metadata": metadata,
                    }
                )

            logger.info("Collected %s Slack MCP signal documents", len(documents))
            return documents
        finally:
            await client.close_all()

    def _load_mcp_server_config(self) -> Dict[str, Any]:
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"MCP config not found: {self.config_path}")

        import yaml

        with open(self.config_path, "r", encoding="utf-8") as handle:
            config = yaml.safe_load(handle) or {}

        return config.get("servers", {})

    def _extract_messages_from_mcp_result(self, result: Dict[str, Any]) -> List[Dict[str, Any]]:
        parsed_messages: List[Dict[str, Any]] = []
        for chunk in result.get("content", []):
            if chunk.get("type") != "text":
                continue

            text_payload = chunk.get("text")
            if not text_payload:
                continue

            try:
                payload = json.loads(text_payload)
            except json.JSONDecodeError:
                continue

            if isinstance(payload, dict):
                if isinstance(payload.get("messages"), list):
                    parsed_messages.extend([m for m in payload["messages"] if isinstance(m, dict)])
                elif isinstance(payload.get("matches"), list):
                    parsed_messages.extend([m for m in payload["matches"] if isinstance(m, dict)])
                elif isinstance(payload.get("items"), list):
                    parsed_messages.extend([m for m in payload["items"] if isinstance(m, dict)])
            elif isinstance(payload, list):
                parsed_messages.extend([m for m in payload if isinstance(m, dict)])

        return parsed_messages

    def _parse_message_timestamp(self, message: Dict[str, Any]) -> Optional[datetime]:
        raw_ts = message.get("ts") or message.get("timestamp") or message.get("created_at")
        if raw_ts is None:
            return None

        if isinstance(raw_ts, (int, float)):
            return datetime.fromtimestamp(float(raw_ts), tz=timezone.utc)

        if isinstance(raw_ts, str):
            try:
                return datetime.fromtimestamp(float(raw_ts), tz=timezone.utc)
            except ValueError:
                pass
            try:
                normalized = raw_ts.replace("Z", "+00:00")
                parsed = datetime.fromisoformat(normalized)
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                return None

        return None

    def _extract_text(self, message: Dict[str, Any]) -> str:
        for key in ("text", "message", "content", "body"):
            value = message.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    def _extract_signals(self, text: str) -> Dict[str, List[str]]:
        lowered = text.lower()

        decision_matches = self._keyword_matches(
            lowered,
            ["decision", "decided", "approved", "we will", "let's", "agreed"],
        )
        todo_matches = self._keyword_matches(
            lowered,
            ["todo", "action item", "follow up", "next step", "assign", "owner", "deadline"],
        )
        important_matches = self._keyword_matches(
            lowered,
            ["urgent", "important", "blocker", "incident", "risk", "asap", "critical"],
        )

        return {
            "decisions": decision_matches,
            "todos": todo_matches,
            "important": important_matches,
        }

    def _keyword_matches(self, lowered_text: str, keywords: List[str]) -> List[str]:
        return [kw for kw in keywords if re.search(rf"\b{re.escape(kw)}\b", lowered_text)]

    def _build_signal_document_text(self, *, text: str, signals: Dict[str, List[str]]) -> str:
        sections: List[str] = ["## Extracted signals"]
        if signals["decisions"]:
            sections.append(f"- Decisions: {', '.join(signals['decisions'])}")
        if signals["todos"]:
            sections.append(f"- TODOs: {', '.join(signals['todos'])}")
        if signals["important"]:
            sections.append(f"- Important: {', '.join(signals['important'])}")

        sections.append("\n## Original message")
        sections.append(text)
        return "\n".join(sections)
