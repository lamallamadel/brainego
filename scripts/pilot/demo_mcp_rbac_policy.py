#!/usr/bin/env python3
"""Pilot demo: validate MCP connectivity + RBAC behavior (AFR-96)."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple


DEFAULT_GATEWAY_URL = "http://localhost:9100"
DEFAULT_ADMIN_KEY = os.getenv("PILOT_ADMIN_KEY", "sk-admin-key-456")
DEFAULT_ANALYST_KEY = os.getenv("PILOT_ANALYST_KEY", "sk-test-key-123")


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


def _parse_json(payload: str) -> Any:
    payload = (payload or "").strip()
    if not payload:
        return {}
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return {"raw": payload}


def request_json(
    method: str,
    url: str,
    *,
    api_key: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    timeout: float = 10.0,
) -> Tuple[int, Any]:
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


def run_check(name: str, passed: bool, detail: str) -> CheckResult:
    prefix = "[PASS]" if passed else "[FAIL]"
    print(f"{prefix} {name}: {detail}")
    return CheckResult(name=name, passed=passed, detail=detail)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate MCP gateway RBAC and policy behavior for pilot readiness."
    )
    parser.add_argument("--gateway-url", default=DEFAULT_GATEWAY_URL, help="MCP gateway base URL")
    parser.add_argument("--admin-key", default=DEFAULT_ADMIN_KEY, help="Admin API key")
    parser.add_argument("--analyst-key", default=DEFAULT_ANALYST_KEY, help="Analyst/read-only API key")
    parser.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout in seconds")
    args = parser.parse_args()

    gateway_url = args.gateway_url.rstrip("/")
    timeout = float(args.timeout)
    checks: list[CheckResult] = []

    print("=== Pilot MCP RBAC/Policy Validation ===")
    print(f"Gateway URL: {gateway_url}")
    print("")

    status, body = request_json("GET", f"{gateway_url}/health", timeout=timeout)
    checks.append(
        run_check(
            "Gateway health",
            status == 200,
            f"status={status}",
        )
    )

    status, body = request_json(
        "GET",
        f"{gateway_url}/mcp/acl/role",
        api_key=args.admin_key,
        timeout=timeout,
    )
    admin_role = body.get("role") if isinstance(body, dict) else None
    checks.append(
        run_check(
            "Admin role mapping",
            status == 200 and admin_role == "admin",
            f"status={status}, role={admin_role}",
        )
    )

    status, body = request_json(
        "GET",
        f"{gateway_url}/mcp/acl/role",
        api_key=args.analyst_key,
        timeout=timeout,
    )
    analyst_role = body.get("role") if isinstance(body, dict) else None
    checks.append(
        run_check(
            "Analyst role mapping",
            status == 200 and analyst_role == "analyst",
            f"status={status}, role={analyst_role}",
        )
    )

    status, body = request_json(
        "GET",
        f"{gateway_url}/mcp/servers",
        api_key=args.analyst_key,
        timeout=timeout,
    )
    server_ids = []
    if isinstance(body, dict):
        for server in body.get("servers", []):
            if isinstance(server, dict):
                server_ids.append(str(server.get("id", "")))
    checks.append(
        run_check(
            "Analyst server discovery",
            status == 200 and "mcp-filesystem" in server_ids,
            f"status={status}, servers={server_ids}",
        )
    )

    status, body = request_json(
        "POST",
        f"{gateway_url}/mcp/tools/list",
        api_key=args.analyst_key,
        payload={"server_id": "mcp-filesystem"},
        timeout=timeout,
    )
    tools = []
    if isinstance(body, dict):
        for tool in body.get("tools", []):
            if isinstance(tool, dict):
                tools.append(str(tool.get("name", "")))
    checks.append(
        run_check(
            "Analyst tool discovery",
            status == 200 and "read_file" in tools and "write_file" not in tools,
            f"status={status}, tools={tools[:10]}",
        )
    )

    status, body = request_json(
        "POST",
        f"{gateway_url}/mcp/tools/call",
        api_key=args.analyst_key,
        payload={
            "server_id": "mcp-filesystem",
            "tool_name": "write_file",
            "arguments": {
                "path": "/workspace/pilot_forbidden_write.txt",
                "content": "this write should be denied for analyst role",
            },
        },
        timeout=timeout,
    )
    checks.append(
        run_check(
            "RBAC deny write for analyst",
            status == 403,
            f"status={status}, detail={body}",
        )
    )

    passed = sum(1 for item in checks if item.passed)
    failed = len(checks) - passed
    print("")
    print("=== Summary ===")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
