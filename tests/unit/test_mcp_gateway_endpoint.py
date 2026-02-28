# Needs: python-package:fastapi>=0.133.1
# Needs: python-package:httpx>=0.28.1

from fastapi.testclient import TestClient

import gateway_service_mcp as service


class DummyACL:
    def get_user_role(self, api_key):
        return "developer"

    def validate_request(self, **kwargs):
        return True, "ok"


class DummyMCPClient:
    async def list_tools(self, server_id):
        return [{"name": "dummy_tool", "server_id": server_id}]

    async def call_tool(self, server_id, tool_name, arguments):
        return {"server_id": server_id, "tool_name": tool_name, "arguments": arguments}

    async def list_resources(self, server_id):
        return [{"uri": "dummy://resource", "server_id": server_id}]

    async def read_resource(self, server_id, uri):
        return {"uri": uri, "server_id": server_id, "content": "ok"}


API_HEADER = {"Authorization": "Bearer sk-test-key-123"}


def setup_function():
    service.metrics = service.MetricsStore()

def _configure_dependencies(monkeypatch):
    monkeypatch.setattr(service, "mcp_client", DummyMCPClient())
    monkeypatch.setattr(service, "mcp_acl", DummyACL())


def test_metrics_endpoint_is_public(monkeypatch):
    _configure_dependencies(monkeypatch)
    client = TestClient(service.app)

    response = client.get("/metrics")

    assert response.status_code == 200
    assert "metrics" in response.json()


def test_unified_mcp_gateway_list_tools(monkeypatch):
    _configure_dependencies(monkeypatch)
    client = TestClient(service.app)

    response = client.post(
        "/mcp",
        json={"server_id": "mcp-github", "action": "list_tools"},
        headers=API_HEADER,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["server_id"] == "mcp-github"
    assert payload["action"] == "list_tools"
    assert payload["result"][0]["name"] == "dummy_tool"


def test_unified_mcp_gateway_requires_tool_name_for_call_tool(monkeypatch):
    _configure_dependencies(monkeypatch)
    client = TestClient(service.app)

    response = client.post(
        "/mcp",
        json={"server_id": "mcp-github", "action": "call_tool"},
        headers=API_HEADER,
    )

    assert response.status_code == 400
    assert "tool_name is required" in response.json()["detail"]


def test_mcp_metrics_include_error_rate(monkeypatch):
    _configure_dependencies(monkeypatch)
    client = TestClient(service.app)

    bad_response = client.post(
        "/mcp",
        json={"server_id": "mcp-github", "action": "call_tool"},
        headers=API_HEADER,
    )
    assert bad_response.status_code == 400

    ok_response = client.post(
        "/mcp",
        json={"server_id": "mcp-github", "action": "list_resources"},
        headers=API_HEADER,
    )
    assert ok_response.status_code == 200

    metrics_response = client.get("/metrics")
    assert metrics_response.status_code == 200

    m = metrics_response.json()["metrics"]
    assert "mcp_error_rate" in m
    assert m["mcp_requests"] >= 2
    assert m["mcp_errors"] >= 1
