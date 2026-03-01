# Needs: python-package:pytest>=9.0.2
# Needs: python-package:httpx>=0.28.1
import pytest

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from internal_mcp_client import InternalMCPGatewayClient


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
async def test_call_tool_does_not_enforce_local_policy(monkeypatch):
    response = _FakeResponse(status_code=200, json_data={"status": "success"})

    def _factory(**kwargs):
        return _FakeAsyncClient(response=response)

    monkeypatch.setattr("internal_mcp_client.httpx.AsyncClient", _factory)

    client = InternalMCPGatewayClient(
        gateway_base_url="http://gateway:9100",
        allowed_tools={"allowed_tool"},
        timeout_seconds=1.0,
    )

    result = await client.call_tool("mcp-docs", "forbidden_tool", {"query": "hello"}, context="agent")

    assert result.ok is True
    assert result.status_code == 200
    assert result.error is None


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
async def test_call_tool_supports_per_call_timeout_override(monkeypatch):
    captured_timeout = {}
    response = _FakeResponse(status_code=200, json_data={"status": "success"})

    def _factory(**kwargs):
        captured_timeout["value"] = kwargs.get("timeout")
        return _FakeAsyncClient(response=response)

    monkeypatch.setattr("internal_mcp_client.httpx.AsyncClient", _factory)

    client = InternalMCPGatewayClient(
        gateway_base_url="http://gateway:9100",
        allowed_tools=set(),
        timeout_seconds=2.0,
    )

    result = await client.call_tool(
        "mcp-docs",
        "search_docs",
        {"query": "hello"},
        timeout_seconds=0.4,
    )

    assert result.ok is True
    assert result.status_code == 200
    assert captured_timeout["value"] == 0.4


@pytest.mark.unit
@pytest.mark.anyio
async def test_call_tool_redacts_secrets_in_success_payload(monkeypatch):
    captured_request_payload = {}
    response = _FakeResponse(
        status_code=200,
        json_data={
            "token": "sk-secretvalue12345",
            "nested": {"api_key": "api_key=abc123456789"},
        },
    )

    class _CaptureAsyncClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, *args, **kwargs):
            captured_request_payload["json"] = kwargs.get("json")
            return response

    monkeypatch.setattr("internal_mcp_client.httpx.AsyncClient", _CaptureAsyncClient)

    client = InternalMCPGatewayClient(
        gateway_base_url="http://gateway:9100",
        allowed_tools={"search_docs"},
        timeout_seconds=1.0,
    )

    result = await client.call_tool(
        "mcp-docs",
        "search_docs",
        {"token": "sk-secretvalue12345"},
        context="rag",
    )

    assert captured_request_payload["json"]["arguments"]["token"] == "sk-secretvalue12345"
    assert result.ok is True
    assert "sk-secretvalue12345" not in str(result.data)
    assert "[REDACTED_SECRET]" in str(result.data)


@pytest.mark.unit
@pytest.mark.anyio
async def test_call_tool_redacts_secrets_in_error_payload(monkeypatch):
    response = _FakeResponse(
        status_code=500,
        text='{"error":"token leak sk-secretvalue12345"}',
    )

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
    assert "sk-secretvalue12345" not in (result.error or "")
    assert "[REDACTED_SECRET]" in (result.error or "")
