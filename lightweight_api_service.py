#!/usr/bin/env python3
"""Lightweight API service that proxies chat, RAG and memory endpoints."""

import os
import json
import re
from typing import Dict, Set

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response

MAX_SERVE_URL = os.getenv("MAX_SERVE_URL", "http://localhost:8080").rstrip("/")
MAX_CHAT_PATH = os.getenv("MAX_CHAT_PATH", "/v1/chat/completions")
RAG_SERVICE_URL = os.getenv("RAG_SERVICE_URL", "http://localhost:8001").rstrip("/")
MEM0_SERVICE_URL = os.getenv("MEM0_SERVICE_URL", "http://localhost:8002").rstrip("/")
FORWARD_TIMEOUT_SECONDS = float(os.getenv("FORWARD_TIMEOUT_SECONDS", "20"))

ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
EXCLUDED_HEADERS = {"host", "content-length", "connection"}

GUARDRAIL_SUSPICIOUS_REQUEST_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(print|show|dump|reveal|exfiltrat(e|ion)|leak)\b.{0,80}\b(secret|credential|token|api[_ -]?key)\b",
        r"\b(os\.environ|environment variable|env var|\.env|process\.env)\b",
        r"\b(internal config|runtime config|system prompt|service account)\b",
    )
]
GUARDRAIL_SECRET_OUTPUT_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bsk-[a-z0-9]{8,}\b",
        r"\b(api[_ -]?key|token|secret|password)\s*[:=]\s*[\"']?[a-z0-9_\-\/+=]{6,}[\"']?",
        r"\b(aws_access_key_id|aws_secret_access_key|client_secret)\b",
    )
]

app = FastAPI(
    title="Lightweight API Service",
    version="1.2.0",
    description="Minimal API façade forwarding /v1/chat, /v1/rag/query and /memory/* requests.",
)


def _is_auth_enabled() -> bool:
    """Return whether API key auth is enabled (default: enabled)."""
    return os.getenv("REQUIRE_API_KEY", "true").lower() in {"1", "true", "yes", "on"}


def _load_valid_api_keys() -> Set[str]:
    """Load allowed API keys from env (comma-separated)."""
    configured = os.getenv("API_KEYS", "")
    return {key.strip() for key in configured.split(",") if key.strip()}


def _extract_api_key(request: Request) -> str:
    """Extract API key from x-api-key header or Bearer Authorization token."""
    x_api_key = request.headers.get("x-api-key")
    if x_api_key:
        return x_api_key.strip()

    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()

    return ""


def _is_protected_path(path: str) -> bool:
    """Return True when request path must be authenticated for MVP."""
    return path in {"/v1/chat", "/v1/rag/query", "/memory"} or path.startswith("/memory/")


@app.middleware("http")
async def enforce_api_key(request: Request, call_next):
    """Protect MVP endpoints with API key authentication."""
    if request.method == "OPTIONS":
        return await call_next(request)

    if _is_auth_enabled() and _is_protected_path(request.url.path):
        valid_api_keys = _load_valid_api_keys()
        provided_key = _extract_api_key(request)
        if not provided_key or not valid_api_keys or provided_key not in valid_api_keys:
            return JSONResponse(
                status_code=401,
                content={
                    "detail": "Invalid or missing API key",
                    "type": "authentication_error",
                },
                headers={"WWW-Authenticate": "Bearer"},
            )

    return await call_next(request)


def _forward_headers(request: Request) -> Dict[str, str]:
    """Return inbound headers safe to forward downstream."""
    return {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in EXCLUDED_HEADERS
    }


def _guardrail_mode() -> str:
    """Return safety policy mode for secret/exfiltration guardrails."""
    mode = os.getenv("SAFETY_GUARDRAIL_MODE", "block").strip().lower()
    if mode not in {"off", "block", "redact"}:
        return "block"
    return mode


def _extract_text_values(payload):
    if isinstance(payload, str):
        yield payload
    elif isinstance(payload, list):
        for item in payload:
            yield from _extract_text_values(item)
    elif isinstance(payload, dict):
        for value in payload.values():
            yield from _extract_text_values(value)


def _contains_suspicious_exfiltration_request(raw_body: bytes) -> bool:
    if not raw_body:
        return False

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        return False

    for text in _extract_text_values(payload):
        normalized = text.strip()
        if not normalized:
            continue
        for pattern in GUARDRAIL_SUSPICIOUS_REQUEST_PATTERNS:
            if pattern.search(normalized):
                return True
    return False


def _redact_secrets(content: bytes) -> bytes:
    text = content.decode("utf-8", errors="ignore")
    for pattern in GUARDRAIL_SECRET_OUTPUT_PATTERNS:
        text = pattern.sub("[REDACTED_SECRET]", text)
    return text.encode("utf-8")


def _contains_secret_like_output(content: bytes) -> bool:
    text = content.decode("utf-8", errors="ignore")
    return any(pattern.search(text) for pattern in GUARDRAIL_SECRET_OUTPUT_PATTERNS)


async def _forward_request(request: Request, downstream_url: str) -> Response:
    """Forward the incoming request and return downstream response transparently."""
    try:
        body = await request.body()
        mode = _guardrail_mode()
        if mode != "off" and _contains_suspicious_exfiltration_request(body):
            if mode == "block":
                raise HTTPException(
                    status_code=403,
                    detail="Request blocked by safety policy: secret or environment exfiltration attempt detected",
                )
            body = json.dumps({"guardrail": "Request content redacted by safety policy"}).encode("utf-8")

        async with httpx.AsyncClient(timeout=FORWARD_TIMEOUT_SECONDS) as client:
            response = await client.request(
                method=request.method,
                url=downstream_url,
                params=request.query_params,
                content=body if body else None,
                headers=_forward_headers(request),
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail=f"Downstream timeout: {downstream_url}") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Downstream request failed: {downstream_url}") from exc

    response_headers = {
        key: value
        for key, value in response.headers.items()
        if key.lower() not in EXCLUDED_HEADERS
    }

    mode = _guardrail_mode()
    response_content = response.content
    if mode != "off" and _contains_secret_like_output(response_content):
        if mode == "block":
            raise HTTPException(
                status_code=403,
                detail="Response blocked by safety policy: secret or credential leakage detected",
            )
        response_content = _redact_secrets(response_content)

    return Response(
        content=response_content,
        status_code=response.status_code,
        media_type=response.headers.get("content-type"),
        headers=response_headers,
    )


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse(
        {
            "status": "ok",
            "auth_enabled": _is_auth_enabled(),
            "routes": {
                "chat": f"{MAX_SERVE_URL}{MAX_CHAT_PATH}",
                "rag_query": f"{RAG_SERVICE_URL}/v1/rag/query",
                "memory": f"{MEM0_SERVICE_URL}/memory/*",
            },
        }
    )


@app.api_route("/v1/chat", methods=["POST"])
async def chat_proxy(request: Request) -> Response:
    return await _forward_request(request, f"{MAX_SERVE_URL}{MAX_CHAT_PATH}")


@app.api_route("/v1/rag/query", methods=["POST"])
async def rag_query_proxy(request: Request) -> Response:
    return await _forward_request(request, f"{RAG_SERVICE_URL}/v1/rag/query")


@app.api_route("/memory/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def memory_proxy(path: str, request: Request) -> Response:
    if request.method not in ALLOWED_METHODS:
        raise HTTPException(status_code=405, detail="Method not allowed")
    return await _forward_request(request, f"{MEM0_SERVICE_URL}/memory/{path}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=9010)
