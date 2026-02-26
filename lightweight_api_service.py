#!/usr/bin/env python3
"""Lightweight API service that proxies chat, RAG and memory endpoints."""

import os
from typing import Dict, Set

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response

MAX_SERVE_URL = os.getenv("MAX_SERVE_URL", "http://localhost:8080").rstrip("/")
MAX_CHAT_PATH = os.getenv("MAX_CHAT_PATH", "/v1/chat/completions")
RAG_SERVICE_URL = os.getenv("RAG_SERVICE_URL", "http://localhost:8001").rstrip("/")
MEM0_SERVICE_URL = os.getenv("MEM0_SERVICE_URL", "http://localhost:8002").rstrip("/")
FORWARD_TIMEOUT_SECONDS = float(os.getenv("FORWARD_TIMEOUT_SECONDS", "20"))
REQUIRE_API_KEY = os.getenv("REQUIRE_API_KEY", "true").lower() in {"1", "true", "yes", "on"}
DEFAULT_API_KEYS = "sk-test-key-123"

ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
EXCLUDED_HEADERS = {"host", "content-length", "connection"}

app = FastAPI(
    title="Lightweight API Service",
    version="1.1.0",
    description="Minimal API façade forwarding /v1/chat, /v1/rag/query and /memory/* requests.",
)


def _load_valid_api_keys() -> Set[str]:
    """Load allowed API keys from env (comma-separated) with a safe default for local MVP runs."""
    configured = os.getenv("API_KEYS", DEFAULT_API_KEYS)
    return {key.strip() for key in configured.split(",") if key.strip()}


VALID_API_KEYS = _load_valid_api_keys()


def _extract_api_key(request: Request) -> str:
    """Extract API key from x-api-key header or Bearer Authorization token."""
    x_api_key = request.headers.get("x-api-key")
    if x_api_key:
        return x_api_key.strip()

    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()

    return ""


@app.middleware("http")
async def enforce_api_key(request: Request, call_next):
    """Protect MVP endpoints with API key authentication."""
    protected_prefixes = ("/v1/chat", "/v1/rag/query", "/memory/")
    if REQUIRE_API_KEY and request.url.path.startswith(protected_prefixes):
        provided_key = _extract_api_key(request)
        if not provided_key or provided_key not in VALID_API_KEYS:
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


async def _forward_request(request: Request, downstream_url: str) -> Response:
    """Forward the incoming request and return downstream response transparently."""
    try:
        body = await request.body()
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

    return Response(
        content=response.content,
        status_code=response.status_code,
        media_type=response.headers.get("content-type"),
        headers=response_headers,
    )


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse(
        {
            "status": "ok",
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
