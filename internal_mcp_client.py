#!/usr/bin/env python3
# Needs: python-package:httpx>=0.28.1
"""Internal MCP gateway client for brainego API services."""

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set

import httpx

from tool_policy_engine import ToolPolicyEngine, load_default_tool_policy_engine

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
        tool_policy_engine: Optional[ToolPolicyEngine] = None,
        default_workspace_id: Optional[str] = None,
    ):
        self.gateway_base_url = gateway_base_url.rstrip("/")
        self.allowed_tools = {tool.strip() for tool in allowed_tools if tool.strip()}
        self.timeout_seconds = timeout_seconds
        self.api_key = api_key
        self.tool_policy_engine = tool_policy_engine
        self.default_workspace_id = (default_workspace_id or "").strip() or None

    @classmethod
    def from_env(cls) -> "InternalMCPGatewayClient":
        allowed_tools_raw = os.getenv("MCP_ALLOWED_TOOLS", "")
        allowed_tools = set(allowed_tools_raw.split(",")) if allowed_tools_raw else set()
        tool_policy_enabled = os.getenv("MCP_TOOL_POLICY_ENABLED", "true").lower() == "true"

        tool_policy_engine: Optional[ToolPolicyEngine] = None
        if tool_policy_enabled:
            tool_policy_engine = load_default_tool_policy_engine()

        return cls(
            gateway_base_url=os.getenv("MCP_GATEWAY_URL", "http://localhost:9100"),
            allowed_tools=allowed_tools,
            timeout_seconds=float(os.getenv("MCP_GATEWAY_TIMEOUT_SECONDS", "10")),
            api_key=os.getenv("MCP_GATEWAY_API_KEY"),
            tool_policy_engine=tool_policy_engine,
            default_workspace_id=os.getenv("MCP_TOOL_POLICY_DEFAULT_WORKSPACE"),
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

    def _infer_action(self, tool_name: str, action: Optional[str]) -> str:
        normalized = (action or "").strip().lower()
        if normalized in {"read", "write", "delete"}:
            return normalized

        tool_name_lower = tool_name.lower()
        if any(token in tool_name_lower for token in ("delete", "remove", "destroy", "drop", "erase")):
            return "delete"
        if any(
            token in tool_name_lower
            for token in ("create", "update", "write", "append", "modify", "post", "send", "upload", "add")
        ):
            return "write"
        return "read"

    def _policy_denied_result(
        self,
        *,
        started_at: float,
        server_id: str,
        tool_name: str,
        context: Optional[str],
        workspace_id: Optional[str],
        request_id: Optional[str],
        action: str,
        reason: str,
    ) -> MCPToolResult:
        latency_ms = (time.perf_counter() - started_at) * 1000
        normalized_workspace = workspace_id or self.default_workspace_id or "unknown"
        normalized_request_id = request_id or f"auto-{uuid.uuid4().hex[:8]}"
        audit_event = {
            "event_type": "tool_policy_denied",
            "code": "PolicyDenied",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "workspace_id": normalized_workspace,
            "request_id": normalized_request_id,
            "server_id": server_id,
            "tool_name": tool_name,
            "action": action,
            "context": context,
            "reason": reason,
        }
        logger.warning("audit_event=%s", json.dumps(audit_event, sort_keys=True))
        return MCPToolResult(
            ok=False,
            tool_name=tool_name,
            latency_ms=latency_ms,
            status_code=403,
            error=f"PolicyDenied: {reason}",
            data={"code": "PolicyDenied", "audit_event": audit_event},
        )

    async def call_tool(
        self,
        server_id: str,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
        context: Optional[str] = None,
        workspace_id: Optional[str] = None,
        request_id: Optional[str] = None,
        action: Optional[str] = None,
    ) -> MCPToolResult:
        started_at = time.perf_counter()
        normalized_action = self._infer_action(tool_name, action)
        effective_workspace_id = (workspace_id or self.default_workspace_id or "").strip() or None
        payload_arguments = arguments or {}
        payload = {
            "server_id": server_id,
            "tool_name": tool_name,
            "arguments": payload_arguments,
        }

        if not self.is_tool_allowed(tool_name):
            return self._policy_denied_result(
                started_at=started_at,
                server_id=server_id,
                tool_name=tool_name,
                context=context,
                workspace_id=effective_workspace_id,
                request_id=request_id,
                action=normalized_action,
                reason=f"tool '{tool_name}' is not allowed for API-routed MCP calls",
            )

        effective_timeout_seconds = self.timeout_seconds
        if self.tool_policy_engine:
            decision = self.tool_policy_engine.evaluate_tool_call(
                workspace_id=effective_workspace_id,
                request_id=request_id,
                server_id=server_id,
                tool_name=tool_name,
                action=normalized_action,
                arguments=payload_arguments,
                default_timeout_seconds=self.timeout_seconds,
            )
            if not decision.allowed:
                return self._policy_denied_result(
                    started_at=started_at,
                    server_id=server_id,
                    tool_name=tool_name,
                    context=context,
                    workspace_id=decision.workspace_id or effective_workspace_id,
                    request_id=request_id,
                    action=normalized_action,
                    reason=decision.reason or "Tool call denied by workspace policy",
                )
            if decision.timeout_seconds and decision.timeout_seconds > 0:
                effective_timeout_seconds = decision.timeout_seconds

        try:
            async with httpx.AsyncClient(timeout=effective_timeout_seconds) as client:
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
                "mcp_tool_call tool=%s status=ok action=%s workspace=%s http_status=%s latency_ms=%.2f context=%s",
                tool_name,
                normalized_action,
                effective_workspace_id,
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
