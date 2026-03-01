# Needs: python-package:pyyaml>=6.0.1
"""Workspace-aware tool policy engine with deny-by-default semantics."""

from __future__ import annotations

import fnmatch
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml

logger = logging.getLogger(__name__)

SUPPORTED_ACTIONS = {"read", "write", "delete"}


@dataclass(frozen=True)
class ToolPolicyDecision:
    """Decision returned by tool policy validation."""

    allowed: bool
    reason: Optional[str]
    code: str = "PolicyDenied"
    workspace_id: Optional[str] = None
    timeout_seconds: Optional[float] = None


@dataclass
class WorkspaceToolPolicy:
    """Policy rules scoped to one workspace."""

    workspace_id: str
    allowed_mcp_servers: Set[str] = field(default_factory=set)
    allowed_tool_actions: Set[str] = field(default_factory=set)
    allowed_tool_names: Dict[str, Set[str]] = field(default_factory=dict)
    allowlists_global: Dict[str, List[str]] = field(default_factory=dict)
    allowlists_servers: Dict[str, Dict[str, List[str]]] = field(default_factory=dict)
    allowlists_tools: Dict[str, Dict[str, List[str]]] = field(default_factory=dict)
    max_tool_calls_per_request: int = 0
    per_call_timeout_seconds: Optional[float] = None

    def allowed_tools_for_action(self, action: str) -> Set[str]:
        """Return tools allowed for an action including wildcard bucket."""
        tools = set(self.allowed_tool_names.get("*", set()))
        tools.update(self.allowed_tool_names.get(action, set()))
        return tools

    def resolve_timeout(self, fallback_timeout_seconds: float) -> float:
        """Resolve effective timeout for a tool call."""
        if self.per_call_timeout_seconds and self.per_call_timeout_seconds > 0:
            return float(self.per_call_timeout_seconds)
        return float(fallback_timeout_seconds)


