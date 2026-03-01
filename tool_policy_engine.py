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
SUPPORTED_ROLES = {"admin", "developer", "viewer"}


@dataclass(frozen=True)
class ToolPolicyDecision:
    """Decision returned by tool policy validation."""

    allowed: bool
    reason: Optional[str]
    code: str = "PolicyDenied"
    workspace_id: Optional[str] = None
    timeout_seconds: Optional[float] = None


@dataclass
class WorkspaceRolePolicy:
    """Role-scoped tool permissions inside a workspace policy."""

    role: str
    allowed_tool_actions: Set[str] = field(default_factory=set)
    allowed_tool_names: Dict[str, Set[str]] = field(default_factory=dict)
    required_scopes_by_action: Dict[str, Set[str]] = field(default_factory=dict)

    def allowed_tools_for_action(self, action: str) -> Set[str]:
        """Return tools allowed for an action including wildcard bucket."""
        tools = set(self.allowed_tool_names.get("*", set()))
        tools.update(self.allowed_tool_names.get(action, set()))
        return tools

    def required_scopes_for_action(self, action: str) -> Set[str]:
        """Return required scopes for an action including wildcard bucket."""
        scopes = set(self.required_scopes_by_action.get("*", set()))
        scopes.update(self.required_scopes_by_action.get(action, set()))
        return scopes

    def to_dict(self) -> Dict[str, Any]:
        """Serialize role policy to stable dictionary form."""
        return {
            "allowed_tool_actions": sorted(self.allowed_tool_actions),
            "tool_scopes": {
                action: sorted(tool_names)
                for action, tool_names in sorted(self.allowed_tool_names.items())
            },
            "required_scopes": {
                action: sorted(scopes)
                for action, scopes in sorted(self.required_scopes_by_action.items())
            },
        }


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
    default_role: str = "viewer"
    role_policies: Dict[str, WorkspaceRolePolicy] = field(default_factory=dict)
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

    def get_role_policy(self, role: str) -> Optional[WorkspaceRolePolicy]:
        """Return normalized role policy when workspace has RBAC rules."""
        normalized_role = _normalize_role(role)
        if not self.role_policies:
            return None
        return self.role_policies.get(normalized_role)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize workspace policy to stable dictionary form."""
        payload: Dict[str, Any] = {
            "allowed_mcp_servers": sorted(self.allowed_mcp_servers),
            "allowed_tool_actions": sorted(self.allowed_tool_actions),
            "allowed_tool_names": {
                action: sorted(tool_names)
                for action, tool_names in sorted(self.allowed_tool_names.items())
            },
            "allowlists": {
                "global": self.allowlists_global,
                "servers": self.allowlists_servers,
                "tools": self.allowlists_tools,
            },
            "max_tool_calls_per_request": self.max_tool_calls_per_request,
            "per_call_timeout_seconds": self.per_call_timeout_seconds,
        }
        if self.role_policies:
            payload["default_role"] = self.default_role
            payload["roles"] = {
                role: role_policy.to_dict()
                for role, role_policy in sorted(self.role_policies.items())
            }
        return payload


class ToolPolicyEngine:
    """Evaluate tool calls against workspace-scoped deny-by-default policies."""

    def __init__(
        self,
        workspace_policies: Dict[str, WorkspaceToolPolicy],
        default_workspace_id: Optional[str] = None,
        default_role: str = "viewer",
        request_counter_ttl_seconds: int = 3600,
    ):
        self.workspace_policies = workspace_policies
        self.default_workspace_id = (default_workspace_id or "").strip() or None
        self.default_role = _normalize_supported_role(default_role, fallback="viewer")
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
        global_default_role = payload.get("default_role", "viewer")
        workspace_policies: Dict[str, WorkspaceToolPolicy] = {}
        for workspace_id, workspace_config in workspaces_payload.items():
            parsed = cls._parse_workspace_policy(
                workspace_id=str(workspace_id).strip(),
                config=workspace_config or {},
                fallback_default_role=global_default_role,
            )
            workspace_policies[parsed.workspace_id] = parsed

        return cls(
            workspace_policies=workspace_policies,
            default_workspace_id=payload.get("default_workspace"),
            default_role=global_default_role,
        )

    @staticmethod
    def _parse_workspace_policy(
        workspace_id: str,
        config: Dict[str, Any],
        fallback_default_role: str = "viewer",
    ) -> WorkspaceToolPolicy:
        if not workspace_id:
            raise ValueError("workspace_id cannot be empty in tool policy config")

        allowed_mcp_servers = _as_string_set(config.get("allowed_mcp_servers"))
        allowed_tool_actions = {action.lower() for action in _as_string_set(config.get("allowed_tool_actions"))}
        allowed_tool_names = _parse_allowed_tool_names(config.get("allowed_tool_names"))
        role_policies = _parse_role_policies(config.get("roles", {}))
        default_role = _normalize_supported_role(
            config.get("default_role", fallback_default_role),
            fallback="viewer",
        )
        if role_policies and default_role not in role_policies:
            raise ValueError(
                f"default_role '{default_role}' is not declared in roles for workspace '{workspace_id}'"
            )
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
            default_role=default_role,
            role_policies=role_policies,
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
        role: Optional[str] = None,
        scopes: Optional[List[str]] = None,
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
        normalized_role = _normalize_role(role or workspace_policy.default_role or self.default_role)
        normalized_scopes = _as_string_set(scopes or [])

        role_policy = workspace_policy.get_role_policy(normalized_role)
        if workspace_policy.role_policies and not role_policy:
            return ToolPolicyDecision(
                allowed=False,
                reason=(
                    f"role '{normalized_role}' is not configured for workspace "
                    f"'{resolved_workspace}'"
                ),
                workspace_id=resolved_workspace,
            )

        role_allowed_actions = (
            role_policy.allowed_tool_actions if role_policy else workspace_policy.allowed_tool_actions
        )
        if (
            role_allowed_actions
            and "*" not in role_allowed_actions
            and normalized_action not in role_allowed_actions
        ):
            role_context = (
                f" for role '{normalized_role}'"
                if workspace_policy.role_policies
                else ""
            )
            return ToolPolicyDecision(
                allowed=False,
                reason=(
                    f"action '{normalized_action}' is not allowed{role_context} in workspace "
                    f"'{resolved_workspace}'"
                ),
                workspace_id=resolved_workspace,
            )

        if role_policy and normalized_role == "developer" and normalized_action in {"write", "delete"}:
            developer_tool_scope = role_policy.allowed_tools_for_action(normalized_action)
            if not developer_tool_scope:
                return ToolPolicyDecision(
                    allowed=False,
                    reason=(
                        "developer role requires explicit tool scope for "
                        f"'{normalized_action}' in workspace '{resolved_workspace}'"
                    ),
                    workspace_id=resolved_workspace,
                )

            required_scopes = role_policy.required_scopes_for_action(normalized_action)
            if not required_scopes:
                return ToolPolicyDecision(
                    allowed=False,
                    reason=(
                        "developer role requires explicit security scope for "
                        f"'{normalized_action}' in workspace '{resolved_workspace}'"
                    ),
                    workspace_id=resolved_workspace,
                )
            missing_scopes = required_scopes - normalized_scopes
            if missing_scopes:
                return ToolPolicyDecision(
                    allowed=False,
                    reason=(
                        f"missing required scope(s) {sorted(missing_scopes)} for role "
                        f"'{normalized_role}' in workspace '{resolved_workspace}'"
                    ),
                    workspace_id=resolved_workspace,
                )
        elif role_policy:
            required_scopes = role_policy.required_scopes_for_action(normalized_action)
            missing_scopes = required_scopes - normalized_scopes
            if missing_scopes:
                return ToolPolicyDecision(
                    allowed=False,
                    reason=(
                        f"missing required scope(s) {sorted(missing_scopes)} for role "
                        f"'{normalized_role}' in workspace '{resolved_workspace}'"
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

        allowed_tools = (
            role_policy.allowed_tools_for_action(normalized_action)
            if role_policy
            else workspace_policy.allowed_tools_for_action(normalized_action)
        )
        if not allowed_tools:
            role_context = (
                f" for role '{normalized_role}'"
                if role_policy
                else ""
            )
            return ToolPolicyDecision(
                allowed=False,
                reason=(
                    f"no tools allowed for action '{normalized_action}'{role_context} in workspace "
                    f"'{resolved_workspace}'"
                ),
                workspace_id=resolved_workspace,
            )
        if "*" not in allowed_tools and tool_name not in allowed_tools:
            role_context = (
                f" for role '{normalized_role}'"
                if role_policy
                else ""
            )
            return ToolPolicyDecision(
                allowed=False,
                reason=(
                    f"tool '{tool_name}' is not allowed for action '{normalized_action}' "
                    f"{role_context} in workspace '{resolved_workspace}'"
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

    def get_workspace_policy(self, workspace_id: str) -> Dict[str, Any]:
        """Return serialized workspace policy payload."""
        normalized_workspace = (workspace_id or "").strip()
        if not normalized_workspace:
            raise ValueError("workspace_id is required")
        workspace_policy = self.workspace_policies.get(normalized_workspace)
        if not workspace_policy:
            raise KeyError(normalized_workspace)
        return workspace_policy.to_dict()

    def upsert_workspace_policy(self, workspace_id: str, policy_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Create/update workspace policy and return serialized snapshot."""
        normalized_workspace = (workspace_id or "").strip()
        if not normalized_workspace:
            raise ValueError("workspace_id is required")
        parsed = self._parse_workspace_policy(
            workspace_id=normalized_workspace,
            config=policy_payload or {},
            fallback_default_role=self.default_role,
        )
        with self._lock:
            self.workspace_policies[normalized_workspace] = parsed
        return parsed.to_dict()


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


