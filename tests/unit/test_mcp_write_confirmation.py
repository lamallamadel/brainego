# Needs: python-package:pytest>=9.0.2

from mcp_write_confirmation import PendingWritePlanStore, requires_write_confirmation


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

    assert requires_write_confirmation("github_list_issues") is False
    assert requires_write_confirmation("notion_create_page") is False
    assert requires_write_confirmation("calendar_update_event") is False


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