class ToolPolicyEngine:
    """Evaluate tool calls against workspace-scoped deny-by-default policies."""

    def __init__(
        self,
        workspace_policies: Dict[str, WorkspaceToolPolicy],
        default_workspace_id: Optional[str] = None,
        request_counter_ttl_seconds: int = 3600,
    ):
        self.workspace_policies = workspace_policies
        self.default_workspace_id = (default_workspace_id or "").strip() or None
        self.request_counter_ttl_seconds = request_counter_ttl_seconds
        self._request_call_counts: Dict[Tuple[str, str], Tuple[int, float]] = {}
        self._lock = threading.Lock()

    @classmethod
    def from_yaml(cls, config_path: str) -> "ToolPolicyEngine":
        """Load policy engine from YAML config file."""
        config_file = Path(config_path)
        if not config_file.exists():
            logger.warning(
                "Tool policy config not found at %s. Deny-by-default policy active.",
                config_path,
            )
            return cls(workspace_policies={})

        with config_file.open("r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle) or {}

        workspaces_payload = payload.get("workspaces", {}) or {}
        workspace_policies: Dict[str, WorkspaceToolPolicy] = {}
        for workspace_id, workspace_config in workspaces_payload.items():
            parsed = cls._parse_workspace_policy(
                workspace_id=str(workspace_id).strip(),
                config=workspace_config or {},
            )
            workspace_policies[parsed.workspace_id] = parsed

        return cls(
            workspace_policies=workspace_policies,
            default_workspace_id=payload.get("default_workspace"),
        )

    @staticmethod
    def _parse_workspace_policy(workspace_id: str, config: Dict[str, Any]) -> WorkspaceToolPolicy:
        if not workspace_id:
            raise ValueError("workspace_id cannot be empty in tool policy config")

        allowed_mcp_servers = _as_string_set(config.get("allowed_mcp_servers"))
        allowed_tool_actions = {action.lower() for action in _as_string_set(config.get("allowed_tool_actions"))}
        allowed_tool_names = _parse_allowed_tool_names(config.get("allowed_tool_names"))
        allowlists_global, allowlists_servers, allowlists_tools = _parse_allowlists(
            config.get("allowlists", {})
        )

        max_tool_calls_per_request = int(config.get("max_tool_calls_per_request", 0) or 0)
        per_call_timeout_seconds = config.get("per_call_timeout_seconds")
        timeout_value = (
            float(per_call_timeout_seconds)
            if per_call_timeout_seconds is not None
            else None
        )

        return WorkspaceToolPolicy(
            workspace_id=workspace_id,
            allowed_mcp_servers=allowed_mcp_servers,
            allowed_tool_actions=allowed_tool_actions,
            allowed_tool_names=allowed_tool_names,
            allowlists_global=allowlists_global,
            allowlists_servers=allowlists_servers,
            allowlists_tools=allowlists_tools,
            max_tool_calls_per_request=max_tool_calls_per_request,
            per_call_timeout_seconds=timeout_value,
        )

    def resolve_workspace_id(self, workspace_id: Optional[str]) -> Optional[str]:
        """Resolve workspace ID using explicit value or configured default."""
        normalized = (workspace_id or "").strip()
        if normalized:
            return normalized
        return self.default_workspace_id

    def evaluate_tool_call(
        self,
        *,
        workspace_id: Optional[str],
        request_id: Optional[str],
        server_id: str,
        tool_name: str,
        action: str,
        arguments: Optional[Dict[str, Any]],
        default_timeout_seconds: float,
    ) -> ToolPolicyDecision:
        """Validate a tool call and return allow/deny decision + effective timeout."""
        resolved_workspace = self.resolve_workspace_id(workspace_id)
        if not resolved_workspace:
            return ToolPolicyDecision(
                allowed=False,
                reason="workspace_id is required by tool policy",
                workspace_id=workspace_id,
            )

        workspace_policy = self.workspace_policies.get(resolved_workspace)
        if not workspace_policy:
            return ToolPolicyDecision(
                allowed=False,
                reason=f"no tool policy configured for workspace '{resolved_workspace}'",
                workspace_id=resolved_workspace,
            )

        normalized_action = _normalize_action(action)
        if (
            workspace_policy.allowed_tool_actions
            and "*" not in workspace_policy.allowed_tool_actions
            and normalized_action not in workspace_policy.allowed_tool_actions
        ):
            return ToolPolicyDecision(
                allowed=False,
                reason=(
                    f"action '{normalized_action}' is not allowed in workspace "
                    f"'{resolved_workspace}'"
                ),
                workspace_id=resolved_workspace,
            )

        if (
            "*" not in workspace_policy.allowed_mcp_servers
            and server_id not in workspace_policy.allowed_mcp_servers
        ):
            return ToolPolicyDecision(
                allowed=False,
                reason=(
                    f"MCP server '{server_id}' is not allowed in workspace "
                    f"'{resolved_workspace}'"
                ),
                workspace_id=resolved_workspace,
            )

        allowed_tools = workspace_policy.allowed_tools_for_action(normalized_action)
        if not allowed_tools:
            return ToolPolicyDecision(
                allowed=False,
                reason=(
                    f"no tools allowed for action '{normalized_action}' in workspace "
                    f"'{resolved_workspace}'"
                ),
                workspace_id=resolved_workspace,
            )
        if "*" not in allowed_tools and tool_name not in allowed_tools:
            return ToolPolicyDecision(
                allowed=False,
                reason=(
                    f"tool '{tool_name}' is not allowed for action '{normalized_action}' "
                    f"in workspace '{resolved_workspace}'"
                ),
                workspace_id=resolved_workspace,
            )

        allowlist_allowed, allowlist_reason = self._validate_allowlists(
            workspace_policy=workspace_policy,
            server_id=server_id,
            tool_name=tool_name,
            arguments=arguments or {},
        )
        if not allowlist_allowed:
            return ToolPolicyDecision(
                allowed=False,
                reason=allowlist_reason,
                workspace_id=resolved_workspace,
            )

        quota_allowed, quota_reason = self._validate_request_quota(
            workspace_policy=workspace_policy,
            workspace_id=resolved_workspace,
            request_id=request_id,
        )
        if not quota_allowed:
            return ToolPolicyDecision(
                allowed=False,
                reason=quota_reason,
                workspace_id=resolved_workspace,
            )

        return ToolPolicyDecision(
            allowed=True,
            reason=None,
            workspace_id=resolved_workspace,
            timeout_seconds=workspace_policy.resolve_timeout(default_timeout_seconds),
        )

    def _validate_allowlists(
        self,
        *,
        workspace_policy: WorkspaceToolPolicy,
        server_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> Tuple[bool, Optional[str]]:
        constraints: Dict[str, Set[str]] = {}

        for arg_name, patterns in workspace_policy.allowlists_global.items():
            constraints.setdefault(arg_name, set()).update(patterns)

        for arg_name, patterns in workspace_policy.allowlists_servers.get(server_id, {}).items():
            constraints.setdefault(arg_name, set()).update(patterns)

        for arg_name, patterns in workspace_policy.allowlists_tools.get(tool_name, {}).items():
            constraints.setdefault(arg_name, set()).update(patterns)

        if not constraints:
            return True, None

        for arg_name, patterns in constraints.items():
            if arg_name not in arguments:
                continue

            values = _extract_argument_values(arguments[arg_name])
            if not values:
                continue

            for value in values:
                if not any(fnmatch.fnmatch(value, pattern) for pattern in patterns):
                    return (
                        False,
                        f"argument '{arg_name}' value '{value}' is outside allowlist",
                    )

        return True, None

    def _validate_request_quota(
        self,
        *,
        workspace_policy: WorkspaceToolPolicy,
        workspace_id: str,
        request_id: Optional[str],
    ) -> Tuple[bool, Optional[str]]:
        max_calls = workspace_policy.max_tool_calls_per_request
        if max_calls <= 0:
            return True, None

        # Request-scoped quota is only enforceable when request_id is available.
        if not request_id:
            return True, None

        now = time.time()
        key = (workspace_id, request_id)

        with self._lock:
            self._cleanup_stale_request_counters(now)
            current_count, _ = self._request_call_counts.get(key, (0, now))
            if current_count >= max_calls:
                return (
                    False,
                    (
                        f"max tool calls per request exceeded ({max_calls}) "
                        f"for request '{request_id}'"
                    ),
                )
            self._request_call_counts[key] = (current_count + 1, now)

        return True, None

    def _cleanup_stale_request_counters(self, now: float) -> None:
        cutoff = now - self.request_counter_ttl_seconds
        stale_keys = [key for key, (_, ts) in self._request_call_counts.items() if ts < cutoff]
        for key in stale_keys:
            self._request_call_counts.pop(key, None)


def load_default_tool_policy_engine() -> ToolPolicyEngine:
    """Load tool policy engine from default path or MCP_TOOL_POLICY_CONFIG."""
    config_path = os.getenv("MCP_TOOL_POLICY_CONFIG", "configs/tool-policy.yaml")
    return ToolPolicyEngine.from_yaml(config_path)


def _as_string_set(raw_values: Any) -> Set[str]:
    if raw_values is None:
        return set()
    if isinstance(raw_values, str):
        values = [raw_values]
    elif isinstance(raw_values, (list, tuple, set)):
        values = list(raw_values)
    else:
        values = [raw_values]
    return {str(value).strip() for value in values if str(value).strip()}


def _parse_allowed_tool_names(raw_tool_names: Any) -> Dict[str, Set[str]]:
    if not raw_tool_names:
        return {}

    if isinstance(raw_tool_names, list):
        return {"*": _as_string_set(raw_tool_names)}

    if not isinstance(raw_tool_names, dict):
        return {}

    parsed: Dict[str, Set[str]] = {}
    for action, names in raw_tool_names.items():
        raw_action = str(action).strip().lower()
        normalized_action = "*" if raw_action == "*" else _normalize_action(raw_action)
        parsed[normalized_action] = _as_string_set(names)
    return parsed


def _parse_allowlists(raw_allowlists: Any) -> Tuple[
    Dict[str, List[str]],
    Dict[str, Dict[str, List[str]]],
    Dict[str, Dict[str, List[str]]],
]:
    if not isinstance(raw_allowlists, dict):
        return {}, {}, {}

    allowlists_global = _normalize_allowlist_map(raw_allowlists.get("global", {}))

    server_allowlists: Dict[str, Dict[str, List[str]]] = {}
    for server_id, allowlist_map in (raw_allowlists.get("servers", {}) or {}).items():
        server_allowlists[str(server_id)] = _normalize_allowlist_map(allowlist_map)

    tool_allowlists: Dict[str, Dict[str, List[str]]] = {}
    for tool_name, allowlist_map in (raw_allowlists.get("tools", {}) or {}).items():
        tool_allowlists[str(tool_name)] = _normalize_allowlist_map(allowlist_map)

    return allowlists_global, server_allowlists, tool_allowlists


def _normalize_allowlist_map(raw_map: Any) -> Dict[str, List[str]]:
    if not isinstance(raw_map, dict):
        return {}

    normalized: Dict[str, List[str]] = {}
    for key, raw_patterns in raw_map.items():
        patterns = _as_pattern_list(raw_patterns)
        if patterns:
            normalized[str(key)] = patterns
    return normalized


def _as_pattern_list(raw_patterns: Any) -> List[str]:
    if raw_patterns is None:
        return []
    if isinstance(raw_patterns, str):
        patterns = [raw_patterns]
    elif isinstance(raw_patterns, list):
        patterns = raw_patterns
    else:
        return []
    return [str(pattern).strip() for pattern in patterns if str(pattern).strip()]


def _extract_argument_values(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (str, int, float, bool)):
        return [str(value)]
    if isinstance(value, (list, tuple, set)):
        collected: List[str] = []
        for item in value:
            collected.extend(_extract_argument_values(item))
        return collected
    return []


def _normalize_action(action: str) -> str:
    normalized = (action or "").strip().lower()
    if normalized in SUPPORTED_ACTIONS:
        return normalized
    return "read"
