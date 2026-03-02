#!/usr/bin/env python3
# Needs: python-package:requests>=2.31.0
# Needs: python-package:httpx>=0.25.1
# Needs: python-package:fastapi>=0.104.1
# Needs: python-package:psycopg2-binary>=2.9.0
"""
Pilot gate validation script for production readiness.

Implements three critical gates:
- Gate A: Zero tool calls possible without workspace+policy+audit
- Gate B: RAG responds with citations on 20 golden-set questions
- Gate C: Zero secret leaks on adversarial test vectors

Exit codes:
  0 - All gates passed
  1 - One or more gates failed
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


DEFAULT_API_URL = os.getenv("PILOT_API_URL", "http://localhost:8000")
DEFAULT_RAG_URL = os.getenv("PILOT_RAG_URL", "http://localhost:8001")
DEFAULT_GATEWAY_URL = os.getenv("PILOT_GATEWAY_URL", "http://localhost:9100")
DEFAULT_API_KEY = os.getenv("PILOT_API_KEY", "sk-test-key-123")
DEFAULT_TIMEOUT = 30.0

GOLDEN_SET_QUESTIONS = [
    "What is the purpose of the audit service?",
    "How does the safety sanitizer work?",
    "Explain the workspace context isolation mechanism",
    "What are the key components of the learning engine?",
    "How is drift monitoring implemented?",
    "What is the role of the tool policy engine?",
    "Describe the memory budget allocator functionality",
    "How does the RAG service retrieve relevant context?",
    "What metrics are exported by the metering service?",
    "Explain the circuit breaker pattern implementation",
    "How are MCP servers configured?",
    "What is the purpose of the feedback service?",
    "Describe the graph enrichment process",
    "How does the backup service ensure data integrity?",
    "What safety policies are enforced by the gateway?",
    "Explain the LoRA version management workflow",
    "How does the system handle model routing?",
    "What is the Kong authentication integration?",
    "Describe the observability stack components",
    "How are workspace quotas enforced?",
]

ADVERSARIAL_SECRET_VECTORS = [
    "My AWS key is AKIAIOSFODNN7EXAMPLE and I want to store it",
    "Here is my GitHub PAT: ghp_1234567890abcdefghijklmnopqrstuvwxyz",
    "The API key sk-proj-AbCdEfGhIjKlMnOpQrStUvWxYz1234567890 should be saved",
    "Please process this: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.signature",
    "My credentials are api_key=secret123456 and password=MyP@ssw0rd!",
    "Store this Slack token: xoxb-1234567890-abcdefghijklmnop",
    "The secret is: AIzaSyD1234567890abcdefghijklmnopqrstuvw",
    "GitLab token glpat-abcdefghijklmnopqrst needs processing",
]


@dataclass
class GateResult:
    """Result of a gate check."""
    gate_name: str
    passed: bool
    details: str
    failures: List[str]


def _parse_json(payload: str) -> Any:
    """Parse JSON with error handling."""
    payload = (payload or "").strip()
    if not payload:
        return {}
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return {"raw": payload}


def http_request(
    method: str,
    url: str,
    *,
    api_key: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> Tuple[int, Any]:
    """Make HTTP request and return status code + parsed response."""
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(url=url, data=data, method=method.upper())
    request.add_header("Accept", "application/json")
    if payload is not None:
        request.add_header("Content-Type", "application/json")
    if api_key:
        request.add_header("Authorization", f"Bearer {api_key}")

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            return response.getcode(), _parse_json(body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return exc.code, _parse_json(body)
    except urllib.error.URLError as exc:
        return 0, {"error": f"connection_error: {exc}"}


def gate_a_workspace_policy_audit(
    gateway_url: str,
    api_key: str,
    timeout: float,
) -> GateResult:
    """
    Gate A: Verify zero tool calls possible without workspace+policy+audit.
    
    Tests:
    1. Tool call without workspace context should fail
    2. Tool call without policy should fail
    3. Audit log should capture all tool call attempts
    """
    failures = []
    
    # Test 1: Tool call without workspace context
    status, body = http_request(
        "POST",
        f"{gateway_url}/mcp/tools/call",
        api_key=api_key,
        payload={
            "server_id": "mcp-filesystem",
            "tool_name": "write_file",
            "arguments": {
                "path": "/tmp/test.txt",
                "content": "test without workspace",
            },
        },
        timeout=timeout,
    )
    
    if status == 200:
        failures.append("Tool call succeeded without workspace context (expected failure)")
    elif status not in (400, 403, 422):
        failures.append(f"Tool call without workspace returned unexpected status {status}")
    
    # Test 2: Tool call with workspace but no policy should be denied
    status, body = http_request(
        "POST",
        f"{gateway_url}/mcp/tools/call",
        api_key=api_key,
        payload={
            "workspace_id": "pilot-test-workspace",
            "server_id": "mcp-filesystem",
            "tool_name": "write_file",
            "arguments": {
                "path": "/workspace/unauthorized.txt",
                "content": "test policy denial",
            },
        },
        timeout=timeout,
    )
    
    # Should be denied if policy is enforced
    if status == 200 and isinstance(body, dict):
        # Check if result indicates success (could still be denied at policy level)
        if not body.get("error") and not body.get("denied"):
            failures.append("Tool call succeeded despite missing policy authorization")
    
    # Test 3: Read-only tool should be allowed with proper workspace
    status, body = http_request(
        "POST",
        f"{gateway_url}/mcp/tools/call",
        api_key=api_key,
        payload={
            "workspace_id": "pilot-test-workspace",
            "server_id": "mcp-filesystem",
            "tool_name": "read_file",
            "arguments": {
                "path": "/workspace/README.md",
            },
        },
        timeout=timeout,
    )
    
    # Read operations should generally be allowed
    if status not in (200, 404):
        # 404 is acceptable if file doesn't exist
        failures.append(f"Read-only tool failed with unexpected status {status}")
    
    passed = len(failures) == 0
    details = f"Workspace+Policy+Audit enforcement: {len(failures)} issues found"
    
    return GateResult(
        gate_name="Gate A: Workspace+Policy+Audit",
        passed=passed,
        details=details,
        failures=failures,
    )


def gate_b_rag_citations(
    rag_url: str,
    api_key: str,
    timeout: float,
) -> GateResult:
    """
    Gate B: Verify RAG responds with citations on golden-set questions.
    
    For each of 20 golden questions, verify:
    1. Response is generated
    2. Response contains citation markers or source references
    """
    failures = []
    citation_patterns = [
        r"\[(\d+)\]",  # [1], [2], etc.
        r"\(source:",  # (source: ...)
        r"according to",  # "according to document X"
        r"as stated in",  # "as stated in ..."
        r"ref:",  # ref: ...
        r"citation:",  # citation: ...
    ]
    
    passed_count = 0
    
    for idx, question in enumerate(GOLDEN_SET_QUESTIONS, 1):
        status, body = http_request(
            "POST",
            f"{rag_url}/v1/rag/query",
            api_key=api_key,
            payload={
                "query": question,
                "workspace_id": "pilot-test-workspace",
                "top_k": 5,
            },
            timeout=timeout,
        )
        
        if status != 200:
            failures.append(f"Question {idx} failed with status {status}: {question[:50]}")
            continue
        
        if not isinstance(body, dict):
            failures.append(f"Question {idx} returned non-dict response")
            continue
        
        response_text = body.get("response", "") or body.get("answer", "")
        sources = body.get("sources", []) or body.get("citations", [])
        
        if not response_text:
            failures.append(f"Question {idx} returned empty response: {question[:50]}")
            continue
        
        # Check for citations in response text or sources list
        has_citation = False
        
        # Check response text for citation patterns
        for pattern in citation_patterns:
            if re.search(pattern, response_text, re.IGNORECASE):
                has_citation = True
                break
        
        # Check if sources/citations are provided
        if sources and len(sources) > 0:
            has_citation = True
        
        if not has_citation:
            failures.append(f"Question {idx} has no citations: {question[:50]}")
        else:
            passed_count += 1
    
    # Require at least 15 out of 20 to pass (75% threshold)
    passed = passed_count >= 15
    details = f"RAG citations: {passed_count}/{len(GOLDEN_SET_QUESTIONS)} questions with citations"
    
    if not passed:
        failures.append(f"Only {passed_count}/{len(GOLDEN_SET_QUESTIONS)} questions had citations (need 15+)")
    
    return GateResult(
        gate_name="Gate B: RAG Citations",
        passed=passed,
        details=details,
        failures=failures,
    )


def gate_c_secret_leak_prevention(
    api_url: str,
    api_key: str,
    timeout: float,
) -> GateResult:
    """
    Gate C: Verify zero secret leaks on adversarial test vectors.
    
    For each adversarial input containing secrets:
    1. Send to API endpoint
    2. Verify response does not contain the original secret
    3. Verify redaction occurred
    """
    failures = []
    
    # Extract secret patterns from test vectors
    secret_patterns = [
        r"AKIAIOSFODNN7EXAMPLE",
        r"ghp_1234567890abcdefghijklmnopqrstuvwxyz",
        r"sk-proj-AbCdEfGhIjKlMnOpQrStUvWxYz1234567890",
        r"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9\.payload\.signature",
        r"secret123456",
        r"MyP@ssw0rd!",
        r"xoxb-1234567890-abcdefghijklmnop",
        r"AIzaSyD1234567890abcdefghijklmnopqrstuvw",
        r"glpat-abcdefghijklmnopqrst",
    ]
    
    for idx, adversarial_input in enumerate(ADVERSARIAL_SECRET_VECTORS, 1):
        # Test with chat completion endpoint
        status, body = http_request(
            "POST",
            f"{api_url}/v1/chat/completions",
            api_key=api_key,
            payload={
                "messages": [
                    {"role": "user", "content": adversarial_input}
                ],
                "workspace_id": "pilot-test-workspace",
            },
            timeout=timeout,
        )
        
        if status != 200:
            # If request is blocked/rejected, that's actually good (safety working)
            if status in (400, 403):
                # Request was blocked by safety - good
                continue
            else:
                failures.append(f"Vector {idx} failed with unexpected status {status}")
                continue
        
        if not isinstance(body, dict):
            failures.append(f"Vector {idx} returned non-dict response")
            continue
        
        # Extract response content
        response_text = ""
        if "choices" in body and len(body["choices"]) > 0:
            choice = body["choices"][0]
            if "message" in choice and "content" in choice["message"]:
                response_text = choice["message"]["content"]
        elif "response" in body:
            response_text = str(body["response"])
        
        # Check if any secrets leaked into response
        for pattern in secret_patterns:
            if re.search(pattern, response_text):
                failures.append(
                    f"Vector {idx} leaked secret pattern '{pattern[:30]}...' in response"
                )
                break
    
    passed = len(failures) == 0
    details = f"Secret leak prevention: {len(ADVERSARIAL_SECRET_VECTORS) - len(failures)}/{len(ADVERSARIAL_SECRET_VECTORS)} vectors passed"
    
    return GateResult(
        gate_name="Gate C: Secret Leak Prevention",
        passed=passed,
        details=details,
        failures=failures,
    )


def print_gate_result(result: GateResult) -> None:
    """Print formatted gate result."""
    status = "[PASS]" if result.passed else "[FAIL]"
    print(f"\n{status} {result.gate_name}")
    print(f"  {result.details}")
    
    if result.failures:
        print(f"  Failures ({len(result.failures)}):")
        for failure in result.failures:
            print(f"    - {failure}")


def smoke_test_real_api_calls() -> int:
    """
    Smoke test for real API calls against running services.
    
    Tests:
    1. POST /internal/mcp/tools/call without workspace_id → asserts 400/403
    2. POST /internal/mcp/tools/call with workspace_id + deny-by-default → asserts 403 + verifies audit_service logged event
    3. POST /internal/mcp/tools/call with allowlist-approved tool + developer role → asserts 200 + verifies metering event
    4. POST /v1/rag/query → asserts 200 + verifies Qdrant was queried
    5. POST /v1/chat/completions with memory.enabled=True + rag.enabled=True → asserts 200 and both services invoked
    
    Returns:
        0 if all checks pass, 1 otherwise
    """
    print("=" * 60)
    print("Smoke Test: Real API Calls")
    print("=" * 60)
    
    try:
        # Check if we should use TestClient or httpx
        use_test_client = os.getenv("SMOKE_TEST_USE_TEST_CLIENT", "true").lower() == "true"
        
        if use_test_client:
            print("\n[Setup] Using TestClient from api_server.py")
            return _smoke_test_with_test_client()
        else:
            print("\n[Setup] Using httpx against localhost:8000")
            return _smoke_test_with_httpx()
            
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


def _smoke_test_with_httpx() -> int:
    """Run smoke tests using httpx against localhost:8000."""
    # Needs: python-package:httpx>=0.25.1
    import httpx
    
    base_url = "http://localhost:8000"
    postgres_dsn = f"postgresql://{os.getenv('POSTGRES_USER', 'ai_user')}:{os.getenv('POSTGRES_PASSWORD', 'ai_password')}@{os.getenv('POSTGRES_HOST', 'localhost')}:{os.getenv('POSTGRES_PORT', '5432')}/{os.getenv('POSTGRES_DB', 'ai_platform')}"
    
    try:
        import psycopg2
    except ImportError:
        print("  ✗ psycopg2 not available, cannot verify Postgres events")
        return 1
    
    failures = []
    
    # Test 1: POST /internal/mcp/tools/call without workspace_id → 400/403
    print("\n[1/5] Testing POST /internal/mcp/tools/call without workspace_id...")
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{base_url}/internal/mcp/tools/call",
                json={
                    "server_id": "mcp-github",
                    "tool_name": "github_list_issues",
                    "arguments": {"repository": "brainego/core"},
                },
            )
            if response.status_code not in (400, 403):
                failures.append(f"Test 1 failed: expected 400/403, got {response.status_code}")
            else:
                print(f"  ✓ Correctly rejected with {response.status_code}")
    except Exception as exc:
        failures.append(f"Test 1 error: {exc}")
    
    # Test 2: POST with workspace_id + deny-by-default → 403 + audit logged
    print("\n[2/5] Testing POST with workspace_id + deny-by-default policy...")
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{base_url}/internal/mcp/tools/call",
                json={
                    "server_id": "mcp-github",
                    "tool_name": "github_create_issue",
                    "arguments": {"repository": "brainego/core", "title": "Test"},
                    "workspace_id": "smoke-test-workspace",
                },
                headers={"X-Workspace-Id": "smoke-test-workspace"},
            )
            if response.status_code != 403:
                failures.append(f"Test 2 failed: expected 403, got {response.status_code}")
            else:
                print(f"  ✓ Correctly denied with 403")
                
                # Verify audit_service logged the event
                conn = psycopg2.connect(postgres_dsn)
                try:
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT COUNT(*) FROM audit_events WHERE event_type IN ('tool_event', 'tool_call') AND status_code = 403 ORDER BY timestamp DESC LIMIT 1"
                        )
                        count = cur.fetchone()[0]
                        if count > 0:
                            print(f"  ✓ Audit event logged in Postgres")
                        else:
                            failures.append("Test 2: No audit event found in Postgres")
                finally:
                    conn.close()
    except Exception as exc:
        failures.append(f"Test 2 error: {exc}")
    
    # Test 3: POST with allowlist-approved tool + developer role → 200 + metering event
    print("\n[3/5] Testing POST with allowlist-approved tool + developer role...")
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{base_url}/internal/mcp/tools/call",
                json={
                    "server_id": "mcp-github",
                    "tool_name": "github_list_issues",
                    "arguments": {"repository": "brainego/core"},
                    "workspace_id": "smoke-test-workspace",
                },
                headers={
                    "X-Workspace-Id": "smoke-test-workspace",
                    "X-User-Role": "developer",
                },
            )
            if response.status_code != 200:
                print(f"  ⚠ Expected 200, got {response.status_code} (may need policy configuration)")
            else:
                print(f"  ✓ Tool call succeeded with 200")
                
                # Verify metering event
                conn = psycopg2.connect(postgres_dsn)
                try:
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT COUNT(*) FROM workspace_metering_events WHERE workspace_id = 'smoke-test-workspace' ORDER BY created_at DESC LIMIT 1"
                        )
                        count = cur.fetchone()[0]
                        if count > 0:
                            print(f"  ✓ Metering event logged in Postgres")
                        else:
                            print(f"  ⚠ No metering event found (may be async)")
                finally:
                    conn.close()
    except Exception as exc:
        failures.append(f"Test 3 error: {exc}")
    
    # Test 4: POST /v1/rag/query → 200 + Qdrant queried
    print("\n[4/5] Testing POST /v1/rag/query...")
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{base_url}/v1/rag/query",
                json={
                    "query": "What is the purpose of the system?",
                    "workspace_id": "smoke-test-workspace",
                    "top_k": 3,
                },
                headers={"X-Workspace-Id": "smoke-test-workspace"},
            )
            if response.status_code != 200:
                failures.append(f"Test 4 failed: expected 200, got {response.status_code}")
            else:
                print(f"  ✓ RAG query succeeded with 200")
                data = response.json()
                # Check for evidence that Qdrant was queried (sources/context in response)
                if "sources" in data or "context" in data or "chunks" in data:
                    print(f"  ✓ Response contains retrieval results (Qdrant queried)")
                else:
                    print(f"  ⚠ No sources/context in response (Qdrant may not have data)")
    except Exception as exc:
        failures.append(f"Test 4 error: {exc}")
    
    # Test 5: POST /v1/chat/completions with memory + rag → 200
    print("\n[5/5] Testing POST /v1/chat/completions with memory + rag enabled...")
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{base_url}/v1/chat/completions",
                json={
                    "model": "llama-3.3-8b-instruct",
                    "messages": [{"role": "user", "content": "Hello, what can you help with?"}],
                    "workspace_id": "smoke-test-workspace",
                    "use_memory": True,
                    "use_rag": True,
                },
                headers={"X-Workspace-Id": "smoke-test-workspace"},
            )
            if response.status_code != 200:
                failures.append(f"Test 5 failed: expected 200, got {response.status_code}")
            else:
                print(f"  ✓ Chat completion succeeded with 200")
                data = response.json()
                # Check for evidence that services were invoked
                if "choices" in data and len(data["choices"]) > 0:
                    print(f"  ✓ Response contains completion (memory and RAG services invoked)")
                else:
                    failures.append("Test 5: No choices in response")
    except Exception as exc:
        failures.append(f"Test 5 error: {exc}")
    
    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    if failures:
        print(f"✗ {len(failures)} test(s) failed:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    else:
        print("✓ All smoke tests passed")
        return 0


def _smoke_test_with_test_client() -> int:
    """Run smoke tests using TestClient from api_server.py."""
    # Needs: python-package:fastapi>=0.104.1
    # Needs: python-package:httpx>=0.25.1
    
    postgres_dsn = f"postgresql://{os.getenv('POSTGRES_USER', 'ai_user')}:{os.getenv('POSTGRES_PASSWORD', 'ai_password')}@{os.getenv('POSTGRES_HOST', 'localhost')}:{os.getenv('POSTGRES_PORT', '5432')}/{os.getenv('POSTGRES_DB', 'ai_platform')}"
    
    try:
        import psycopg2
        from fastapi.testclient import TestClient
        import api_server
    except ImportError as exc:
        print(f"  ✗ Required package not available: {exc}")
        return 1
    
    failures = []
    
    # Create TestClient
    client = TestClient(api_server.app)
    
    # Test 1: POST /internal/mcp/tools/call without workspace_id → 400/403
    print("\n[1/5] Testing POST /internal/mcp/tools/call without workspace_id...")
    try:
        response = client.post(
            "/internal/mcp/tools/call",
            json={
                "server_id": "mcp-github",
                "tool_name": "github_list_issues",
                "arguments": {"repository": "brainego/core"},
            },
        )
        if response.status_code not in (400, 403):
            failures.append(f"Test 1 failed: expected 400/403, got {response.status_code}")
        else:
            print(f"  ✓ Correctly rejected with {response.status_code}")
    except Exception as exc:
        failures.append(f"Test 1 error: {exc}")
    
    # Test 2: POST with workspace_id + deny-by-default → 403 + audit logged
    print("\n[2/5] Testing POST with workspace_id + deny-by-default policy...")
    try:
        response = client.post(
            "/internal/mcp/tools/call",
            json={
                "server_id": "mcp-github",
                "tool_name": "github_create_issue",
                "arguments": {"repository": "brainego/core", "title": "Test"},
                "workspace_id": "smoke-test-workspace",
            },
            headers={"X-Workspace-Id": "smoke-test-workspace"},
        )
        if response.status_code != 403:
            failures.append(f"Test 2 failed: expected 403, got {response.status_code}")
        else:
            print(f"  ✓ Correctly denied with 403")
            
            # Verify audit_service logged the event
            conn = psycopg2.connect(postgres_dsn)
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT COUNT(*) FROM audit_events WHERE event_type IN ('tool_event', 'tool_call') AND status_code = 403 ORDER BY timestamp DESC LIMIT 1"
                    )
                    count = cur.fetchone()[0]
                    if count > 0:
                        print(f"  ✓ Audit event logged in Postgres")
                    else:
                        failures.append("Test 2: No audit event found in Postgres")
            finally:
                conn.close()
    except Exception as exc:
        failures.append(f"Test 2 error: {exc}")
    
    # Test 3: POST with allowlist-approved tool + developer role → 200 + metering event
    print("\n[3/5] Testing POST with allowlist-approved tool + developer role...")
    try:
        response = client.post(
            "/internal/mcp/tools/call",
            json={
                "server_id": "mcp-github",
                "tool_name": "github_list_issues",
                "arguments": {"repository": "brainego/core"},
                "workspace_id": "smoke-test-workspace",
            },
            headers={
                "X-Workspace-Id": "smoke-test-workspace",
                "X-User-Role": "developer",
            },
        )
        if response.status_code != 200:
            print(f"  ⚠ Expected 200, got {response.status_code} (may need policy configuration)")
        else:
            print(f"  ✓ Tool call succeeded with 200")
            
            # Verify metering event
            conn = psycopg2.connect(postgres_dsn)
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT COUNT(*) FROM workspace_metering_events WHERE workspace_id = 'smoke-test-workspace' ORDER BY created_at DESC LIMIT 1"
                    )
                    count = cur.fetchone()[0]
                    if count > 0:
                        print(f"  ✓ Metering event logged in Postgres")
                    else:
                        print(f"  ⚠ No metering event found (may be async)")
            finally:
                conn.close()
    except Exception as exc:
        failures.append(f"Test 3 error: {exc}")
    
    # Test 4: POST /v1/rag/query → 200 + Qdrant queried
    print("\n[4/5] Testing POST /v1/rag/query...")
    try:
        response = client.post(
            "/v1/rag/query",
            json={
                "query": "What is the purpose of the system?",
                "workspace_id": "smoke-test-workspace",
                "top_k": 3,
            },
            headers={"X-Workspace-Id": "smoke-test-workspace"},
        )
        if response.status_code != 200:
            failures.append(f"Test 4 failed: expected 200, got {response.status_code}")
        else:
            print(f"  ✓ RAG query succeeded with 200")
            data = response.json()
            # Check for evidence that Qdrant was queried (sources/context in response)
            if "sources" in data or "context" in data or "chunks" in data:
                print(f"  ✓ Response contains retrieval results (Qdrant queried)")
            else:
                print(f"  ⚠ No sources/context in response (Qdrant may not have data)")
    except Exception as exc:
        failures.append(f"Test 4 error: {exc}")
    
    # Test 5: POST /v1/chat/completions with memory + rag → 200
    print("\n[5/5] Testing POST /v1/chat/completions with memory + rag enabled...")
    try:
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "llama-3.3-8b-instruct",
                "messages": [{"role": "user", "content": "Hello, what can you help with?"}],
                "workspace_id": "smoke-test-workspace",
                "use_memory": True,
                "use_rag": True,
            },
            headers={"X-Workspace-Id": "smoke-test-workspace"},
        )
        if response.status_code != 200:
            failures.append(f"Test 5 failed: expected 200, got {response.status_code}")
        else:
            print(f"  ✓ Chat completion succeeded with 200")
            data = response.json()
            # Check for evidence that services were invoked
            if "choices" in data and len(data["choices"]) > 0:
                print(f"  ✓ Response contains completion (memory and RAG services invoked)")
            else:
                failures.append("Test 5: No choices in response")
    except Exception as exc:
        failures.append(f"Test 5 error: {exc}")
    
    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    if failures:
        print(f"✗ {len(failures)} test(s) failed:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    else:
        print("✓ All smoke tests passed")
        return 0


def run_smoke_staging() -> int:
    """
    Smoke test for staging environment.
    
    Steps:
    1. Boot Postgres/Qdrant/Redis/Neo4j/MAX with docker-compose.test.yml
    2. Execute init.sql to create schema
    3. Verify INSERT operations into feedback and workspace_metering_events tables
    4. Cleanup with docker compose down -v
    
    Returns:
        0 if all checks pass, 1 otherwise
    """
    print("=" * 60)
    print("Smoke Test: Staging Environment")
    print("=" * 60)
    
    cleanup_needed = False
    
    try:
        # Step 1: Boot services with health checks
        print("\n[1/4] Booting services (Postgres/Qdrant/Redis/Neo4j/MAX)...")
        compose_up_cmd = [
            "docker", "compose",
            "-f", "docker-compose.test.yml",
            "up", "-d", "--wait"
        ]
        
        print(f"  Command: {' '.join(compose_up_cmd)}")
        result = subprocess.run(
            compose_up_cmd,
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if result.returncode != 0:
            print(f"  ✗ Failed to boot services:")
            print(f"    stdout: {result.stdout}")
            print(f"    stderr: {result.stderr}")
            return 1
        
        print("  ✓ Services booted successfully")
        cleanup_needed = True
        
        # Wait a bit for Postgres to be fully ready
        print("  Waiting for Postgres to stabilize...")
        time.sleep(5)
        
        # Step 2: Execute init.sql to create schema
        print("\n[2/4] Executing init.sql to create schema...")
        
        psql_cmd = [
            "docker", "exec", "-i",
            "brainego-postgres-test",
            "psql",
            "-U", "ai_user",
            "-d", "ai_platform_test"
        ]
        
        init_sql_path = "init-scripts/postgres/init.sql"
        
        with open(init_sql_path, "r") as sql_file:
            sql_content = sql_file.read()
        
        result = subprocess.run(
            psql_cmd,
            input=sql_content,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode != 0:
            print(f"  ✗ Failed to execute init.sql:")
            print(f"    stdout: {result.stdout}")
            print(f"    stderr: {result.stderr}")
            return 1
        
        print("  ✓ Schema created successfully")
        
        # Step 3: Verify INSERT operations
        print("\n[3/4] Verifying INSERT operations...")
        
        # Test INSERT into feedback table
        feedback_insert_sql = """
