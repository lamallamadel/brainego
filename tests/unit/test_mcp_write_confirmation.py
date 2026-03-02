# Needs: python-package:pytest>=9.0.2

from mcp_write_confirmation import (
    PendingWritePlanStore,
    evaluate_write_confirmation_gate,
    requires_write_confirmation,
)


class _FakeClock:
    def __init__(self, now: float = 1_700_000_000.0):
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_requires_confirmation_for_issue_comment_write_tools() -> None:
    assert requires_write_confirmation("github_create_issue") is True
    assert requires_write_confirmation("github_update_issue") is True
    assert requires_write_confirmation("github_create_issue_comment") is True
    assert requires_write_confirmation("linear_create_comment") is True
    assert requires_write_confirmation("linear_update_issue") is True
    assert requires_write_confirmation("jira_create_issue") is True
    assert requires_write_confirmation("jira_update_issue") is True
    assert requires_write_confirmation("notion_create_page") is True
    assert requires_write_confirmation("calendar_update_event") is True
    assert requires_write_confirmation("filesystem_create_directory") is True
    assert requires_write_confirmation("github_comment_issue") is True

    assert requires_write_confirmation("github_list_issues") is False
    assert requires_write_confirmation("jira_list_projects") is False
    assert requires_write_confirmation("github_list_issue_comments") is False
    assert requires_write_confirmation("github_get_issue_comment") is False


def test_pending_plan_can_be_confirmed_with_exact_same_call() -> None:
    store = PendingWritePlanStore(ttl_seconds=600)
    plan = store.create_plan(
        requested_by="sk-test-key-123",
        server_id="mcp-github",
        tool_name="github_create_issue",
        arguments={"title": "AFR-90", "body": "details"},
    )

    accepted, reason = store.consume_plan(
        confirmation_id=plan.confirmation_id,
        requested_by="sk-test-key-123",
        server_id="mcp-github",
        tool_name="github_create_issue",
        arguments={"title": "AFR-90", "body": "details"},
    )

    assert accepted is True
    assert reason is None


def test_confirmation_rejects_arguments_that_do_not_match_the_plan() -> None:
    store = PendingWritePlanStore(ttl_seconds=600)
    plan = store.create_plan(
        requested_by="sk-test-key-123",
        server_id="mcp-github",
        tool_name="github_update_issue",
        arguments={"issue_number": 5, "title": "before"},
    )

    accepted, reason = store.consume_plan(
        confirmation_id=plan.confirmation_id,
        requested_by="sk-test-key-123",
        server_id="mcp-github",
        tool_name="github_update_issue",
        arguments={"issue_number": 5, "title": "after"},
    )

    assert accepted is False
    assert reason == "Confirmed request does not match pending plan"


def test_confirmation_rejects_different_caller() -> None:
    store = PendingWritePlanStore(ttl_seconds=600)
    plan = store.create_plan(
        requested_by="sk-test-key-123",
        server_id="mcp-github",
        tool_name="github_create_issue",
        arguments={"title": "A", "body": "B"},
    )

    accepted, reason = store.consume_plan(
        confirmation_id=plan.confirmation_id,
        requested_by="sk-dev-key-789",
        server_id="mcp-github",
        tool_name="github_create_issue",
        arguments={"title": "A", "body": "B"},
    )

    assert accepted is False
    assert reason == "confirmation_id does not belong to this caller"


def test_confirmation_plan_expires() -> None:
    clock = _FakeClock()
    store = PendingWritePlanStore(ttl_seconds=10, time_fn=clock)
    plan = store.create_plan(
        requested_by="sk-test-key-123",
        server_id="mcp-github",
        tool_name="github_create_comment",
        arguments={"issue_number": 8, "body": "hello"},
    )
    clock.advance(11)

    accepted, reason = store.consume_plan(
        confirmation_id=plan.confirmation_id,
        requested_by="sk-test-key-123",
        server_id="mcp-github",
        tool_name="github_create_comment",
        arguments={"issue_number": 8, "body": "hello"},
    )

    assert accepted is False
    assert reason == "Unknown or expired confirmation_id"


