#!/usr/bin/env python3
"""Write-action confirmation helpers for MCP tool calls."""

from __future__ import annotations

import copy
import re
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, Optional


WRITE_CONFIRMATION_VERBS = frozenset({"create", "update", "add", "append", "post"})
READ_ONLY_VERBS = frozenset({"list", "get", "search", "read", "fetch", "query"})
COMMENT_VERBS = frozenset({"comment"})
TOKEN_SPLIT_PATTERN = re.compile(r"[^a-z0-9]+")


def _normalize_tool_tokens(tool_name: str) -> list[str]:
    normalized = (tool_name or "").strip().lower()
    if not normalized:
        return []

    tokens = [token for token in TOKEN_SPLIT_PATTERN.split(normalized) if token]
    normalized_tokens = []
    for token in tokens:
        if token.endswith("ies") and len(token) > 3:
            normalized_tokens.append(token[:-3] + "y")
        elif token.endswith("s") and len(token) > 3:
            normalized_tokens.append(token[:-1])
        else:
            normalized_tokens.append(token)
    return normalized_tokens


def requires_write_confirmation(tool_name: str) -> bool:
    """
    Return True when tool name looks like a mutating write action.

    Examples that should require explicit confirmation:
      - github_create_issue
      - github_update_issue
      - github_create_issue_comment
      - linear_create_comment
      - notion_create_page
      - calendar_update_event
    """
    tokens = _normalize_tool_tokens(tool_name)
    if not tokens:
        return False

    write_markers = WRITE_CONFIRMATION_VERBS | COMMENT_VERBS
    first_write_index = next(
        (index for index, token in enumerate(tokens) if token in write_markers),
        None,
    )
    if first_write_index is None:
        return False

    first_read_index = next(
        (index for index, token in enumerate(tokens) if token in READ_ONLY_VERBS),
        None,
    )
    if first_read_index is None:
        return True

    # Prioritize the earliest explicit action token in mixed names.
    return first_write_index < first_read_index


@dataclass(frozen=True)
class PendingWritePlan:
    """Stored write-call plan awaiting explicit confirmation."""

    confirmation_id: str
    requested_by: str
    server_id: str
    tool_name: str
    arguments: Dict[str, Any]
    created_at_epoch: float
    expires_at_epoch: float

    def to_public_dict(self) -> Dict[str, Any]:
        return {
            "confirmation_id": self.confirmation_id,
            "server_id": self.server_id,
            "tool_name": self.tool_name,
            "arguments": copy.deepcopy(self.arguments),
            "created_at": datetime.utcfromtimestamp(self.created_at_epoch).isoformat() + "Z",
            "expires_at": datetime.utcfromtimestamp(self.expires_at_epoch).isoformat() + "Z",
        }


@dataclass(frozen=True)
class WriteConfirmationGateDecision:
    """Decision returned by the write confirmation gate."""

    allow_execution: bool
    pending_plan: Optional[PendingWritePlan] = None
    status_code: Optional[int] = None
    reason: Optional[str] = None


class PendingWritePlanStore:
    """In-memory storage for pending write confirmations."""

    def __init__(
        self,
        ttl_seconds: int = 600,
        max_entries: int = 1000,
        time_fn: Optional[Callable[[], float]] = None,
    ):
        self.ttl_seconds = max(1, ttl_seconds)
        self.max_entries = max(1, max_entries)
        self._time_fn = time_fn or time.time
        self._plans: Dict[str, PendingWritePlan] = {}
        self._lock = threading.Lock()

    def create_plan(
        self,
        requested_by: str,
        server_id: str,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
    ) -> PendingWritePlan:
        now = self._time_fn()
        confirmation_id = str(uuid.uuid4())
        plan = PendingWritePlan(
            confirmation_id=confirmation_id,
            requested_by=requested_by,
            server_id=server_id,
            tool_name=tool_name,
            arguments=copy.deepcopy(arguments or {}),
            created_at_epoch=now,
            expires_at_epoch=now + self.ttl_seconds,
        )

        with self._lock:
            self._cleanup_expired_locked(now)
            if len(self._plans) >= self.max_entries:
                # Drop oldest plan to preserve bounded memory usage.
                oldest_id = min(self._plans.items(), key=lambda item: item[1].created_at_epoch)[0]
                self._plans.pop(oldest_id, None)
            self._plans[confirmation_id] = plan

        return plan

    def consume_plan(
        self,
        confirmation_id: str,
        requested_by: str,
        server_id: str,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
    ) -> tuple[bool, Optional[str]]:
        now = self._time_fn()
        normalized_arguments = copy.deepcopy(arguments or {})

        with self._lock:
            self._cleanup_expired_locked(now)
            plan = self._plans.get(confirmation_id)
            if not plan:
                return False, "Unknown or expired confirmation_id"

            if plan.requested_by != requested_by:
                return False, "confirmation_id does not belong to this caller"

            if (
                plan.server_id != server_id
                or plan.tool_name != tool_name
                or plan.arguments != normalized_arguments
            ):
                return False, "Confirmed request does not match pending plan"

            self._plans.pop(confirmation_id, None)
            return True, None

    def _cleanup_expired_locked(self, now: float) -> None:
        expired_plan_ids = [
            plan_id
            for plan_id, plan in self._plans.items()
            if plan.expires_at_epoch <= now
        ]
        for plan_id in expired_plan_ids:
            self._plans.pop(plan_id, None)


def evaluate_write_confirmation_gate(
    *,
    store: PendingWritePlanStore,
    requested_by: str,
    server_id: str,
    tool_name: str,
    arguments: Optional[Dict[str, Any]] = None,
    confirm: bool = False,
    confirmation_id: Optional[str] = None,
) -> WriteConfirmationGateDecision:
    """
    Evaluate the write confirmation gate for one tool call.

    Behaviour:
    - Any call with confirmation_id requires confirm=true.
    - Write issue/comment tools require a two-step flow:
      1) unconfirmed call returns pending plan
      2) confirmed call must include matching confirmation_id + payload
    - confirm=true without confirmation_id is rejected for write issue/comment tools.
    """
    normalized_arguments = copy.deepcopy(arguments or {})
    normalized_confirmation_id = (confirmation_id or "").strip() or None

    if normalized_confirmation_id and not confirm:
        return WriteConfirmationGateDecision(
            allow_execution=False,
            status_code=400,
            reason="confirmation_id requires confirm=true",
        )

    if not requires_write_confirmation(tool_name):
        return WriteConfirmationGateDecision(allow_execution=True)

    if confirm and not normalized_confirmation_id:
        return WriteConfirmationGateDecision(
            allow_execution=False,
            status_code=400,
            reason="confirm=true requires confirmation_id",
        )

    if confirm and normalized_confirmation_id:
        plan_matches, mismatch_reason = store.consume_plan(
            confirmation_id=normalized_confirmation_id,
            requested_by=requested_by,
            server_id=server_id,
            tool_name=tool_name,
            arguments=normalized_arguments,
        )
        if not plan_matches:
            return WriteConfirmationGateDecision(
                allow_execution=False,
                status_code=409,
                reason=mismatch_reason or "Confirmed request does not match pending plan",
            )
        return WriteConfirmationGateDecision(allow_execution=True)

    pending_plan = store.create_plan(
        requested_by=requested_by,
        server_id=server_id,
        tool_name=tool_name,
        arguments=normalized_arguments,
    )
    return WriteConfirmationGateDecision(
        allow_execution=False,
        pending_plan=pending_plan,
    )