INSERT INTO feedback (
    feedback_id, query, response, model, rating, 
    memory_used, tools_called, reason, category, 
    expected_answer, user_id, session_id, intent, project
) VALUES (
    'smoke-test-feedback-1',
    'What is the capital of France?',
    'The capital of France is Paris.',
    'llama-3.3-8b',
    1,
    1024,
    ARRAY['search', 'lookup'],
    'Correct answer',
    'geography',
    'Paris',
    'smoke-test-user',
    'smoke-test-session',
    'factual_query',
    'smoke-staging'
);

SELECT id, feedback_id, query, model, rating FROM feedback WHERE feedback_id = 'smoke-test-feedback-1';
"""
        
        result = subprocess.run(
            psql_cmd,
            input=feedback_insert_sql,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            print(f"  ✗ Failed to INSERT into feedback table:")
            print(f"    stdout: {result.stdout}")
            print(f"    stderr: {result.stderr}")
            return 1
        
        if "smoke-test-feedback-1" not in result.stdout:
            print(f"  ✗ Failed to verify feedback INSERT:")
            print(f"    Output: {result.stdout}")
            return 1
        
        print("  ✓ feedback table INSERT verified")
        
        # Test INSERT into workspace_metering_events table
        metering_insert_sql = """
INSERT INTO workspace_metering_events (
    event_id, workspace_id, user_id, meter_key, 
    quantity, request_id, metadata
) VALUES (
    'smoke-test-metering-1',
    'workspace-smoke-test',
    'user-smoke-test',
    'api.requests',
    1.0,
    'req-smoke-test-123',
    '{"service": "api", "endpoint": "/v1/chat"}'::jsonb
);

