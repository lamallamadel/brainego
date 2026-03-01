# Needs: python-package:pytest>=9.0.2
import pytest

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from internal_mcp_client import InternalMCPGatewayClient
from tool_policy_engine import ToolPolicyEngine, WorkspaceToolPolicy


class _FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text

    def json(self):
        return self._json_data


class _FakeAsyncClient:
    def __init__(self, response=None, exc=None, **kwargs):
        self._response = response
        self._exc = exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, *args, **kwargs):
        if self._exc:
            raise self._exc
        return self._response


@pytest.mark.unit
@pytest.mark.anyio
async def test_call_tool_success(monkeypatch):
    response = _FakeResponse(status_code=200, json_data={"status": "success", "result": {"x": 1}})

    def _factory(**kwargs):
        return _FakeAsyncClient(response=response)

    monkeypatch.setattr("internal_mcp_client.httpx.AsyncClient", _factory)

    client = InternalMCPGatewayClient(
        gateway_base_url="http://gateway:9100",
        allowed_tools={"search_docs"},
        timeout_seconds=1.0,
    )

    result = await client.call_tool("mcp-docs", "search_docs", {"query": "hello"}, context="rag")

    assert result.ok is True
    assert result.tool_name == "search_docs"
    assert result.status_code == 200
    assert result.data == {"status": "success", "result": {"x": 1}}


@pytest.mark.unit
@pytest.mark.anyio
async def test_call_tool_blocked_when_not_allowed():
    client = InternalMCPGatewayClient(
        gateway_base_url="http://gateway:9100",
        allowed_tools={"allowed_tool"},
        timeout_seconds=1.0,
    )

    result = await client.call_tool("mcp-docs", "forbidden_tool", {"query": "hello"}, context="agent")

    assert result.ok is False
    assert result.status_code == 403
    assert (result.error or "").startswith("PolicyDenied:")
    assert result.data is not None
    assert result.data.get("code") == "PolicyDenied"
    assert result.data.get("audit_event", {}).get("event_type") == "tool_policy_denied"


@pytest.mark.unit
@pytest.mark.anyio
async def test_call_tool_http_error(monkeypatch):
    response = _FakeResponse(status_code=500, text="upstream error")

    def _factory(**kwargs):
        return _FakeAsyncClient(response=response)

    monkeypatch.setattr("internal_mcp_client.httpx.AsyncClient", _factory)

    client = InternalMCPGatewayClient(
        gateway_base_url="http://gateway:9100",
        allowed_tools=set(),
        timeout_seconds=1.0,
    )

    result = await client.call_tool("mcp-docs", "search_docs", {"query": "hello"})

    assert result.ok is False
    assert result.status_code == 500
    assert result.error == "upstream error"


@pytest.mark.unit
@pytest.mark.anyio
async def test_call_tool_blocked_when_workspace_policy_denies_server():
    policy_engine = ToolPolicyEngine(
        workspace_policies={
            "ws-1": WorkspaceToolPolicy(
                workspace_id="ws-1",
                allowed_mcp_servers={"mcp-allowed"},
                allowed_tool_actions={"read"},
                allowed_tool_names={"read": {"search_docs"}},
                max_tool_calls_per_request=5,
                per_call_timeout_seconds=0.5,
            )
        }
    )
    client = InternalMCPGatewayClient(
        gateway_base_url="http://gateway:9100",
        allowed_tools=set(),
        timeout_seconds=1.0,
        tool_policy_engine=policy_engine,
    )

    result = await client.call_tool(
        "mcp-forbidden",
        "search_docs",
        {"query": "hello"},
        context="agent",
        workspace_id="ws-1",
        request_id="req-001",
    )

    assert result.ok is False
    assert result.status_code == 403
    assert (result.error or "").startswith("PolicyDenied:")
    assert "not allowed" in (result.error or "")
    assert result.data is not None
    assert result.data.get("code") == "PolicyDenied"
    assert result.data.get("audit_event", {}).get("workspace_id") == "ws-1"
    assert result.data.get("audit_event", {}).get("request_id") == "req-001"


@pytest.mark.unit
@pytest.mark.anyio
async def test_call_tool_uses_workspace_policy_timeout(monkeypatch):
    captured_timeout = {}
    response = _FakeResponse(status_code=200, json_data={"status": "success", "result": {"x": 1}})

    def _factory(**kwargs):
        captured_timeout["value"] = kwargs.get("timeout")
        return _FakeAsyncClient(response=response)

    monkeypatch.setattr("internal_mcp_client.httpx.AsyncClient", _factory)

    policy_engine = ToolPolicyEngine(
        workspace_policies={
            "ws-1": WorkspaceToolPolicy(
                workspace_id="ws-1",
                allowed_mcp_servers={"mcp-docs"},
                allowed_tool_actions={"read"},
                allowed_tool_names={"read": {"search_docs"}},
                max_tool_calls_per_request=5,
                per_call_timeout_seconds=0.25,
            )
        }
    )
    client = InternalMCPGatewayClient(
        gateway_base_url="http://gateway:9100",
        allowed_tools=set(),
        timeout_seconds=3.0,
        tool_policy_engine=policy_engine,
    )

    result = await client.call_tool(
        "mcp-docs",
        "search_docs",
        {"query": "hello"},
        workspace_id="ws-1",
        request_id="req-101",
    )

    assert result.ok is True
    assert result.status_code == 200
    assert captured_timeout["value"] == 0.25


@pytest.mark.unit
@pytest.mark.anyio
async def test_call_tool_enforces_max_calls_per_request(monkeypatch):
    request_count = {"http_calls": 0}
    response = _FakeResponse(status_code=200, json_data={"status": "success"})

    def _factory(**kwargs):
        request_count["http_calls"] += 1
        return _FakeAsyncClient(response=response)

    monkeypatch.setattr("internal_mcp_client.httpx.AsyncClient", _factory)

    policy_engine = ToolPolicyEngine(
        workspace_policies={
            "ws-1": WorkspaceToolPolicy(
                workspace_id="ws-1",
                allowed_mcp_servers={"mcp-docs"},
                allowed_tool_actions={"read"},
                allowed_tool_names={"read": {"search_docs"}},
                max_tool_calls_per_request=1,
                per_call_timeout_seconds=1.0,
            )
        }
    )
    client = InternalMCPGatewayClient(
        gateway_base_url="http://gateway:9100",
        allowed_tools=set(),
        timeout_seconds=1.0,
        tool_policy_engine=policy_engine,
    )

    first = await client.call_tool(
        "mcp-docs",
        "search_docs",
        {"query": "hello"},
        workspace_id="ws-1",
        request_id="req-201",
    )
    second = await client.call_tool(
        "mcp-docs",
        "search_docs",
        {"query": "hello again"},
        workspace_id="ws-1",
        request_id="req-201",
    )

    assert first.ok is True
    assert second.ok is False
    assert second.status_code == 403
    assert "max tool calls per request exceeded" in (second.error or "")
    assert request_count["http_calls"] == 1
