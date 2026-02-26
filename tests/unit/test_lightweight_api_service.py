# Needs: fastapi>=0.133.1
# Needs: httpx>=0.28.1

from fastapi.testclient import TestClient

import lightweight_api_service as service


class MockResponse:
    def __init__(self, status_code=200, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.content = str(self._payload).encode("utf-8")
        self.headers = headers or {"content-type": "application/json"}


class MockAsyncClient:
    def __init__(self, recorder):
        self.recorder = recorder

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def request(self, method, url, params=None, content=None, headers=None):
        self.recorder["method"] = method
        self.recorder["url"] = url
        self.recorder["params"] = dict(params) if params is not None else {}
        self.recorder["content"] = content
        self.recorder["headers"] = headers or {}
        return MockResponse(
            200,
            {"ok": True, "url": url, "method": method},
            {"content-type": "application/json", "x-test": "ok"},
        )


def _patch_client(monkeypatch, recorder):
    def fake_client(*args, **kwargs):
        return MockAsyncClient(recorder)

    monkeypatch.setattr(service.httpx, "AsyncClient", fake_client)


def test_chat_endpoint_forwards_to_max_chat_path(monkeypatch):
    recorder = {}
    _patch_client(monkeypatch, recorder)

    client = TestClient(service.app)
    response = client.post("/v1/chat", json={"messages": [{"role": "user", "content": "hi"}]})

    assert response.status_code == 200
    assert recorder["method"] == "POST"
    assert recorder["url"] == f"{service.MAX_SERVE_URL}{service.MAX_CHAT_PATH}"


def test_rag_query_forwards_query_params_and_body(monkeypatch):
    recorder = {}
    _patch_client(monkeypatch, recorder)

    client = TestClient(service.app)
    response = client.post("/v1/rag/query?tenant=acme", json={"query": "hello"})

    assert response.status_code == 200
    assert recorder["url"] == f"{service.RAG_SERVICE_URL}/v1/rag/query"
    assert recorder["params"] == {"tenant": "acme"}
    assert b'"query":"hello"' in recorder["content"]


def test_memory_wildcard_endpoint_forwards_path_and_method(monkeypatch):
    recorder = {}
    _patch_client(monkeypatch, recorder)

    client = TestClient(service.app)
    response = client.delete("/memory/forget/abc123")

    assert response.status_code == 200
    assert recorder["method"] == "DELETE"
    assert recorder["url"] == f"{service.MEM0_SERVICE_URL}/memory/forget/abc123"


def test_forwarded_response_keeps_downstream_headers(monkeypatch):
    recorder = {}
    _patch_client(monkeypatch, recorder)

    client = TestClient(service.app)
    response = client.post("/v1/chat", json={"messages": [{"role": "user", "content": "ok"}]})

    assert response.status_code == 200
    assert response.headers.get("x-test") == "ok"
