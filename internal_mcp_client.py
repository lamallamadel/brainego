#!/usr/bin/env python3
# Needs: python-package:httpx>=0.28.1
"""Internal MCP gateway client for brainego API services."""

import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Set

import httpx

from safety_sanitizer import redact_secrets, sanitize_tool_output_payload
from safety_sanitizer import redact_sensitive

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
        allowed_tools: Optional[Set[str]] = None,
        timeout_seconds: float = 10.0,
        api_key: Optional[str] = None,
    ):
        self.gateway_base_url = gateway_base_url.rstrip("/")
        # Backward compatibility only; authorization lives in api_server proxy.
        self.allowed_tools = {
            tool.strip() for tool in (allowed_tools or set()) if tool and tool.strip()
        }
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

    def _headers(self, workspace_id: Optional[str] = None) -> Dict[str, str]:
        headers = {"content-type": "application/json"}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"
            headers["x-api-key"] = self.api_key
        if workspace_id:
            headers["x-workspace-id"] = workspace_id
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
        workspace_id: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        confirm: Optional[bool] = None,
        confirmation_id: Optional[str] = None,
    ) -> MCPToolResult:
        started_at = time.perf_counter()
        raw_arguments = arguments or {}
        redacted_arguments, argument_redactions = redact_sensitive(raw_arguments)
        payload = {
            "server_id": server_id,
            "tool_name": tool_name,
            "arguments": raw_arguments,
        }
        if workspace_id:
            payload["workspace_id"] = workspace_id
        if confirm is not None:
            payload["confirm"] = bool(confirm)
        if confirmation_id:
            payload["confirmation_id"] = confirmation_id

        # Authorization is enforced centrally by api_server/tool_policy_engine.
        # Keep the legacy local allowlist as an optional observability signal only.
        if self.allowed_tools and not self.is_tool_allowed(tool_name):
            logger.info(
                "mcp_tool_call tool=%s local_allowlist_miss=true context=%s (not enforced client-side)",
                tool_name,
                context,
            )

        effective_timeout_seconds = (
            float(timeout_seconds)
            if timeout_seconds is not None and float(timeout_seconds) > 0
            else self.timeout_seconds
        )

        try:
            async with httpx.AsyncClient(timeout=effective_timeout_seconds) as client:
                response = await client.post(
                    f"{self.gateway_base_url}/mcp/tools/call",
                    json=payload,
                    headers=self._headers(workspace_id=workspace_id),
                )

            latency_ms = (time.perf_counter() - started_at) * 1000

            if response.status_code >= 400:
                safe_error, error_safety = sanitize_tool_output_payload(response.text)
                error = safe_error if isinstance(safe_error, str) else str(safe_error)
                error, error_redactions = redact_sensitive(response.text)
                logger.error(
                    "mcp_tool_call tool=%s status=error http_status=%s latency_ms=%.2f error=%s context=%s arguments=%s argument_redactions=%s error_redactions=%s error_policy_hits=%s",
                    tool_name,
                    response.status_code,
                    latency_ms,
                    error,
                    context,
                    redacted_arguments,
                    argument_redactions,
                    error_safety["secret_redactions"],
                    error_safety["strings_with_injection"],
                )
                return MCPToolResult(
                    ok=False,
                    tool_name=tool_name,
                    latency_ms=latency_ms,
                    status_code=response.status_code,
                    error=error,
                )

            data = response.json()
            safe_data, output_safety = sanitize_tool_output_payload(data)
            if not isinstance(safe_data, dict):
                safe_data = {"result": safe_data}
            redacted_data, output_redactions = redact_sensitive(data)
            if not isinstance(redacted_data, dict):
                redacted_data = {"result": redacted_data}
            logger.info(
                "mcp_tool_call tool=%s status=ok http_status=%s latency_ms=%.2f context=%s arguments=%s argument_redactions=%s output_redactions=%s output_policy_hits=%s",
                tool_name,
                response.status_code,
                latency_ms,
                context,
                redacted_arguments,
                argument_redactions,
                output_safety["secret_redactions"],
                output_safety["strings_with_injection"],
            )
            return MCPToolResult(
                ok=True,
                tool_name=tool_name,
                latency_ms=latency_ms,
                status_code=response.status_code,
                data=safe_data,
            )
        except Exception as exc:
            latency_ms = (time.perf_counter() - started_at) * 1000
            safe_error, error_safety = sanitize_tool_output_payload(str(exc))
            redacted_error = safe_error if isinstance(safe_error, str) else str(safe_error)
            redacted_error, error_redactions = redact_sensitive(str(exc))
            logger.exception(
                "mcp_tool_call tool=%s status=exception latency_ms=%.2f context=%s arguments=%s argument_redactions=%s error_redactions=%s error_policy_hits=%s",
                tool_name,
                latency_ms,
                context,
                redacted_arguments,
                argument_redactions,
                error_safety["secret_redactions"],
                error_safety["strings_with_injection"],
            )
            return MCPToolResult(
                ok=False,
                tool_name=tool_name,
                latency_ms=latency_ms,
                status_code=502,
                error=redacted_error,
            )
