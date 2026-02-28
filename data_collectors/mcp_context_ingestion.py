#!/usr/bin/env python3
"""MCP-based context ingestion helpers for project data sources."""

import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx


class MCPGitHubContextIngestor:
    """Collect GitHub project context through MCP gateway."""

    def __init__(
        self,
        gateway_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout_seconds: float = 30.0,
    ):
        self.gateway_url = gateway_url or os.getenv("MCP_GATEWAY_URL", "http://mcpjungle:9100")
        self.api_key = api_key or os.getenv("MCP_GATEWAY_API_KEY", "")
        self.timeout_seconds = timeout_seconds

    async def collect_project_context(self, query: str, per_page: int = 20) -> List[Dict[str, Any]]:
        headers = {"content-type": "application/json"}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"

        payload = {
            "action": "call_tool",
            "server_id": "mcp-github",
            "tool_name": "github_search_repositories",
            "arguments": {
                "query": query,
                "per_page": per_page,
            },
        }

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(f"{self.gateway_url}/mcp", headers=headers, json=payload)
            response.raise_for_status()
            raw = response.json()

        results = []
        now = datetime.utcnow().isoformat()
        for item in (raw.get("result", {}).get("content") or []):
            text = item.get("text") or ""
            if not text:
                continue
            results.append(
                {
                    "text": text,
                    "metadata": {
                        "source": "mcp-github",
                        "query": query,
                        "collected_at": now,
                    },
                }
            )

        return results



class MCPNotionKnowledgeIngestor:
    """Collect Notion knowledge base context through MCP gateway."""

    def __init__(
        self,
        gateway_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout_seconds: float = 30.0,
    ):
        self.gateway_url = gateway_url or os.getenv("MCP_GATEWAY_URL", "http://mcpjungle:9100")
        self.api_key = api_key or os.getenv("MCP_GATEWAY_API_KEY", "")
        self.timeout_seconds = timeout_seconds

    async def collect_knowledge_base(self, query: str) -> List[Dict[str, Any]]:
        headers = {"content-type": "application/json"}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"

        payload = {
            "action": "call_tool",
            "server_id": "mcp-notion",
            "tool_name": "notion_search",
            "arguments": {
                "query": query,
            },
        }

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(f"{self.gateway_url}/mcp", headers=headers, json=payload)
            response.raise_for_status()
            raw = response.json()

        results = []
        now = datetime.utcnow().isoformat()
        for item in (raw.get("result", {}).get("content") or []):
            text = item.get("text") or ""
            if not text:
                continue
            results.append(
                {
                    "text": text,
                    "metadata": {
                        "source": "mcp-notion",
                        "query": query,
                        "collected_at": now,
                    },
                }
            )

        return results



class MCPSlackStreamingSource:
    """Fetch near-real-time Slack content through MCP as a streaming source."""

    def __init__(
        self,
        gateway_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout_seconds: float = 30.0,
    ):
        self.gateway_url = gateway_url or os.getenv("MCP_GATEWAY_URL", "http://mcpjungle:9100")
        self.api_key = api_key or os.getenv("MCP_GATEWAY_API_KEY", "")
        self.timeout_seconds = timeout_seconds

    async def fetch_channel_history(self, channel_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        headers = {"content-type": "application/json"}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"

        payload = {
            "action": "call_tool",
            "server_id": "mcp-slack",
            "tool_name": "slack_get_channel_history",
            "arguments": {
                "channel": channel_id,
                "limit": limit,
            },
        }

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(f"{self.gateway_url}/mcp", headers=headers, json=payload)
            response.raise_for_status()
            raw = response.json()

        records = []
        collected_at = datetime.utcnow().isoformat()
        for item in (raw.get("result", {}).get("content") or []):
            text = item.get("text") or ""
            if not text:
                continue
            records.append(
                {
                    "text": text,
                    "metadata": {
                        "source": "mcp-slack",
                        "channel_id": channel_id,
                        "collected_at": collected_at,
                    },
                }
            )

        return records