def test_gate_rejects_confirmation_id_without_confirm_flag() -> None:
    store = PendingWritePlanStore(ttl_seconds=600)
    decision = evaluate_write_confirmation_gate(
        store=store,
        requested_by="sk-test-key-123",
        server_id="mcp-github",
        tool_name="github_create_issue",
        arguments={"title": "AFR-106"},
        confirm=False,
        confirmation_id="conf-123",
    )

    assert decision.allow_execution is False
    assert decision.pending_plan is None
    assert decision.status_code == 400
    assert decision.reason == "confirmation_id requires confirm=true"


def test_gate_rejects_confirm_true_without_confirmation_id_for_write_tools() -> None:
    store = PendingWritePlanStore(ttl_seconds=600)
    decision = evaluate_write_confirmation_gate(
        store=store,
        requested_by="sk-test-key-123",
        server_id="mcp-github",
        tool_name="github_create_issue",
        arguments={"title": "AFR-106"},
        confirm=True,
        confirmation_id=None,
    )

    assert decision.allow_execution is False
    assert decision.pending_plan is None
    assert decision.status_code == 400
    assert decision.reason == "confirm=true requires confirmation_id"


def test_gate_returns_pending_plan_for_unconfirmed_write_tool() -> None:
    store = PendingWritePlanStore(ttl_seconds=600)
    decision = evaluate_write_confirmation_gate(
        store=store,
        requested_by="sk-test-key-123",
        server_id="mcp-github",
        tool_name="github_create_issue",
        arguments={"title": "AFR-106"},
        confirm=False,
        confirmation_id=None,
    )

    assert decision.allow_execution is False
    assert decision.status_code is None
    assert decision.pending_plan is not None
    assert decision.pending_plan.tool_name == "github_create_issue"


def test_gate_allows_non_write_tools_without_confirmation() -> None:
    store = PendingWritePlanStore(ttl_seconds=600)
    decision = evaluate_write_confirmation_gate(
        store=store,
        requested_by="sk-test-key-123",
        server_id="mcp-github",
        tool_name="github_list_issues",
        arguments={"state": "open"},
        confirm=False,
        confirmation_id=None,
    )

    assert decision.allow_execution is True
    assert decision.pending_plan is None
    assert decision.status_code is None
    assert decision.reason is None


def test_gate_allows_confirmed_write_after_matching_plan() -> None:
    store = PendingWritePlanStore(ttl_seconds=600)
    pending = evaluate_write_confirmation_gate(
        store=store,
        requested_by="sk-test-key-123",
        server_id="mcp-github",
        tool_name="github_update_issue",
        arguments={"issue_number": 7, "title": "AFR-106"},
        confirm=False,
        confirmation_id=None,
    )
    assert pending.pending_plan is not None

    confirmed = evaluate_write_confirmation_gate(
        store=store,
        requested_by="sk-test-key-123",
        server_id="mcp-github",
        tool_name="github_update_issue",
        arguments={"issue_number": 7, "title": "AFR-106"},
        confirm=True,
        confirmation_id=pending.pending_plan.confirmation_id,
    )

    assert confirmed.allow_execution is True
    assert confirmed.pending_plan is None
    assert confirmed.status_code is None


def test_gate_rejects_confirmed_write_when_plan_payload_differs() -> None:
    store = PendingWritePlanStore(ttl_seconds=600)
    pending = evaluate_write_confirmation_gate(
        store=store,
        requested_by="sk-test-key-123",
        server_id="mcp-github",
        tool_name="github_update_issue",
        arguments={"issue_number": 7, "title": "before"},
        confirm=False,
        confirmation_id=None,
    )
    assert pending.pending_plan is not None

    confirmed = evaluate_write_confirmation_gate(
        store=store,
        requested_by="sk-test-key-123",
        server_id="mcp-github",
        tool_name="github_update_issue",
        arguments={"issue_number": 7, "title": "after"},
        confirm=True,
        confirmation_id=pending.pending_plan.confirmation_id,
    )

    assert confirmed.allow_execution is False
    assert confirmed.pending_plan is None
    assert confirmed.status_code == 409
    assert confirmed.reason == "Confirmed request does not match pending plan"
