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
SUPPORTED_POLICY_VERSION = 1


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
class ToolRedactionRule:
    """Argument-level redaction rule scoped by workspace policy."""

    argument: str
    patterns: List[str] = field(default_factory=list)
    replacement: str = "[REDACTED]"

    def applies_to(self, argument_name: str, value: str) -> bool:
        if argument_name != self.argument:
            return False
        return any(fnmatch.fnmatch(value, pattern) for pattern in self.patterns)

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
    redaction_rules: List[ToolRedactionRule] = field(default_factory=list)

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
            "redaction_rules": [
                {
                    "argument": rule.argument,
                    "patterns": list(rule.patterns),
                    "replacement": rule.replacement,
                }
                for rule in self.redaction_rules
            ],
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

        try:
            with config_file.open("r", encoding="utf-8") as handle:
                raw_payload = yaml.safe_load(handle)
        except OSError as exc:
            raise ValueError(f"unable to read tool policy config at '{config_path}': {exc}") from exc
        except yaml.YAMLError as exc:
            raise ValueError(f"invalid YAML in tool policy config '{config_path}': {exc}") from exc

        payload = _ensure_mapping(raw_payload or {}, field_name="tool policy document")
        _validate_policy_version(payload.get("version"))

        workspaces_payload = _ensure_mapping(
            payload.get("workspaces", {}),
            field_name="workspaces",
        )
        global_default_role = _parse_supported_role(
            payload.get("default_role"),
            field_name="default_role",
            fallback="viewer",
        )
        workspace_policies: Dict[str, WorkspaceToolPolicy] = {}
        for workspace_id, workspace_config in workspaces_payload.items():
            if not isinstance(workspace_id, str):
                raise ValueError("workspaces keys must be strings")
            normalized_workspace_id = workspace_id.strip()
            if not normalized_workspace_id:
                raise ValueError("workspaces keys must be non-empty strings")
            parsed = cls._parse_workspace_policy(
                workspace_id=normalized_workspace_id,
                config=_ensure_mapping(
                    workspace_config,
                    field_name=f"workspaces.{normalized_workspace_id}",
                ),
                fallback_default_role=global_default_role,
            )
            workspace_policies[parsed.workspace_id] = parsed

        default_workspace_raw = payload.get("default_workspace")
        default_workspace = None
        if default_workspace_raw is not None:
            if not isinstance(default_workspace_raw, str):
                raise ValueError("default_workspace must be a string when provided")
            default_workspace = default_workspace_raw.strip() or None
            if default_workspace and default_workspace not in workspace_policies:
                raise ValueError(
                    f"default_workspace '{default_workspace}' is not declared in workspaces"
                )

        return cls(
            workspace_policies=workspace_policies,
            default_workspace_id=default_workspace,
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

        allowed_mcp_servers = _parse_string_set(
            config.get("allowed_mcp_servers"),
            field_name=f"workspaces.{workspace_id}.allowed_mcp_servers",
        )
        allowed_tool_actions = _parse_action_set(
            config.get("allowed_tool_actions"),
            field_name=f"workspaces.{workspace_id}.allowed_tool_actions",
        )
        allowed_tool_names = _parse_allowed_tool_names(
            config.get("allowed_tool_names"),
            field_name=f"workspaces.{workspace_id}.allowed_tool_names",
        )
        role_policies = _parse_role_policies(
            config.get("roles"),
            field_name=f"workspaces.{workspace_id}.roles",
        )
        default_role = _parse_supported_role(
            config.get("default_role"),
            field_name=f"workspaces.{workspace_id}.default_role",
            fallback=fallback_default_role,
        )
        if role_policies and default_role not in role_policies:
            raise ValueError(
                f"default_role '{default_role}' is not declared in roles for workspace '{workspace_id}'"
            )
        allowlists_global, allowlists_servers, allowlists_tools = _parse_allowlists(
            config.get("allowlists"),
            field_name=f"workspaces.{workspace_id}.allowlists",
        )

        max_tool_calls_per_request = _parse_non_negative_int(
            config.get("max_tool_calls_per_request", 0),
            field_name=f"workspaces.{workspace_id}.max_tool_calls_per_request",
        )
        timeout_value = _parse_optional_timeout_seconds(
            config.get("per_call_timeout_seconds"),
            field_name=f"workspaces.{workspace_id}.per_call_timeout_seconds",
        )
        redaction_rules = _parse_redaction_rules(
            config.get("redaction_rules"),
            field_name=f"workspaces.{workspace_id}.redaction_rules",
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
            redaction_rules=redaction_rules,
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

        try:
            normalized_action = _normalize_action(action)
        except ValueError:
            return ToolPolicyDecision(
                allowed=False,
                reason=(
                    f"unsupported action '{action}'. Allowed actions: "
                    f"{sorted(SUPPORTED_ACTIONS)}"
                ),
                workspace_id=resolved_workspace,
            )
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

    def redact_tool_arguments(
        self,
        *,
        workspace_id: Optional[str],
        server_id: str,
        tool_name: str,
        arguments: Optional[Dict[str, Any]],
    ) -> Tuple[Dict[str, Any], int]:
        """Apply workspace redaction rules to argument payloads for auditing."""
        payload = dict(arguments or {})
        resolved_workspace = self.resolve_workspace_id(workspace_id)
        if not resolved_workspace:
            return payload, 0
        workspace_policy = self.workspace_policies.get(resolved_workspace)
        if not workspace_policy or not workspace_policy.redaction_rules:
            return payload, 0

        redacted_payload = dict(payload)
        redactions = 0
        for rule in workspace_policy.redaction_rules:
            if rule.argument not in redacted_payload:
                continue
            values = _extract_argument_values(redacted_payload[rule.argument])
            if not values:
                continue
            if any(any(fnmatch.fnmatch(value, pattern) for pattern in rule.patterns) for value in values):
                redacted_payload[rule.argument] = rule.replacement
                redactions += 1

        return redacted_payload, redactions

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
    try:
        return ToolPolicyEngine.from_yaml(config_path)
    except ValueError as exc:
        logger.error(
            "Failed to load tool policy config at %s (%s). Deny-by-default policy active.",
            config_path,
            exc,
        )
        return ToolPolicyEngine(workspace_policies={})


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


def _validate_policy_version(raw_version: Any) -> None:
    if raw_version is None:
        return
    if isinstance(raw_version, bool) or not isinstance(raw_version, int):
        raise ValueError("version must be an integer")
    if raw_version != SUPPORTED_POLICY_VERSION:
        raise ValueError(
            f"unsupported tool policy version '{raw_version}'. "
            f"Supported versions: [{SUPPORTED_POLICY_VERSION}]"
        )


def _ensure_mapping(raw_value: Any, *, field_name: str, allow_none: bool = True) -> Dict[str, Any]:
    if raw_value is None and allow_none:
        return {}
    if not isinstance(raw_value, dict):
        raise ValueError(f"{field_name} must be a mapping")
    return raw_value


def _parse_string_set(raw_values: Any, *, field_name: str) -> Set[str]:
    if raw_values is None:
        return set()
    if isinstance(raw_values, str):
        normalized = raw_values.strip()
        return {normalized} if normalized else set()
    if not isinstance(raw_values, (list, tuple, set)):
        raise ValueError(f"{field_name} must be a string or a list of strings")

    normalized_values: Set[str] = set()
    for index, value in enumerate(raw_values):
        if not isinstance(value, str):
            raise ValueError(f"{field_name}[{index}] must be a string")
        normalized = value.strip()
        if normalized:
            normalized_values.add(normalized)
    return normalized_values


def _parse_action_set(raw_actions: Any, *, field_name: str) -> Set[str]:
    normalized_actions: Set[str] = set()
    for raw_action in _parse_string_set(raw_actions, field_name=field_name):
        lowered_action = raw_action.lower()
        if lowered_action == "*":
            normalized_actions.add("*")
            continue
        normalized_actions.add(_normalize_action(lowered_action))
    return normalized_actions


def _parse_supported_role(role: Any, *, field_name: str, fallback: str) -> str:
    if role is None:
        return fallback
    normalized = _normalize_role(role)
    if normalized in SUPPORTED_ROLES:
        return normalized
    raise ValueError(f"unsupported role '{role}' in {field_name}. Allowed roles: {sorted(SUPPORTED_ROLES)}")


def _parse_non_negative_int(raw_value: Any, *, field_name: str) -> int:
    if raw_value is None:
        return 0
    if isinstance(raw_value, bool):
        raise ValueError(f"{field_name} must be a non-negative integer")
    try:
        parsed = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a non-negative integer") from exc
    if parsed < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return parsed


def _parse_optional_timeout_seconds(raw_value: Any, *, field_name: str) -> Optional[float]:
    if raw_value is None:
        return None
    if isinstance(raw_value, bool):
        raise ValueError(f"{field_name} must be a number")
    try:
        parsed = float(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a number") from exc
    if parsed < 0:
        raise ValueError(f"{field_name} must be greater than or equal to zero")
    if parsed == 0:
        return None
    return parsed


def _parse_allowed_tool_names(raw_tool_names: Any, *, field_name: str) -> Dict[str, Set[str]]:
    if raw_tool_names is None:
        return {}

    if isinstance(raw_tool_names, (str, list, tuple, set)):
        return {"*": _parse_string_set(raw_tool_names, field_name=field_name)}

    if not isinstance(raw_tool_names, dict):
        raise ValueError(
            f"{field_name} must be a mapping of action->tool names or a list of tool names"
        )

    parsed: Dict[str, Set[str]] = {}
    for action, names in raw_tool_names.items():
        if not isinstance(action, str):
            raise ValueError(f"{field_name} keys must be strings")
        raw_action = action.strip().lower()
        if not raw_action:
            raise ValueError(f"{field_name} action keys must be non-empty")
        normalized_action = "*" if raw_action == "*" else _normalize_action(raw_action)
        parsed[normalized_action] = _parse_string_set(
            names,
            field_name=f"{field_name}.{raw_action}",
        )
    return parsed


def _parse_required_scopes(raw_required_scopes: Any, *, field_name: str) -> Dict[str, Set[str]]:
    if not raw_required_scopes:
        return {}

    if isinstance(raw_required_scopes, (list, tuple, set, str)):
        return {"*": _parse_string_set(raw_required_scopes, field_name=field_name)}

    if not isinstance(raw_required_scopes, dict):
        raise ValueError(
            f"{field_name} must be a mapping of action->scope names or a list of scope names"
        )

    parsed: Dict[str, Set[str]] = {}
    for raw_action, raw_scopes in raw_required_scopes.items():
        if not isinstance(raw_action, str):
            raise ValueError(f"{field_name} keys must be strings")
        action = raw_action.strip().lower()
        if not action:
            raise ValueError(f"{field_name} action keys must be non-empty")
        normalized_action = "*" if action == "*" else _normalize_action(action)
        parsed[normalized_action] = _parse_string_set(
            raw_scopes,
            field_name=f"{field_name}.{action}",
        )
    return parsed


def _parse_role_policies(raw_roles: Any, *, field_name: str) -> Dict[str, WorkspaceRolePolicy]:
    if raw_roles is None:
        return {}
    if not isinstance(raw_roles, dict):
        raise ValueError(f"{field_name} must be a mapping")

    parsed: Dict[str, WorkspaceRolePolicy] = {}
    for raw_role, raw_role_policy in raw_roles.items():
        if not isinstance(raw_role, str):
            raise ValueError(f"{field_name} keys must be strings")
        role = _normalize_role(raw_role)
        if role not in SUPPORTED_ROLES:
            raise ValueError(
                f"unsupported role '{raw_role}'. Allowed roles: {sorted(SUPPORTED_ROLES)}"
            )
        if raw_role_policy is None:
            role_config: Dict[str, Any] = {}
        elif isinstance(raw_role_policy, dict):
            role_config = raw_role_policy
        else:
            raise ValueError(f"{field_name}.{role} must be a mapping")

        allowed_tool_actions = _parse_action_set(
            role_config.get("allowed_tool_actions"),
            field_name=f"{field_name}.{role}.allowed_tool_actions",
        )

        allowed_tool_names = _parse_allowed_tool_names(
            role_config.get("allowed_tool_names"),
            field_name=f"{field_name}.{role}.allowed_tool_names",
        )
        tool_scopes = _parse_allowed_tool_names(
            role_config.get("tool_scopes"),
            field_name=f"{field_name}.{role}.tool_scopes",
        )
        for action, tool_names in tool_scopes.items():
            allowed_tool_names.setdefault(action, set()).update(tool_names)

        if not allowed_tool_actions:
            allowed_tool_actions = {action for action in allowed_tool_names.keys() if action != "*"}

        parsed[role] = WorkspaceRolePolicy(
            role=role,
            allowed_tool_actions=allowed_tool_actions,
            allowed_tool_names=allowed_tool_names,
            required_scopes_by_action=_parse_required_scopes(
                role_config.get("required_scopes"),
                field_name=f"{field_name}.{role}.required_scopes",
            ),
        )

    return parsed


def _parse_redaction_rules(raw_rules: Any, *, field_name: str) -> List[ToolRedactionRule]:
    if raw_rules is None:
        return []
    if not isinstance(raw_rules, list):
        raise ValueError(f"{field_name} must be a list")

    parsed: List[ToolRedactionRule] = []
    for index, raw_rule in enumerate(raw_rules):
        if not isinstance(raw_rule, dict):
            raise ValueError(f"{field_name}[{index}] must be a mapping")
        argument = raw_rule.get("argument")
        if not isinstance(argument, str) or not argument.strip():
            raise ValueError(f"{field_name}[{index}].argument must be a non-empty string")
        patterns = _as_pattern_list(
            raw_rule.get("patterns"),
            field_name=f"{field_name}[{index}].patterns",
        )
        if not patterns:
            raise ValueError(f"{field_name}[{index}].patterns must include at least one pattern")
        replacement = raw_rule.get("replacement", "[REDACTED]")
        if not isinstance(replacement, str):
            raise ValueError(f"{field_name}[{index}].replacement must be a string")
        parsed.append(
            ToolRedactionRule(
                argument=argument.strip(),
                patterns=patterns,
                replacement=replacement,
            )
        )
    return parsed


def _parse_allowlists(raw_allowlists: Any, *, field_name: str) -> Tuple[
    Dict[str, List[str]],
    Dict[str, Dict[str, List[str]]],
    Dict[str, Dict[str, List[str]]],
]:
    if raw_allowlists is None:
        return {}, {}, {}
    if not isinstance(raw_allowlists, dict):
        raise ValueError(f"{field_name} must be a mapping")

    allowlists_global = _normalize_allowlist_map(
        raw_allowlists.get("global", {}),
        field_name=f"{field_name}.global",
    )

    raw_server_allowlists = _ensure_mapping(
        raw_allowlists.get("servers", {}),
        field_name=f"{field_name}.servers",
    )
    server_allowlists: Dict[str, Dict[str, List[str]]] = {}
    for server_id, allowlist_map in raw_server_allowlists.items():
        if not isinstance(server_id, str):
            raise ValueError(f"{field_name}.servers keys must be strings")
        normalized_server_id = server_id.strip()
        if not normalized_server_id:
            raise ValueError(f"{field_name}.servers keys must be non-empty strings")
        server_allowlists[normalized_server_id] = _normalize_allowlist_map(
            allowlist_map,
            field_name=f"{field_name}.servers.{normalized_server_id}",
        )

    raw_tool_allowlists = _ensure_mapping(
        raw_allowlists.get("tools", {}),
        field_name=f"{field_name}.tools",
    )
    tool_allowlists: Dict[str, Dict[str, List[str]]] = {}
    for tool_name, allowlist_map in raw_tool_allowlists.items():
        if not isinstance(tool_name, str):
            raise ValueError(f"{field_name}.tools keys must be strings")
        normalized_tool_name = tool_name.strip()
        if not normalized_tool_name:
            raise ValueError(f"{field_name}.tools keys must be non-empty strings")
        tool_allowlists[normalized_tool_name] = _normalize_allowlist_map(
            allowlist_map,
            field_name=f"{field_name}.tools.{normalized_tool_name}",
        )

    return allowlists_global, server_allowlists, tool_allowlists


def _normalize_allowlist_map(raw_map: Any, *, field_name: str) -> Dict[str, List[str]]:
    if raw_map is None:
        return {}
    if not isinstance(raw_map, dict):
        raise ValueError(f"{field_name} must be a mapping")

    normalized: Dict[str, List[str]] = {}
    for key, raw_patterns in raw_map.items():
        if not isinstance(key, str):
            raise ValueError(f"{field_name} keys must be strings")
        normalized_key = key.strip()
        if not normalized_key:
            raise ValueError(f"{field_name} keys must be non-empty strings")
        patterns = _as_pattern_list(
            raw_patterns,
            field_name=f"{field_name}.{normalized_key}",
        )
        if patterns:
            normalized[normalized_key] = patterns
    return normalized


def _as_pattern_list(raw_patterns: Any, *, field_name: str) -> List[str]:
    if raw_patterns is None:
        return []
    if isinstance(raw_patterns, str):
        patterns = [raw_patterns]
    elif isinstance(raw_patterns, (list, tuple, set)):
        patterns = list(raw_patterns)
    else:
        raise ValueError(f"{field_name} must be a string or a list of strings")
    normalized_patterns: List[str] = []
    for index, pattern in enumerate(patterns):
        if not isinstance(pattern, str):
            raise ValueError(f"{field_name}[{index}] must be a string")
        normalized = pattern.strip()
        if normalized:
            normalized_patterns.append(normalized)
    return normalized_patterns


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
    raise ValueError(
        f"unsupported action '{action}'. Allowed actions: {sorted(SUPPORTED_ACTIONS)}"
    )


def _normalize_role(role: Any) -> str:
    return str(role or "").strip().lower()


def _normalize_supported_role(role: Any, fallback: str = "viewer") -> str:
    normalized = _normalize_role(role)
    if normalized in SUPPORTED_ROLES:
        return normalized
    return fallback
