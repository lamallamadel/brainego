"""E2E graph-assisted troubleshooting scenario.

Scenario validates that a Problem linked to Lessons and Projects can be used
alongside RAG chunks to answer a troubleshooting query.
"""

import json
import os
import socket
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

    if payload.get("status") not in {"healthy", "degraded"}:
        pytest.skip(f"E2E API health is not ready (status={payload.get('status')})")


@pytest.mark.e2e
def test_graph_assisted_troubleshooting_flow(api_base_url: str) -> None:
    """Create a graph-assisted troubleshooting data set and query it end-to-end."""
    scenario_id = uuid.uuid4().hex[:10]
    problem_name = f"Recurring ETL Failure Pattern {scenario_id}"
    project_name = f"Payments Analytics Pipeline {scenario_id}"
    lesson_name = f"Idempotent Retry Window Lesson {scenario_id}"

    recurring_failure_pattern = (
        "Recurring failure pattern: nightly ETL job fails after schema drift in upstream events."
    )

    docs = [
        {
            "text": (
                f"Problem: {problem_name}. {recurring_failure_pattern} "
                "Symptoms include duplicate writes, reconciliation mismatch, and retry storms."
            ),
            "metadata": {
                "source": "tests/e2e/test_graph_troubleshooting_flow.py",
                "scenario": "graph-assisted-troubleshooting",
                "node_type": "Problem",
                "name": problem_name,
                "scenario_id": scenario_id,
            },
        },
        {
            "text": (
                f"Lesson: {lesson_name}. Use idempotency keys, schema contract checks, "
                "and canary validation before full replay to stop recurring ETL failures."
            ),
            "metadata": {
                "source": "tests/e2e/test_graph_troubleshooting_flow.py",
                "scenario": "graph-assisted-troubleshooting",
                "node_type": "Lesson",
                "name": lesson_name,
                "scenario_id": scenario_id,
            },
        },
        {
            "text": (
                f"Project: {project_name}. This project is repeatedly impacted by the nightly "
                "ETL failure and tracks mitigation rollout progress."
            ),
            "metadata": {
                "source": "tests/e2e/test_graph_troubleshooting_flow.py",
                "scenario": "graph-assisted-troubleshooting",
                "node_type": "Project",
                "name": project_name,
                "scenario_id": scenario_id,
            },
        },
    ]

    for item in docs:
        ingest_response = _request_json("POST", f"{api_base_url}/v1/rag/ingest", item)
        assert ingest_response["status"] == "success"
        assert ingest_response["chunks_created"] >= 1

    # Build deterministic graph topology for the scenario.
    _request_json(
        "POST",
        f"{api_base_url}/graph/query",
        {
            "query": (
                "MERGE (p:Problem {name: $problem_name, scenario_id: $scenario_id}) "
                "MERGE (l:Lesson {name: $lesson_name, scenario_id: $scenario_id}) "
                "MERGE (pr:Project {name: $project_name, scenario_id: $scenario_id}) "
                "MERGE (p)-[:HAS_LESSON]->(l) "
                "MERGE (p)-[:IMPACTS_PROJECT]->(pr) "
                "RETURN p.name AS problem, l.name AS lesson, pr.name AS project"
            ),
            "parameters": {
                "problem_name": problem_name,
                "lesson_name": lesson_name,
                "project_name": project_name,
                "scenario_id": scenario_id,
            },
        },
    )

    graph_query_response = _request_json(
        "POST",
        f"{api_base_url}/v1/rag/query/graph-enriched",
        {
            "query": (
                "Explain this recurring failure pattern and include the linked lesson "
                "and impacted project."
            ),
            "k": 6,
            "filters": {"scenario": "graph-assisted-troubleshooting", "scenario_id": scenario_id},
            "graph_depth": 2,
            "graph_limit": 20,
            "include_context": True,
        },
    )

    assert graph_query_response["object"] == "rag.graph.query.completion"
    assert graph_query_response["retrieval_stats"]["chunks_retrieved"] >= 1
    assert graph_query_response["retrieval_stats"]["relationships_found"] >= 1

    graph_context = graph_query_response.get("graph_context") or {}
    relationships = graph_context.get("relationships") or []
    relation_types = {
        relation_type
        for relationship in relationships
        for relation_type in relationship.get("relation_types", [])
    }
    assert {"HAS_LESSON", "IMPACTS_PROJECT"}.issubset(relation_types)

    response_text = graph_query_response.get("response", "")
    assert recurring_failure_pattern.lower().split(":", maxsplit=1)[0] in response_text.lower()
    assert "lesson" in response_text.lower()
    assert "project" in response_text.lower()


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
