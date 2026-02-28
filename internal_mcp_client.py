#!/usr/bin/env python3
"""Internal MCP gateway client for brainego API services."""

import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Set

import httpx

logger = logging.getLogger(__name__)


@dataclass
class MCPToolResult:
    """Structured tool-call result returned to internal services."""

    ok: bool
    tool_name: str
    latency_ms: float
    status_code: int
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "tool_name": self.tool_name,
            "latency_ms": round(self.latency_ms, 2),
            "status_code": self.status_code,
            "data": self.data,
            "error": self.error,
        }


class InternalMCPGatewayClient:
    """Client used by API internals (RAG, agents) to call MCP gateway tools."""

    def __init__(
        self,
        gateway_base_url: str,
        allowed_tools: Set[str],
        timeout_seconds: float = 10.0,
        api_key: Optional[str] = None,
    ):
        self.gateway_base_url = gateway_base_url.rstrip("/")
        self.allowed_tools = {tool.strip() for tool in allowed_tools if tool.strip()}
        self.timeout_seconds = timeout_seconds
        self.api_key = api_key

    @classmethod
    def from_env(cls) -> "InternalMCPGatewayClient":
        allowed_tools_raw = os.getenv("MCP_ALLOWED_TOOLS", "")
        allowed_tools = set(allowed_tools_raw.split(",")) if allowed_tools_raw else set()

        return cls(
            gateway_base_url=os.getenv("MCP_GATEWAY_URL", "http://localhost:9100"),
            allowed_tools=allowed_tools,
            timeout_seconds=float(os.getenv("MCP_GATEWAY_TIMEOUT_SECONDS", "10")),
            api_key=os.getenv("MCP_GATEWAY_API_KEY"),
        )

    def _headers(self) -> Dict[str, str]:
        headers = {"content-type": "application/json"}
        if self.api_key:
            headers["x-api-key"] = self.api_key
        return headers

    def is_tool_allowed(self, tool_name: str) -> bool:
        if not self.allowed_tools:
            return True
        return tool_name in self.allowed_tools

    async def call_tool(
        self,
        server_id: str,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
        context: Optional[str] = None,
    ) -> MCPToolResult:
        started_at = time.perf_counter()
        payload = {
            "server_id": server_id,
            "tool_name": tool_name,
            "arguments": arguments or {},
        }

        if not self.is_tool_allowed(tool_name):
            latency_ms = (time.perf_counter() - started_at) * 1000
            error = f"Tool '{tool_name}' is not allowed for API-routed MCP calls"
            logger.warning(
                "mcp_tool_call tool=%s status=blocked latency_ms=%.2f error=%s context=%s",
                tool_name,
                latency_ms,
                error,
                context,
            )
            return MCPToolResult(
                ok=False,
                tool_name=tool_name,
                latency_ms=latency_ms,
                status_code=403,
                error=error,
            )

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    f"{self.gateway_base_url}/mcp/tools/call",
                    json=payload,
                    headers=self._headers(),
                )

            latency_ms = (time.perf_counter() - started_at) * 1000

            if response.status_code >= 400:
                error = response.text
                logger.error(
                    "mcp_tool_call tool=%s status=error http_status=%s latency_ms=%.2f error=%s context=%s",
                    tool_name,
                    response.status_code,
                    latency_ms,
                    error,
                    context,
                )
                return MCPToolResult(
                    ok=False,
                    tool_name=tool_name,
                    latency_ms=latency_ms,
                    status_code=response.status_code,
                    error=error,
                )

            data = response.json()
            logger.info(
                "mcp_tool_call tool=%s status=ok http_status=%s latency_ms=%.2f context=%s",
                tool_name,
                response.status_code,
                latency_ms,
                context,
            )
            return MCPToolResult(
                ok=True,
                tool_name=tool_name,
                latency_ms=latency_ms,
                status_code=response.status_code,
                data=data,
            )
        except Exception as exc:
            latency_ms = (time.perf_counter() - started_at) * 1000
            logger.exception(
                "mcp_tool_call tool=%s status=exception latency_ms=%.2f context=%s",
                tool_name,
                latency_ms,
                context,
            )
            return MCPToolResult(
                ok=False,
                tool_name=tool_name,
                latency_ms=latency_ms,
                status_code=502,
                error=str(exc),
            )