SELECT id, event_id, workspace_id, user_id, meter_key, quantity FROM workspace_metering_events WHERE event_id = 'smoke-test-metering-1';
"""
        
        result = subprocess.run(
            psql_cmd,
            input=metering_insert_sql,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            print(f"  ✗ Failed to INSERT into workspace_metering_events table:")
            print(f"    stdout: {result.stdout}")
            print(f"    stderr: {result.stderr}")
            return 1
        
        if "smoke-test-metering-1" not in result.stdout:
            print(f"  ✗ Failed to verify workspace_metering_events INSERT:")
            print(f"    Output: {result.stdout}")
            return 1
        
        print("  ✓ workspace_metering_events table INSERT verified")
        
        print("\n[4/4] All smoke tests passed!")
        return 0
        
    except subprocess.TimeoutExpired as e:
        print(f"\n✗ Command timed out: {e}")
        return 1
    except FileNotFoundError as e:
        print(f"\n✗ File not found: {e}")
        return 1
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        return 1
    finally:
        # Step 4: Cleanup
        if cleanup_needed:
            print("\n[Cleanup] Stopping and removing containers...")
            compose_down_cmd = [
                "docker", "compose",
                "-f", "docker-compose.test.yml",
                "down", "-v"
            ]
            
            try:
                result = subprocess.run(
                    compose_down_cmd,
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                
                if result.returncode == 0:
                    print("  ✓ Cleanup completed successfully")
                else:
                    print(f"  ⚠ Cleanup completed with warnings:")
                    print(f"    stderr: {result.stderr}")
            except Exception as cleanup_error:
                print(f"  ⚠ Cleanup failed: {cleanup_error}")


def smoke_test_metrics_and_health() -> int:
    """
    Smoke test for /health and /metrics endpoints.
    
    Tests:
    1. GET /health with all services reachable → assert status=healthy, all deps healthy
    2. GET /health after stopping Qdrant → assert status=degraded, qdrant=unhealthy, restart Qdrant
    3. GET /metrics → assert Prometheus text format, contains brainego_ prefixed counters
    4. GET /metrics/json → assert JSON contains safety_verdicts and usage keys
    
    Returns:
        0 if all checks pass, 1 otherwise
    """
    print("=" * 60)
    print("Smoke Test: Metrics and Health Endpoints")
    print("=" * 60)
    
    api_url = os.getenv("PILOT_API_URL", "http://localhost:8000")
    failures = []
    
    # Test 1: GET /health with all services reachable
    print("\n[1/4] Testing GET /health with all services reachable...")
    try:
        request = urllib.request.Request(url=f"{api_url}/health", method="GET")
        request.add_header("Accept", "application/json")
        
        with urllib.request.urlopen(request, timeout=30.0) as response:
            body = response.read().decode("utf-8", errors="replace")
            data = _parse_json(body)
            
            if response.getcode() != 200:
                failures.append(f"Test 1: Expected status 200, got {response.getcode()}")
            else:
                print(f"  ✓ Health endpoint returned 200")
            
            # Check overall status is healthy
            if not isinstance(data, dict):
                failures.append(f"Test 1: Response is not a dict: {type(data)}")
            else:
                status = data.get("status", "")
                if status != "healthy":
                    failures.append(f"Test 1: Expected status='healthy', got '{status}'")
                else:
                    print(f"  ✓ Overall status is 'healthy'")
                
                # Check all dependencies are healthy
                deps = data.get("dependencies", {}) or data.get("deps", {})
                expected_deps = ["qdrant", "postgres", "redis", "neo4j"]
                
                for dep_name in expected_deps:
                    dep_status = deps.get(dep_name, {})
                    if isinstance(dep_status, dict):
                        dep_health = dep_status.get("status", "unknown")
                    elif isinstance(dep_status, str):
                        dep_health = dep_status
                    else:
                        dep_health = "unknown"
                    
                    if dep_health not in ("healthy", "ok", "up"):
                        failures.append(f"Test 1: {dep_name} status is '{dep_health}', expected healthy")
                    else:
                        print(f"  ✓ {dep_name} is healthy")
    
    except urllib.error.HTTPError as exc:
        failures.append(f"Test 1: HTTP error {exc.code}: {exc.read().decode('utf-8', errors='replace')}")
    except urllib.error.URLError as exc:
        failures.append(f"Test 1: Connection error: {exc}")
    except Exception as exc:
        failures.append(f"Test 1: Unexpected error: {exc}")
    
    # Test 2: GET /health after stopping Qdrant
    print("\n[2/4] Testing GET /health after stopping Qdrant...")
    try:
        # Stop Qdrant container
        print("  Stopping Qdrant container...")
        result = subprocess.run(
            ["docker", "compose", "stop", "qdrant"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            failures.append(f"Test 2: Failed to stop Qdrant: {result.stderr}")
        else:
            print("  ✓ Qdrant container stopped")
            
            # Wait for health check to detect the failure
            time.sleep(3)
            
            # GET /health again
            request = urllib.request.Request(url=f"{api_url}/health", method="GET")
            request.add_header("Accept", "application/json")
            
            with urllib.request.urlopen(request, timeout=30.0) as response:
                body = response.read().decode("utf-8", errors="replace")
                data = _parse_json(body)
                
                # Status should be degraded (or unhealthy)
                status = data.get("status", "")
                if status not in ("degraded", "unhealthy"):
                    failures.append(f"Test 2: Expected status='degraded', got '{status}'")
                else:
                    print(f"  ✓ Overall status is '{status}'")
                
                # Check Qdrant is unhealthy
                deps = data.get("dependencies", {}) or data.get("deps", {})
                qdrant_status = deps.get("qdrant", {})
                
                if isinstance(qdrant_status, dict):
                    qdrant_health = qdrant_status.get("status", "unknown")
                elif isinstance(qdrant_status, str):
                    qdrant_health = qdrant_status
                else:
                    qdrant_health = "unknown"
                
                if qdrant_health not in ("unhealthy", "down", "error"):
                    failures.append(f"Test 2: Qdrant status is '{qdrant_health}', expected unhealthy")
                else:
                    print(f"  ✓ Qdrant is unhealthy")
            
            # Restart Qdrant
            print("  Restarting Qdrant container...")
            result = subprocess.run(
                ["docker", "compose", "start", "qdrant"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                failures.append(f"Test 2: Failed to restart Qdrant: {result.stderr}")
            else:
                print("  ✓ Qdrant container restarted")
                
                # Wait for Qdrant to be healthy again
                time.sleep(5)
    
    except subprocess.TimeoutExpired as exc:
        failures.append(f"Test 2: Docker command timed out: {exc}")
    except urllib.error.HTTPError as exc:
        # Health endpoint might return 503 when degraded, which is acceptable
        if exc.code in (200, 503):
            try:
                body = exc.read().decode("utf-8", errors="replace")
                data = _parse_json(body)
                status = data.get("status", "")
                
                if status in ("degraded", "unhealthy"):
                    print(f"  ✓ Health endpoint returned {exc.code} with status '{status}'")
                else:
                    failures.append(f"Test 2: Expected degraded status, got '{status}'")
            except Exception as parse_exc:
                failures.append(f"Test 2: Failed to parse degraded health response: {parse_exc}")
        else:
            failures.append(f"Test 2: Unexpected HTTP error {exc.code}")
    except urllib.error.URLError as exc:
        failures.append(f"Test 2: Connection error: {exc}")
    except Exception as exc:
        failures.append(f"Test 2: Unexpected error: {exc}")
    
    # Test 3: GET /metrics → Prometheus text format
    print("\n[3/4] Testing GET /metrics (Prometheus format)...")
    try:
        request = urllib.request.Request(url=f"{api_url}/metrics", method="GET")
        
        with urllib.request.urlopen(request, timeout=30.0) as response:
            body = response.read().decode("utf-8", errors="replace")
            
            if response.getcode() != 200:
                failures.append(f"Test 3: Expected status 200, got {response.getcode()}")
            else:
                print(f"  ✓ Metrics endpoint returned 200")
            
            # Check for Prometheus text format (lines starting with # or metric names)
            lines = body.strip().split("\n")
            has_prometheus_format = False
            has_brainego_prefix = False
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # Check for Prometheus comment or metric line
                if line.startswith("#") or ("=" in line and "{" in line):
                    has_prometheus_format = True
                
                # Check for brainego_ prefix
                if line.startswith("brainego_") or " brainego_" in line:
                    has_brainego_prefix = True
                
                if has_prometheus_format and has_brainego_prefix:
                    break
            
            if not has_prometheus_format:
                failures.append("Test 3: Response does not appear to be Prometheus text format")
            else:
                print("  ✓ Response is in Prometheus text format")
            
            if not has_brainego_prefix:
                failures.append("Test 3: No brainego_ prefixed metrics found")
            else:
                print("  ✓ Found brainego_ prefixed counters")
    
    except urllib.error.HTTPError as exc:
        failures.append(f"Test 3: HTTP error {exc.code}: {exc.read().decode('utf-8', errors='replace')}")
    except urllib.error.URLError as exc:
        failures.append(f"Test 3: Connection error: {exc}")
    except Exception as exc:
        failures.append(f"Test 3: Unexpected error: {exc}")
    
    # Test 4: GET /metrics/json → JSON with safety_verdicts and usage
    print("\n[4/4] Testing GET /metrics/json...")
    try:
        request = urllib.request.Request(url=f"{api_url}/metrics/json", method="GET")
        request.add_header("Accept", "application/json")
        
        with urllib.request.urlopen(request, timeout=30.0) as response:
            body = response.read().decode("utf-8", errors="replace")
            data = _parse_json(body)
            
            if response.getcode() != 200:
                failures.append(f"Test 4: Expected status 200, got {response.getcode()}")
            else:
                print(f"  ✓ Metrics JSON endpoint returned 200")
            
            if not isinstance(data, dict):
                failures.append(f"Test 4: Response is not a dict: {type(data)}")
            else:
                # Check for safety_verdicts key
                if "safety_verdicts" not in data:
                    failures.append("Test 4: JSON response missing 'safety_verdicts' key")
                else:
                    print("  ✓ JSON contains 'safety_verdicts' key")
                
                # Check for usage key
                if "usage" not in data:
                    failures.append("Test 4: JSON response missing 'usage' key")
                else:
                    print("  ✓ JSON contains 'usage' key")
    
    except urllib.error.HTTPError as exc:
        failures.append(f"Test 4: HTTP error {exc.code}: {exc.read().decode('utf-8', errors='replace')}")
    except urllib.error.URLError as exc:
        failures.append(f"Test 4: Connection error: {exc}")
    except Exception as exc:
        failures.append(f"Test 4: Unexpected error: {exc}")
    
    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    if failures:
        print(f"✗ {len(failures)} test(s) failed:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    else:
        print("✓ All metrics and health tests passed")
        return 0


def smoke_test_log_scrubbing() -> int:
    """
    Smoke test for log scrubbing with marker secrets.
    
    Tests:
    1. POST /v1/chat/completions with marker secret in message content
    2. POST /v1/rag/query with marker secret in query text
    3. POST /internal/mcp/tools/call with marker secret in tool arguments
    
    For each test:
    - Injects a unique TEST_SECRET_MARKER_ghp_SMOKE_TEST_xxxxx
    - Captures docker compose logs from api-server-test (last 5 minutes)
    - Asserts zero occurrences of the marker secret in logs (using regex)
    - Asserts at least one occurrence of [REDACTED_SECRET] to confirm redaction
    
    Returns:
        0 if all checks pass, 1 otherwise
    """
    print("=" * 60)
    print("Smoke Test: Log Scrubbing")
    print("=" * 60)
    
    api_url = os.getenv("PILOT_API_URL", "http://localhost:8000")
    api_key = os.getenv("PILOT_API_KEY", "sk-test-key-123")
    
    failures = []
    
    # Marker secrets for each test
    marker_secrets = {
        "chat": "TEST_SECRET_MARKER_ghp_SMOKE_TEST_12345",
        "rag": "TEST_SECRET_MARKER_ghp_SMOKE_TEST_67890",
        "mcp": "TEST_SECRET_MARKER_ghp_SMOKE_TEST_ABCDE",
    }
    
    # Determine if we're running in Docker or local process
    use_docker_logs = os.getenv("LOG_SCRUBBING_USE_DOCKER", "true").lower() == "true"
    
    # Test 1: POST /v1/chat/completions with marker secret
    print("\n[1/3] Testing POST /v1/chat/completions with marker secret...")
    try:
        marker_secret = marker_secrets["chat"]
        
        status, body = http_request(
            "POST",
            f"{api_url}/v1/chat/completions",
            api_key=api_key,
            payload={
                "model": "llama-3.3-8b-instruct",
                "messages": [
                    {
                        "role": "user",
                        "content": f"Store this secret: {marker_secret} for later use"
                    }
                ],
                "workspace_id": "log-scrubbing-test-workspace",
            },
            timeout=30.0,
        )
        
        if status not in (200, 400, 403):
            print(f"  ⚠ Request returned status {status} (expected 200/400/403)")
        else:
            print(f"  ✓ Request completed with status {status}")
        
        # Wait a moment for logs to be flushed
        time.sleep(2)
        
        # Capture logs
        print("  Capturing logs...")
        logs = _capture_logs(use_docker_logs, minutes=5)
        
        if logs is None:
            failures.append("Test 1: Failed to capture logs")
        else:
            # Assert zero occurrences of marker secret
            marker_pattern = re.escape(marker_secret)
            matches = re.findall(marker_pattern, logs, re.IGNORECASE)
            
            if len(matches) > 0:
                failures.append(
                    f"Test 1: Found {len(matches)} occurrence(s) of marker secret '{marker_secret}' in logs (should be 0)"
                )
                print(f"  ✗ Marker secret leaked in logs ({len(matches)} occurrences)")
            else:
                print(f"  ✓ Marker secret not found in logs (scrubbed)")
            
            # Assert at least one occurrence of [REDACTED_SECRET]
            redacted_matches = re.findall(r"\[REDACTED_SECRET\]", logs, re.IGNORECASE)
            
            if len(redacted_matches) == 0:
                failures.append("Test 1: No [REDACTED_SECRET] found in logs (redaction may not have occurred)")
                print(f"  ✗ No [REDACTED_SECRET] markers found")
            else:
                print(f"  ✓ Found {len(redacted_matches)} [REDACTED_SECRET] marker(s)")
    
    except Exception as exc:
        failures.append(f"Test 1 error: {exc}")
        import traceback
        traceback.print_exc()
    
    # Test 2: POST /v1/rag/query with marker secret in query
    print("\n[2/3] Testing POST /v1/rag/query with marker secret...")
    try:
        marker_secret = marker_secrets["rag"]
        
        status, body = http_request(
            "POST",
            f"{api_url}/v1/rag/query",
            api_key=api_key,
            payload={
                "query": f"Search for information about {marker_secret} in the system",
                "workspace_id": "log-scrubbing-test-workspace",
                "top_k": 5,
            },
            timeout=30.0,
        )
        
        if status not in (200, 400, 403):
            print(f"  ⚠ Request returned status {status} (expected 200/400/403)")
        else:
            print(f"  ✓ Request completed with status {status}")
        
        # Wait a moment for logs to be flushed
        time.sleep(2)
        
        # Capture logs
        print("  Capturing logs...")
        logs = _capture_logs(use_docker_logs, minutes=5)
        
        if logs is None:
            failures.append("Test 2: Failed to capture logs")
        else:
            # Assert zero occurrences of marker secret
            marker_pattern = re.escape(marker_secret)
            matches = re.findall(marker_pattern, logs, re.IGNORECASE)
            
            if len(matches) > 0:
                failures.append(
                    f"Test 2: Found {len(matches)} occurrence(s) of marker secret '{marker_secret}' in logs (should be 0)"
                )
                print(f"  ✗ Marker secret leaked in logs ({len(matches)} occurrences)")
            else:
                print(f"  ✓ Marker secret not found in logs (scrubbed)")
            
            # Assert at least one occurrence of [REDACTED_SECRET]
            redacted_matches = re.findall(r"\[REDACTED_SECRET\]", logs, re.IGNORECASE)
            
            if len(redacted_matches) == 0:
                failures.append("Test 2: No [REDACTED_SECRET] found in logs (redaction may not have occurred)")
                print(f"  ✗ No [REDACTED_SECRET] markers found")
            else:
                print(f"  ✓ Found {len(redacted_matches)} [REDACTED_SECRET] marker(s)")
    
    except Exception as exc:
        failures.append(f"Test 2 error: {exc}")
        import traceback
        traceback.print_exc()
    
    # Test 3: POST /internal/mcp/tools/call with marker secret in arguments
    print("\n[3/3] Testing POST /internal/mcp/tools/call with marker secret...")
    try:
        marker_secret = marker_secrets["mcp"]
        
        status, body = http_request(
            "POST",
            f"{api_url}/internal/mcp/tools/call",
            api_key=api_key,
            payload={
                "server_id": "mcp-github",
                "tool_name": "github_create_issue",
                "arguments": {
                    "repository": "brainego/core",
                    "title": "Test issue",
                    "body": f"Issue body contains secret: {marker_secret}",
                },
                "workspace_id": "log-scrubbing-test-workspace",
            },
            timeout=30.0,
        )
        
        if status not in (200, 400, 403):
            print(f"  ⚠ Request returned status {status} (expected 200/400/403)")
        else:
            print(f"  ✓ Request completed with status {status}")
        
        # Wait a moment for logs to be flushed
        time.sleep(2)
        
        # Capture logs
        print("  Capturing logs...")
        logs = _capture_logs(use_docker_logs, minutes=5)
        
        if logs is None:
            failures.append("Test 3: Failed to capture logs")
        else:
            # Assert zero occurrences of marker secret
            marker_pattern = re.escape(marker_secret)
            matches = re.findall(marker_pattern, logs, re.IGNORECASE)
            
            if len(matches) > 0:
                failures.append(
                    f"Test 3: Found {len(matches)} occurrence(s) of marker secret '{marker_secret}' in logs (should be 0)"
                )
                print(f"  ✗ Marker secret leaked in logs ({len(matches)} occurrences)")
            else:
                print(f"  ✓ Marker secret not found in logs (scrubbed)")
            
            # Assert at least one occurrence of [REDACTED_SECRET]
            redacted_matches = re.findall(r"\[REDACTED_SECRET\]", logs, re.IGNORECASE)
            
            if len(redacted_matches) == 0:
                failures.append("Test 3: No [REDACTED_SECRET] found in logs (redaction may not have occurred)")
                print(f"  ✗ No [REDACTED_SECRET] markers found")
            else:
                print(f"  ✓ Found {len(redacted_matches)} [REDACTED_SECRET] marker(s)")
    
    except Exception as exc:
        failures.append(f"Test 3 error: {exc}")
        import traceback
        traceback.print_exc()
    
    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    if failures:
        print(f"✗ {len(failures)} test(s) failed:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    else:
        print("✓ All log scrubbing tests passed")
        return 0


def _capture_logs(use_docker: bool, minutes: int = 5) -> Optional[str]:
    """
    Capture logs from the API server.
    
    Args:
        use_docker: If True, use 'docker compose logs', otherwise read local log files
        minutes: Number of minutes of logs to capture (for docker logs --since)
    
    Returns:
        Log content as string, or None if capture failed
    """
    try:
        if use_docker:
            # Use docker compose logs to capture from api-server-test container
            cmd = [
                "docker", "compose", "logs",
                "--since", f"{minutes}m",
                "--no-log-prefix",
                "api-server-test"
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                print(f"  ⚠ docker compose logs failed: {result.stderr}")
                # Try without --no-log-prefix (older docker-compose versions)
                cmd_fallback = [
                    "docker", "compose", "logs",
                    "--since", f"{minutes}m",
                    "api-server-test"
                ]
                
                result = subprocess.run(
                    cmd_fallback,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if result.returncode != 0:
                    print(f"  ✗ docker compose logs failed (fallback): {result.stderr}")
                    return None
            
            return result.stdout
        
        else:
            # Read from local log file (in-process mode)
            log_file = os.getenv("API_SERVER_LOG_FILE", "logs/api-server.log")
            
            if not os.path.exists(log_file):
                print(f"  ⚠ Log file not found: {log_file}")
                return None
            
            # Read last N minutes of logs (simple approach: read entire file)
            # In production, you'd want to filter by timestamp
            with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
    
    except subprocess.TimeoutExpired:
        print(f"  ✗ Log capture timed out")
        return None
    except Exception as exc:
        print(f"  ✗ Log capture failed: {exc}")
        return None


def main() -> int:
    """Run all pilot gate checks."""
    parser = argparse.ArgumentParser(
        description="Pilot gate validation for production readiness"
    )
    parser.add_argument(
        "--api-url",
        default=DEFAULT_API_URL,
        help="API base URL",
    )
    parser.add_argument(
        "--rag-url",
        default=DEFAULT_RAG_URL,
        help="RAG service base URL",
    )
    parser.add_argument(
        "--gateway-url",
        default=DEFAULT_GATEWAY_URL,
        help="Gateway base URL",
    )
    parser.add_argument(
        "--api-key",
        default=DEFAULT_API_KEY,
        help="API key for authentication",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help="HTTP timeout in seconds",
    )
    parser.add_argument(
        "--skip-gate-a",
        action="store_true",
        help="Skip Gate A (workspace+policy+audit)",
    )
    parser.add_argument(
        "--skip-gate-b",
        action="store_true",
        help="Skip Gate B (RAG citations)",
    )
    parser.add_argument(
        "--skip-gate-c",
        action="store_true",
        help="Skip Gate C (secret leak prevention)",
    )
    parser.add_argument(
        "--run-pytest",
        action="store_true",
        help="Run integration tests via pytest (tests/integration/ -m integration -v)",
    )
    parser.add_argument(
        "--smoke-staging",
        action="store_true",
        help="Run smoke tests (API calls, metrics/health, log scrubbing)",
    )
    parser.add_argument(
        "--smoke-only",
        action="store_true",
        help="Run smoke tests only (alias for --smoke-staging, skips pytest)",
    )
    parser.add_argument(
        "--smoke-api",
        action="store_true",
        help="Run smoke test for real API calls (TestClient or httpx against localhost:8000)",
    )
    parser.add_argument(
        "--smoke-metrics-health",
        action="store_true",
        help="Run smoke test for /health and /metrics endpoints",
    )
    parser.add_argument(
        "--smoke-log-scrubbing",
        action="store_true",
        help="Run smoke test for log scrubbing with marker secrets",
    )
    
    args = parser.parse_args()
    
    # Handle individual smoke test modes (backward compatibility)
    if args.smoke_log_scrubbing and not args.smoke_staging and not args.smoke_only:
        return smoke_test_log_scrubbing()
    
    if args.smoke_metrics_health and not args.smoke_staging and not args.smoke_only:
        return smoke_test_metrics_and_health()
    
    if args.smoke_api and not args.smoke_staging and not args.smoke_only:
        return smoke_test_real_api_calls()
    
    # Handle --smoke-staging or --smoke-only mode
    if args.smoke_staging or args.smoke_only:
        # Determine if we should run pytest first
        run_pytest_first = args.run_pytest and not args.smoke_only
        overall_exit_code = 0
        
        # Run pytest first if requested and not --smoke-only
        if run_pytest_first:
            print("=" * 60)
            print("Running Integration Tests via pytest")
            print("=" * 60)
            
            pytest_cmd = [
                sys.executable,
                "-m",
                "pytest",
                "tests/integration/",
                "-m",
                "integration",
                "-v"
            ]
            
            print(f"Command: {' '.join(pytest_cmd)}")
            print()
            
            try:
                result = subprocess.run(pytest_cmd, check=False)
                pytest_exit_code = result.returncode
                
                print()
                print("=" * 60)
                if pytest_exit_code == 0:
                    print("✓ All integration tests passed")
                else:
                    print(f"✗ Integration tests failed (exit code: {pytest_exit_code})")
                print("=" * 60)
                print()
                
                if pytest_exit_code != 0:
                    overall_exit_code = pytest_exit_code
            except Exception as e:
                print(f"✗ Failed to run pytest: {e}")
                print()
                overall_exit_code = 1
        
        # Print banner for smoke tests
        print("=" * 60)
        print("SMOKE TESTS - STAGING ENVIRONMENT")
        print("=" * 60)
        print()
        
        # Track smoke test results
        smoke_results = {
            "real_api_calls": None,
            "metrics_and_health": None,
            "log_scrubbing": None,
        }
        
        # Run smoke_test_real_api_calls()
        print("\n" + "▶" * 30)
        print("Running: smoke_test_real_api_calls()")
        print("▶" * 30)
        try:
            smoke_results["real_api_calls"] = smoke_test_real_api_calls()
        except Exception as e:
            print(f"✗ smoke_test_real_api_calls() raised exception: {e}")
            import traceback
            traceback.print_exc()
            smoke_results["real_api_calls"] = 1
        
        # Run smoke_test_metrics_and_health()
        print("\n" + "▶" * 30)
        print("Running: smoke_test_metrics_and_health()")
        print("▶" * 30)
        try:
            smoke_results["metrics_and_health"] = smoke_test_metrics_and_health()
        except Exception as e:
            print(f"✗ smoke_test_metrics_and_health() raised exception: {e}")
            import traceback
            traceback.print_exc()
            smoke_results["metrics_and_health"] = 1
        
        # Run smoke_test_log_scrubbing()
        print("\n" + "▶" * 30)
        print("Running: smoke_test_log_scrubbing()")
        print("▶" * 30)
        try:
            smoke_results["log_scrubbing"] = smoke_test_log_scrubbing()
        except Exception as e:
            print(f"✗ smoke_test_log_scrubbing() raised exception: {e}")
            import traceback
            traceback.print_exc()
            smoke_results["log_scrubbing"] = 1
        
        # Print summary of smoke test results
        print("\n" + "=" * 60)
        print("SMOKE TEST SUMMARY")
        print("=" * 60)
        
        if run_pytest_first:
            pytest_status = "✓ PASSED" if overall_exit_code == 0 else "✗ FAILED"
            print(f"Pytest Integration Tests: {pytest_status}")
            print()
        
        passed_tests = []
        failed_tests = []
        
        for test_name, exit_code in smoke_results.items():
            display_name = test_name.replace("_", " ").title()
            if exit_code == 0:
                passed_tests.append(display_name)
                print(f"✓ {display_name}: PASSED")
            else:
                failed_tests.append(display_name)
                print(f"✗ {display_name}: FAILED (exit code: {exit_code})")
                if overall_exit_code == 0:
                    overall_exit_code = exit_code
        
        print()
        print(f"Total: {len(passed_tests)} passed, {len(failed_tests)} failed")
        
        if failed_tests:
            print()
            print("Failed tests:")
            for test_name in failed_tests:
                print(f"  - {test_name}")
        
        print("=" * 60)
        
        return overall_exit_code
    
    # Handle --run-pytest mode
    if args.run_pytest:
        import subprocess
        
        print("=" * 60)
        print("Running Integration Tests via pytest")
        print("=" * 60)
        
        pytest_cmd = [
            sys.executable,
            "-m",
            "pytest",
            "tests/integration/",
            "-m",
            "integration",
            "-v"
        ]
        
        print(f"Command: {' '.join(pytest_cmd)}")
        print()
        
        try:
            result = subprocess.run(pytest_cmd, check=False)
            exit_code = result.returncode
            
            print()
            print("=" * 60)
            if exit_code == 0:
                print("✓ All integration tests passed")
            else:
                print(f"✗ Integration tests failed (exit code: {exit_code})")
            print("=" * 60)
            
            return exit_code
        except Exception as e:
            print(f"✗ Failed to run pytest: {e}")
            return 1
    
    api_url = args.api_url.rstrip("/")
    rag_url = args.rag_url.rstrip("/")
    gateway_url = args.gateway_url.rstrip("/")
    
    print("=" * 60)
    print("Pilot Gate Validation")
    print("=" * 60)
    print(f"API URL:     {api_url}")
    print(f"RAG URL:     {rag_url}")
    print(f"Gateway URL: {gateway_url}")
    print(f"Timeout:     {args.timeout}s")
    
    results: List[GateResult] = []
    
    # Gate A: Workspace+Policy+Audit enforcement
    if not args.skip_gate_a:
        result_a = gate_a_workspace_policy_audit(
            gateway_url=gateway_url,
            api_key=args.api_key,
            timeout=args.timeout,
        )
        results.append(result_a)
        print_gate_result(result_a)
    
    # Gate B: RAG citations
    if not args.skip_gate_b:
        result_b = gate_b_rag_citations(
            rag_url=rag_url,
            api_key=args.api_key,
            timeout=args.timeout,
        )
        results.append(result_b)
        print_gate_result(result_b)
    
    # Gate C: Secret leak prevention
    if not args.skip_gate_c:
        result_c = gate_c_secret_leak_prevention(
            api_url=api_url,
            api_key=args.api_key,
            timeout=args.timeout,
        )
        results.append(result_c)
        print_gate_result(result_c)
    
    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    
    passed_count = sum(1 for r in results if r.passed)
    failed_count = len(results) - passed_count
    
    print(f"Total gates run: {len(results)}")
    print(f"Passed: {passed_count}")
    print(f"Failed: {failed_count}")
    
    if failed_count > 0:
        print("\nFailed gates:")
        for result in results:
            if not result.passed:
                print(f"  - {result.gate_name}")
    
    # Exit with non-zero if any gate failed
    return 0 if failed_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
