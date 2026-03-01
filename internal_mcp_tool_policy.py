#!/usr/bin/env python3
"""Shared policy evaluation for internal MCP tool proxy calls."""

from dataclasses import dataclass
from typing import Optional, Set


@dataclass(frozen=True)
class MCPToolPolicyDecision:
    """Outcome of a tool-call policy evaluation."""

    allowed: bool
    reason: Optional[str] = None


def parse_allowed_tools(allowed_tools_raw: Optional[str]) -> Set[str]:
    """Parse comma-separated tool names into a normalized allowlist set."""
    if not allowed_tools_raw:
        return set()
    return {
        candidate.strip()
        for candidate in allowed_tools_raw.split(",")
        if candidate and candidate.strip()
    }


def evaluate_tool_policy(tool_name: str, allowed_tools_raw: Optional[str]) -> MCPToolPolicyDecision:
    """
    Evaluate whether an MCP tool call is allowed.

    Policy semantics:
    - Empty allowlist => allow all tools
    - "*" in allowlist => allow all tools
    - Otherwise, tool must be explicitly listed
    """
    normalized_tool_name = (tool_name or "").strip()
    if not normalized_tool_name:
        return MCPToolPolicyDecision(allowed=False, reason="Missing required field: tool_name")

    allowed_tools = parse_allowed_tools(allowed_tools_raw)
    if not allowed_tools or "*" in allowed_tools:
        return MCPToolPolicyDecision(allowed=True)

    if normalized_tool_name in allowed_tools:
        return MCPToolPolicyDecision(allowed=True)

    return MCPToolPolicyDecision(
        allowed=False,
        reason=f"Tool '{normalized_tool_name}' is not allowed for API-routed MCP calls",
    )
