"""E2E MVP flow: ingest document -> ask question -> verify RAG and memory behavior.

This suite is intended for CI Docker/full-stack environments where the API and
its dependencies (RAG + memory backends) are running.
"""

import json
import os
import socket
import time
import urllib.error
import urllib.request
import uuid
from typing import Any

import pytest


API_BASE_URL = os.getenv("E2E_API_BASE_URL", "http://localhost:8000")
REQUEST_TIMEOUT_SECONDS = float(os.getenv("E2E_REQUEST_TIMEOUT_SECONDS", "30"))


class HTTPErrorWithBody(Exception):
    """Raised when an HTTP response is not successful."""


@pytest.fixture(scope="session")
def api_base_url() -> str:
    return API_BASE_URL.rstrip("/")


@pytest.fixture(scope="session", autouse=True)
def require_running_api(api_base_url: str) -> None:
    """Skip e2e suite unless a live API is reachable."""
    try:
        payload = _request_json("GET", f"{api_base_url}/health")
    except (urllib.error.URLError, TimeoutError, socket.error):
        pytest.skip(f"E2E API is unreachable at {api_base_url}; skipping e2e suite")
    except HTTPErrorWithBody as exc:
        pytest.skip(f"E2E API health endpoint returned non-success: {exc}")

    status = payload.get("status")
    if status not in {"healthy", "degraded"}:
        pytest.skip(f"E2E API health is not ready (status={status})")


@pytest.mark.e2e
def test_mvp_flow_ingest_then_rag_then_persistent_memory(api_base_url: str) -> None:
    """Validate end-to-end MVP user flow against running stack."""
    user_id = f"e2e-user-{uuid.uuid4().hex[:10]}"
    project_id = f"e2e-project-{uuid.uuid4().hex[:8]}"

    fact_text = "User profile fact: my preferred language is French."
    rag_text = (
        "Brainego architecture note: Apache Spark handles parallel data processing "
        "workloads in the analytics pipeline."
    )

    ingest_payload = {
        "text": f"{rag_text}\n{fact_text}",
        "metadata": {
            "source": "tests/e2e/test_mvp_flow.py",
            "project": project_id,
            "scenario": "mvp-flow",
        },
    }
    ingest_response = _request_json("POST", f"{api_base_url}/v1/rag/ingest", ingest_payload)
    assert ingest_response["status"] == "success"
    assert ingest_response["chunks_created"] >= 1
    assert ingest_response["document_id"]

    # Turn 1: ask RAG-driven question and store memory.
    first_chat_payload = {
        "user": user_id,
        "messages": [
            {"role": "user", "content": fact_text},
            {"role": "user", "content": "Which framework handles parallel data processing?"},
        ],
        "use_rag": True,
        "use_memory": True,
        "store_memory": True,
        "include_context": True,
    }
    first_chat = _request_json("POST", f"{api_base_url}/v1/chat", first_chat_payload)

    assert "choices" in first_chat and first_chat["choices"]
    assert "x-rag-metadata" in first_chat
    assert first_chat["x-rag-metadata"]["chunks_retrieved"] >= 1
    assert "Apache Spark" in first_chat["choices"][0]["message"]["content"]

    assert "x-memory-metadata" in first_chat
    assert first_chat["x-memory-metadata"].get("memory_stored") is True

    # Allow asynchronous memory indexing in backing services.
    time.sleep(1.0)

    # Turn 2: verify follow-up uses persistent memory context.
    second_chat_payload = {
        "user": user_id,
        "messages": [{"role": "user", "content": "What is my preferred language?"}],
        "use_rag": False,
        "use_memory": True,
        "store_memory": False,
        "include_context": True,
    }
    second_chat = _request_json("POST", f"{api_base_url}/v1/chat", second_chat_payload)

    assert "x-memory-metadata" in second_chat
    assert second_chat["x-memory-metadata"].get("memories_retrieved", 0) >= 1

    memory_context = second_chat.get("memory_context") or []
    assert memory_context, "Expected non-empty memory context in follow-up response"
    assert any("preferred language" in item.get("text", "").lower() for item in memory_context)


def _request_json(method: str, url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Issue an HTTP request and parse JSON response."""
    headers = {"Content-Type": "application/json"}
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, method=method, data=body, headers=headers)

    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore")
        raise HTTPErrorWithBody(f"{method} {url} -> {exc.code}: {raw}") from exc