def _parse_required_scopes(raw_required_scopes: Any) -> Dict[str, Set[str]]:
    if not raw_required_scopes:
        return {}

    if isinstance(raw_required_scopes, (list, tuple, set, str)):
        return {"*": _as_string_set(raw_required_scopes)}

    if not isinstance(raw_required_scopes, dict):
        return {}

    parsed: Dict[str, Set[str]] = {}
    for raw_action, raw_scopes in raw_required_scopes.items():
        action = str(raw_action).strip().lower()
        normalized_action = "*" if action == "*" else _normalize_action(action)
        parsed[normalized_action] = _as_string_set(raw_scopes)
    return parsed


def _parse_role_policies(raw_roles: Any) -> Dict[str, WorkspaceRolePolicy]:
    if not isinstance(raw_roles, dict):
        return {}

    parsed: Dict[str, WorkspaceRolePolicy] = {}
    for raw_role, raw_role_policy in raw_roles.items():
        role = _normalize_role(raw_role)
        if role not in SUPPORTED_ROLES:
            raise ValueError(
                f"unsupported role '{raw_role}'. Allowed roles: {sorted(SUPPORTED_ROLES)}"
            )
        role_config = raw_role_policy if isinstance(raw_role_policy, dict) else {}
        allowed_tool_actions = {
            action.lower()
            for action in _as_string_set(role_config.get("allowed_tool_actions"))
        }

        allowed_tool_names = _parse_allowed_tool_names(role_config.get("allowed_tool_names"))
        tool_scopes = _parse_allowed_tool_names(role_config.get("tool_scopes"))
        for action, tool_names in tool_scopes.items():
            allowed_tool_names.setdefault(action, set()).update(tool_names)

        if not allowed_tool_actions:
            allowed_tool_actions = {action for action in allowed_tool_names.keys() if action != "*"}

        parsed[role] = WorkspaceRolePolicy(
            role=role,
            allowed_tool_actions=allowed_tool_actions,
            allowed_tool_names=allowed_tool_names,
            required_scopes_by_action=_parse_required_scopes(role_config.get("required_scopes")),
        )

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


def _normalize_role(role: Any) -> str:
    return str(role or "").strip().lower()


def _normalize_supported_role(role: Any, fallback: str = "viewer") -> str:
    normalized = _normalize_role(role)
    if normalized in SUPPORTED_ROLES:
        return normalized
    return fallback
