#!/usr/bin/env python3
"""
MCPJungle Gateway Service - Enhanced with MCP Server Integration.

Features:
- API key authentication with role-based access control
- MCP server management and request routing
- OpenTelemetry distributed tracing
- Request routing to MAX Serve, RAG, and Memory services
- Unified /v1/chat endpoint with memory + RAG + inference integration
- MCP endpoint at /mcp for server interactions
- Performance monitoring and metrics
"""

import os
import time
import json
import uuid
import yaml
import logging
from typing import List, Dict, Optional, Any, Annotated
from datetime import datetime
from contextlib import asynccontextmanager

import uvicorn
import redis
from fastapi import FastAPI, HTTPException, Request, Header, Depends, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
import httpx

from rag_service import RAGIngestionService
from memory_service import MemoryService
from memory_scoring_config import load_memory_scoring_config
from mcp_client import MCPClientService
from mcp_acl import MCPACLManager
from mcp_write_confirmation import (
    PendingWritePlanStore,
    evaluate_write_confirmation_gate,
)
from mcp_write_confirmation import PendingWritePlanStore, requires_write_confirmation
from safety_sanitizer import redact_secrets
from workspace_context import get_valid_workspace_ids, resolve_workspace_id
from telemetry import init_telemetry, get_tracer, shutdown_telemetry
from opentelemetry import trace

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
MAX_SERVE_URL = os.getenv("MAX_SERVE_URL", "http://localhost:8080")
MAX_SERVE_HEALTH_URL = f"{MAX_SERVE_URL}/health"
MAX_SERVE_GENERATE_URL = f"{MAX_SERVE_URL}/generate"

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "documents")

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))

# MCP Configuration
MCP_SERVERS_CONFIG_PATH = os.getenv("MCP_SERVERS_CONFIG", "configs/mcp-servers.yaml")
MCP_ACL_CONFIG_PATH = os.getenv("MCP_ACL_CONFIG", "configs/mcp-acl.yaml")

# Telemetry Configuration
ENABLE_TELEMETRY = os.getenv("ENABLE_TELEMETRY", "true").lower() == "true"
OTLP_ENDPOINT = os.getenv("OTLP_ENDPOINT", "http://localhost:4317")
JAEGER_ENDPOINT = os.getenv("JAEGER_ENDPOINT", "localhost:6831")

# API Key configuration - In production, use secure key management
API_KEYS = {
    "sk-test-key-123": {"name": "test-key", "tier": "standard"},
    "sk-admin-key-456": {"name": "admin-key", "tier": "admin"},
    "sk-dev-key-789": {"name": "dev-key", "tier": "developer"}
}

# Load additional API keys from environment
ENV_API_KEYS = os.getenv("API_KEYS", "")
if ENV_API_KEYS:
    for key in ENV_API_KEYS.split(","):
        key = key.strip()
        if key:
            API_KEYS[key] = {"name": "env-key", "tier": "standard"}

WORKSPACE_ID_RESPONSE_HEADER = "X-Workspace-Id"
WORKSPACE_OPTIONAL_PATHS = {"/", "/health", "/metrics"}
WORKSPACE_OPTIONAL_PREFIXES = ("/docs", "/redoc", "/openapi.json")
WORKSPACE_REQUIRED_PREFIXES = ("/mcp",)

# Global services
rag_service = None
memory_service = None
mcp_client = None
mcp_acl = None
redis_client = None
write_confirmation_store = PendingWritePlanStore(
    ttl_seconds=int(os.getenv("MCP_WRITE_CONFIRMATION_TTL_SECONDS", "900"))
)


# Lifespan context manager for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    logger.info("=== MCPJungle Gateway Starting ===")
    
    # Initialize telemetry
    if ENABLE_TELEMETRY:
        try:
            init_telemetry(
                service_name="mcpjungle-gateway",
                service_version="1.0.0",
                otlp_endpoint=OTLP_ENDPOINT,
                jaeger_endpoint=JAEGER_ENDPOINT,
                enable_console_export=False
            )
            logger.info("✓ Telemetry initialized")
        except Exception as e:
            logger.error(f"Failed to initialize telemetry: {e}")
    
    # Initialize Redis client
    global redis_client
    try:
        redis_client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            decode_responses=True
        )
        redis_client.ping()
        logger.info("✓ Redis connected")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        redis_client = None
    
    # Load MCP configurations
    try:
        with open(MCP_SERVERS_CONFIG_PATH, 'r') as f:
            mcp_servers_config = yaml.safe_load(f)
        logger.info(f"✓ Loaded MCP servers config from {MCP_SERVERS_CONFIG_PATH}")
    except Exception as e:
        logger.error(f"Failed to load MCP servers config: {e}")
        mcp_servers_config = {"servers": {}}
    
    try:
        with open(MCP_ACL_CONFIG_PATH, 'r') as f:
            mcp_acl_config = yaml.safe_load(f)
        logger.info(f"✓ Loaded MCP ACL config from {MCP_ACL_CONFIG_PATH}")
    except Exception as e:
        logger.error(f"Failed to load MCP ACL config: {e}")
        mcp_acl_config = {"roles": {}, "default_role": "readonly"}
    
    # Initialize MCP client
    global mcp_client
    try:
        mcp_client = MCPClientService(mcp_servers_config.get("servers", {}))
        await mcp_client.initialize()
        logger.info("✓ MCP client initialized")
    except Exception as e:
        logger.error(f"Failed to initialize MCP client: {e}")
        mcp_client = None
    
    # Initialize ACL manager
    global mcp_acl
    try:
        mcp_acl = MCPACLManager(mcp_acl_config, redis_client)
        logger.info("✓ MCP ACL manager initialized")
    except Exception as e:
        logger.error(f"Failed to initialize MCP ACL manager: {e}")
        mcp_acl = None
    
    logger.info("=== MCPJungle Gateway Started ===")
    
    yield
    
    # Cleanup
    logger.info("=== MCPJungle Gateway Shutting Down ===")
    
    if mcp_client:
        await mcp_client.close_all()
    
    if ENABLE_TELEMETRY:
        shutdown_telemetry()
    
    logger.info("=== MCPJungle Gateway Stopped ===")


# Create FastAPI app
app = FastAPI(
    title="MCPJungle Gateway",
    description="Unified API Gateway with MCP, Memory, RAG, and Inference",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security scheme
security = HTTPBearer()


# Authentication dependency
async def verify_api_key(
    authorization: Annotated[HTTPAuthorizationCredentials, Depends(security)]
) -> Dict[str, Any]:
    """Verify API key from Authorization header."""
    api_key = authorization.credentials
    
    if api_key not in API_KEYS:
        safe_api_key_payload, _ = redact_secrets({"api_key": api_key})
        logger.warning("Invalid API key attempted: %s", safe_api_key_payload.get("api_key"))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )
    
    # Get role from ACL
    role = mcp_acl.get_user_role(api_key=api_key) if mcp_acl else "readonly"
    
    return {
        "api_key": api_key,
        "role": role,
        **API_KEYS[api_key]
    }


def _is_workspace_enforced_path(path: str) -> bool:
    """Return True when workspace context is mandatory for the request path."""
    if path in WORKSPACE_OPTIONAL_PATHS:
        return False
    if any(path.startswith(prefix) for prefix in WORKSPACE_OPTIONAL_PREFIXES):
        return False
    return path.startswith(WORKSPACE_REQUIRED_PREFIXES)


def _normalize_workspace_id(value: Any, context: str) -> str:
    """Normalize workspace identifier and reject empty values."""
    normalized = str(value).strip() if value is not None else ""
    if not normalized:
        raise HTTPException(status_code=400, detail=f"{context} requires workspace_id")
    return normalized


def get_current_workspace_id(request: Request) -> str:
    """Read workspace_id attached by middleware."""
    workspace_id = getattr(request.state, "workspace_id", None)
    if isinstance(workspace_id, str) and workspace_id.strip():
        return workspace_id.strip()
    raise HTTPException(status_code=500, detail="Workspace context missing")


def _resolve_workspace_for_request(
    *,
    raw_request: Request,
    provided_workspace_id: Optional[str],
    context: str,
) -> str:
    """Ensure body/query workspace selectors cannot escape request context."""
    context_workspace_id = get_current_workspace_id(raw_request)
    normalized_context_workspace = _normalize_workspace_id(context_workspace_id, context)
    if provided_workspace_id is None:
        return normalized_context_workspace

    normalized_provided_workspace = _normalize_workspace_id(provided_workspace_id, context)
    if normalized_provided_workspace != normalized_context_workspace:
        raise HTTPException(
            status_code=403,
            detail=f"{context} cannot access another workspace scope",
        )
    return normalized_context_workspace


def _ensure_workspace_arguments(
    *,
    arguments: Optional[Dict[str, Any]],
    workspace_id: str,
    context: str,
) -> Dict[str, Any]:
    """Inject workspace_id into tool arguments and reject mismatches."""
    normalized_workspace_id = _normalize_workspace_id(workspace_id, context)
    normalized_arguments = dict(arguments or {})

    existing_workspace = normalized_arguments.get("workspace_id")
    if existing_workspace is not None:
        normalized_existing_workspace = _normalize_workspace_id(existing_workspace, context)
        if normalized_existing_workspace != normalized_workspace_id:
            raise HTTPException(
                status_code=403,
                detail=f"{context} cannot access another workspace scope",
            )

    metadata = normalized_arguments.get("metadata")
    if isinstance(metadata, dict):
        normalized_metadata = dict(metadata)
        existing_metadata_workspace = normalized_metadata.get("workspace_id")
        if existing_metadata_workspace is not None:
            normalized_metadata_workspace = _normalize_workspace_id(
                existing_metadata_workspace,
                context,
            )
            if normalized_metadata_workspace != normalized_workspace_id:
                raise HTTPException(
                    status_code=403,
                    detail=f"{context} cannot access another workspace scope",
                )
        normalized_metadata["workspace_id"] = normalized_workspace_id
        normalized_arguments["metadata"] = normalized_metadata

    normalized_arguments["workspace_id"] = normalized_workspace_id
    return normalized_arguments


@app.middleware("http")
async def enforce_workspace_context(request: Request, call_next):
    """Require and validate workspace_id on all MCP endpoints."""
    path = request.url.path
    if request.method == "OPTIONS" or not _is_workspace_enforced_path(path):
        return await call_next(request)

    workspace_id = resolve_workspace_id(request)
    if not workspace_id:
        return JSONResponse(
            status_code=400,
            content={
                "detail": (
                    "Missing workspace_id. Provide X-Workspace-Id header "
                    "or workspace_id query parameter."
                ),
                "type": "workspace_error",
                "code": "workspace_id_missing",
            },
        )

    valid_workspace_ids = get_valid_workspace_ids()
    if workspace_id not in valid_workspace_ids:
        return JSONResponse(
            status_code=404,
            content={
                "detail": f"Unknown workspace_id: {workspace_id}",
                "type": "workspace_error",
                "code": "workspace_id_unknown",
            },
        )

    request.state.workspace_id = workspace_id
    response = await call_next(request)
    response.headers[WORKSPACE_ID_RESPONSE_HEADER] = workspace_id
    return response


# Pydantic models
class ChatMessage(BaseModel):
    role: str = Field(..., description="Role of the message author")
    content: str = Field(..., description="Content of the message")
    name: Optional[str] = Field(None, description="Optional name")


class MCPResourceRequest(BaseModel):
    server_id: str = Field(..., description="MCP server ID")
    uri: Optional[str] = Field(None, description="Resource URI (for read_resource)")
    workspace_id: Optional[str] = Field(None, description="Workspace scope for the MCP request")


class MCPToolRequest(BaseModel):
    server_id: str = Field(..., description="MCP server ID")
    tool_name: str = Field(..., description="Tool name to call")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Tool arguments")
    workspace_id: Optional[str] = Field(None, description="Workspace scope for the MCP request")
    confirm: bool = Field(
        default=False,
        description="Explicit confirmation for write actions that mutate issues/comments",
    )
    confirmation_id: Optional[str] = Field(
        None,
        description="Pending confirmation ID returned by an earlier unconfirmed write request",
    )


class MCPPromptRequest(BaseModel):
    server_id: str = Field(..., description="MCP server ID")
    prompt_name: str = Field(..., description="Prompt name")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Prompt arguments")
    workspace_id: Optional[str] = Field(None, description="Workspace scope for the MCP request")


class HealthResponse(BaseModel):
    status: str
    timestamp: str
    services: Dict[str, str]


# Metrics storage
class MetricsStore:
    def __init__(self):
        self.request_count = 0
        self.total_latency = 0.0
        self.latencies = []
        self.errors = 0
        self.auth_failures = 0
        self.mcp_requests = 0
        self.mcp_errors = 0

    def record_request(self, latency: float, error: bool = False, is_mcp: bool = False):
        self.request_count += 1
        if is_mcp:
            self.mcp_requests += 1
            if error:
                self.mcp_errors += 1
        if not error:
            self.total_latency += latency
            self.latencies.append(latency)
            if len(self.latencies) > 1000:
                self.latencies = self.latencies[-1000:]
        else:
            self.errors += 1

    def record_auth_failure(self):
        self.auth_failures += 1

    def get_stats(self) -> Dict[str, Any]:
        if not self.latencies:
            return {
                "request_count": self.request_count,
                "mcp_requests": self.mcp_requests,
                "mcp_errors": self.mcp_errors,
                "mcp_error_rate": 0,
                "errors": self.errors,
                "auth_failures": self.auth_failures,
                "avg_latency_ms": 0,
                "p50_latency_ms": 0,
                "p95_latency_ms": 0,
                "p99_latency_ms": 0
            }
        
        sorted_latencies = sorted(self.latencies)
        n = len(sorted_latencies)
        
        return {
            "request_count": self.request_count,
            "mcp_requests": self.mcp_requests,
            "mcp_errors": self.mcp_errors,
            "mcp_error_rate": round(self.mcp_errors / self.mcp_requests, 4) if self.mcp_requests else 0,
            "errors": self.errors,
            "auth_failures": self.auth_failures,
            "avg_latency_ms": round(self.total_latency / len(self.latencies), 2),
            "p50_latency_ms": round(sorted_latencies[int(n * 0.50)], 2),
            "p95_latency_ms": round(sorted_latencies[int(n * 0.95)], 2),
            "p99_latency_ms": round(sorted_latencies[int(n * 0.99)], 2)
        }


metrics = MetricsStore()


def get_rag_service() -> RAGIngestionService:
    """Get or initialize RAG service."""
    global rag_service
    if rag_service is None:
        logger.info("Initializing RAG Ingestion Service...")
        rag_service = RAGIngestionService(
            qdrant_host=QDRANT_HOST,
            qdrant_port=QDRANT_PORT,
            collection_name=QDRANT_COLLECTION,
            chunk_size=1000,
            chunk_overlap=100
        )
        logger.info("RAG Ingestion Service initialized")
    return rag_service


def get_memory_service() -> MemoryService:
    """Get or initialize Memory service."""
    global memory_service
    if memory_service is None:
        logger.info("Initializing Memory Service...")
        scoring_config = load_memory_scoring_config()
        memory_service = MemoryService(
            qdrant_host=QDRANT_HOST,
            qdrant_port=QDRANT_PORT,
            redis_host=REDIS_HOST,
            redis_port=REDIS_PORT,
            redis_db=REDIS_DB,
            memory_collection="memories",
            embedding_model="sentence-transformers/all-MiniLM-L6-v2",
            temporal_decay_factor=scoring_config["temporal_decay_factor"],
            cosine_weight=scoring_config["cosine_weight"],
            temporal_weight=scoring_config["temporal_weight"]
        )
        logger.info("Memory Service initialized")
    return memory_service


# Endpoints

@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "MCPJungle Gateway - MCP-Enabled AI Platform",
        "version": "1.0.0",
        "docs_url": "/docs",
        "endpoints": {
            "mcp": "/mcp",
            "unified_chat": "/v1/chat",
            "chat_completions": "/v1/chat/completions",
            "health": "/health",
            "metrics": "/metrics"
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    
    # Check MAX Serve health
    max_serve_status = "unknown"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(MAX_SERVE_HEALTH_URL)
            if response.status_code == 200:
                max_serve_status = "healthy"
            else:
                max_serve_status = "unhealthy"
    except Exception as e:
        logger.warning(f"MAX Serve health check failed: {e}")
        max_serve_status = "unreachable"
    
    # Check Qdrant health
    qdrant_status = "unknown"
    try:
        from qdrant_client import QdrantClient
        client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, timeout=5.0)
        collections = client.get_collections()
        qdrant_status = "healthy"
    except Exception as e:
        logger.warning(f"Qdrant health check failed: {e}")
        qdrant_status = "unreachable"
    
    # Check Redis health
    redis_status = "unknown"
    try:
        if redis_client:
            redis_client.ping()
            redis_status = "healthy"
        else:
            redis_status = "not_initialized"
    except Exception as e:
        logger.warning(f"Redis health check failed: {e}")
        redis_status = "unreachable"
    
    # Check MCP status
    mcp_status = "healthy" if mcp_client else "not_initialized"
    
    overall_status = "healthy"
    if max_serve_status != "healthy" or mcp_status != "healthy":
        overall_status = "degraded"
    
    return HealthResponse(
        status=overall_status,
        timestamp=datetime.utcnow().isoformat(),
        services={
            "max_serve": max_serve_status,
            "qdrant": qdrant_status,
            "redis": redis_status,
            "mcp_client": mcp_status
        }
    )


@app.get("/metrics")
async def get_metrics():
    """Get performance metrics. Public endpoint for CI/staging scrapers."""
    return {
        "metrics": metrics.get_stats(),
        "timestamp": datetime.utcnow().isoformat()
    }


# MCP Endpoints

@app.post("/mcp")
async def unified_mcp_gateway(
    request: Dict[str, Any],
    raw_request: Request,
    auth: Dict[str, Any] = Depends(verify_api_key)
):
    """Unified MCP endpoint supporting list_tools/call_tool/list_resources/read_resource."""
    action = request.get("action")
    server_id = request.get("server_id")
    workspace_id = _resolve_workspace_for_request(
        raw_request=raw_request,
        provided_workspace_id=request.get("workspace_id"),
        context="/mcp",
    )

    if not action:
        raise HTTPException(status_code=400, detail="Missing required field: action")
    if not server_id:
        raise HTTPException(status_code=400, detail="Missing required field: server_id")

    if action == "list_tools":
        return await list_mcp_tools(
            MCPResourceRequest(server_id=server_id, workspace_id=workspace_id),
            raw_request,
            auth,
        )

    if action == "call_tool":
        tool_name = request.get("tool_name")
        if not tool_name:
            raise HTTPException(status_code=400, detail="Missing required field: tool_name")
        tool_arguments = _ensure_workspace_arguments(
            arguments=request.get("arguments") or {},
            workspace_id=workspace_id,
            context="/mcp",
        )
        return await call_mcp_tool(
            MCPToolRequest(
                server_id=server_id,
                tool_name=tool_name,
                arguments=tool_arguments,
                workspace_id=workspace_id,
                confirm=bool(request.get("confirm", False)),
                confirmation_id=request.get("confirmation_id"),
            ),
            raw_request,
            auth
        )

    if action == "list_resources":
        return await list_mcp_resources(
            MCPResourceRequest(server_id=server_id, workspace_id=workspace_id),
            raw_request,
            auth,
        )

    if action == "read_resource":
        uri = request.get("uri")
        if not uri:
            raise HTTPException(status_code=400, detail="Missing required field: uri")
        return await read_mcp_resource(
            MCPResourceRequest(server_id=server_id, uri=uri, workspace_id=workspace_id),
            raw_request,
            auth,
        )

    raise HTTPException(status_code=400, detail=f"Unsupported action: {action}")

@app.get("/mcp/servers")
async def list_mcp_servers(raw_request: Request, auth: Dict[str, Any] = Depends(verify_api_key)):
    """List all available MCP servers with access control."""
    tracer = get_tracer() if ENABLE_TELEMETRY else None
    workspace_id = get_current_workspace_id(raw_request)
    
    with tracer.start_as_current_span("list_mcp_servers") if tracer else NoOpSpan():
        if not mcp_client:
            raise HTTPException(status_code=503, detail="MCP client not initialized")
        
        if not mcp_acl:
            raise HTTPException(status_code=503, detail="MCP ACL not initialized")
        
        start_time = time.time()
        
        try:
            all_servers = await mcp_client.list_servers()
            
            # Filter servers based on role permissions
            role = auth.get("role", "readonly")
            available_servers = mcp_acl.get_available_servers(role)
            
            filtered_servers = [
                s for s in all_servers 
                if s["id"] in available_servers
            ]
            
            latency_ms = (time.time() - start_time) * 1000
            metrics.record_request(latency_ms, is_mcp=True)
            
            return {
                "servers": filtered_servers,
                "total": len(filtered_servers),
                "role": role,
                "workspace_id": workspace_id,
            }
        except Exception as e:
            logger.error(f"Error listing MCP servers: {e}")
            metrics.record_request((time.time() - start_time) * 1000, error=True, is_mcp=True)
            raise HTTPException(status_code=500, detail=str(e))


@app.post("/mcp/resources/list")
async def list_mcp_resources(
    request: MCPResourceRequest,
    raw_request: Request,
    auth: Dict[str, Any] = Depends(verify_api_key)
):
    """List resources from an MCP server."""
    tracer = get_tracer() if ENABLE_TELEMETRY else None
    workspace_id = _resolve_workspace_for_request(
        raw_request=raw_request,
        provided_workspace_id=request.workspace_id,
        context="/mcp/resources/list",
    )
    
    with tracer.start_as_current_span("list_mcp_resources") if tracer else NoOpSpan():
        if not mcp_client:
            raise HTTPException(status_code=503, detail="MCP client not initialized")
        
        if not mcp_acl:
            raise HTTPException(status_code=503, detail="MCP ACL not initialized")
        
        start_time = time.time()
        role = auth.get("role", "readonly")
        identifier = f"{workspace_id}:{role}:{auth.get('api_key', '')[:10]}"
        
        try:
            # Validate access
            allowed, reason = mcp_acl.validate_request(
                role=role,
                server_id=request.server_id,
                operation_type="resource",
                operation_name="list",
                operation="read",
                identifier=identifier
            )
            
            if not allowed:
                raise HTTPException(status_code=403, detail=reason)
            
            # List resources
            resources = await mcp_client.list_resources(request.server_id)
            
            # Filter resources based on permissions
            allowed_resources = mcp_acl.get_available_resources(role, request.server_id)
            if "*" not in allowed_resources:
                resources = [
                    r for r in resources
                    if any(ar in r.get("name", "") for ar in allowed_resources)
                ]
            
            latency_ms = (time.time() - start_time) * 1000
            metrics.record_request(latency_ms, is_mcp=True)
            
            return {
                "server_id": request.server_id,
                "workspace_id": workspace_id,
                "resources": resources,
                "count": len(resources)
            }
        except HTTPException:
            metrics.record_request((time.time() - start_time) * 1000, error=True, is_mcp=True)
            raise
        except Exception as e:
            logger.error(f"Error listing resources: {e}")
            metrics.record_request((time.time() - start_time) * 1000, error=True, is_mcp=True)
            raise HTTPException(status_code=500, detail=str(e))


@app.post("/mcp/resources/read")
async def read_mcp_resource(
    request: MCPResourceRequest,
    raw_request: Request,
    auth: Dict[str, Any] = Depends(verify_api_key)
):
    """Read a resource from an MCP server."""
    tracer = get_tracer() if ENABLE_TELEMETRY else None
    workspace_id = _resolve_workspace_for_request(
        raw_request=raw_request,
        provided_workspace_id=request.workspace_id,
        context="/mcp/resources/read",
    )
    
    with tracer.start_as_current_span("read_mcp_resource") if tracer else NoOpSpan():
        if not mcp_client:
            raise HTTPException(status_code=503, detail="MCP client not initialized")
        
        if not mcp_acl:
            raise HTTPException(status_code=503, detail="MCP ACL not initialized")
        
        if not request.uri:
            raise HTTPException(status_code=400, detail="URI is required")
        
        start_time = time.time()
        role = auth.get("role", "readonly")
        identifier = f"{workspace_id}:{role}:{auth.get('api_key', '')[:10]}"
        
        try:
            # Validate access
            allowed, reason = mcp_acl.validate_request(
                role=role,
                server_id=request.server_id,
                operation_type="resource",
                operation_name=request.uri,
                operation="read",
                identifier=identifier
            )
            
            if not allowed:
                raise HTTPException(status_code=403, detail=reason)
            
            # Read resource
            resource = await mcp_client.read_resource(request.server_id, request.uri)
            
            latency_ms = (time.time() - start_time) * 1000
            metrics.record_request(latency_ms, is_mcp=True)
            
            return {
                "server_id": request.server_id,
                "workspace_id": workspace_id,
                "resource": resource
            }
        except HTTPException:
            metrics.record_request((time.time() - start_time) * 1000, error=True, is_mcp=True)
            raise
        except Exception as e:
            logger.error(f"Error reading resource: {e}")
            metrics.record_request((time.time() - start_time) * 1000, error=True, is_mcp=True)
            raise HTTPException(status_code=500, detail=str(e))


@app.post("/mcp/tools/list")
async def list_mcp_tools(
    request: MCPResourceRequest,
    raw_request: Request,
    auth: Dict[str, Any] = Depends(verify_api_key)
):
    """List tools from an MCP server."""
    tracer = get_tracer() if ENABLE_TELEMETRY else None
    workspace_id = _resolve_workspace_for_request(
        raw_request=raw_request,
        provided_workspace_id=request.workspace_id,
        context="/mcp/tools/list",
    )
    
    with tracer.start_as_current_span("list_mcp_tools") if tracer else NoOpSpan():
        if not mcp_client:
            raise HTTPException(status_code=503, detail="MCP client not initialized")
        
        if not mcp_acl:
            raise HTTPException(status_code=503, detail="MCP ACL not initialized")
        
        start_time = time.time()
        role = auth.get("role", "readonly")
        identifier = f"{workspace_id}:{role}:{auth.get('api_key', '')[:10]}"
        
        try:
            # Validate access
            allowed, reason = mcp_acl.validate_request(
                role=role,
                server_id=request.server_id,
                operation_type="tool",
                operation_name="list",
                operation="read",
                identifier=identifier
            )
            
            if not allowed:
                raise HTTPException(status_code=403, detail=reason)
            
            # List tools
            tools = await mcp_client.list_tools(request.server_id)
            
            # Filter tools based on permissions
            allowed_tools = mcp_acl.get_available_tools(role, request.server_id)
            if "*" not in allowed_tools:
                tools = [
                    t for t in tools
                    if t.get("name") in allowed_tools
                ]
            
            latency_ms = (time.time() - start_time) * 1000
            metrics.record_request(latency_ms, is_mcp=True)
            
            return {
                "server_id": request.server_id,
                "workspace_id": workspace_id,
                "tools": tools,
                "count": len(tools)
            }
        except HTTPException:
            metrics.record_request((time.time() - start_time) * 1000, error=True, is_mcp=True)
            raise
        except Exception as e:
            logger.error(f"Error listing tools: {e}")
            metrics.record_request((time.time() - start_time) * 1000, error=True, is_mcp=True)
            raise HTTPException(status_code=500, detail=str(e))


@app.post("/mcp/tools/call")
async def call_mcp_tool(
    request: MCPToolRequest,
    raw_request: Request,
    auth: Dict[str, Any] = Depends(verify_api_key)
):
    """Call a tool on an MCP server."""
    tracer = get_tracer() if ENABLE_TELEMETRY else None
    workspace_id = _resolve_workspace_for_request(
        raw_request=raw_request,
        provided_workspace_id=request.workspace_id,
        context="/mcp/tools/call",
    )
    tool_arguments = _ensure_workspace_arguments(
        arguments=request.arguments,
        workspace_id=workspace_id,
        context="/mcp/tools/call",
    )
    
    with tracer.start_as_current_span("call_mcp_tool") if tracer else NoOpSpan():
        if not mcp_client:
            raise HTTPException(status_code=503, detail="MCP client not initialized")
        
        if not mcp_acl:
            raise HTTPException(status_code=503, detail="MCP ACL not initialized")
        
        start_time = time.time()
        role = auth.get("role", "readonly")
        identifier = f"{role}:{auth.get('api_key', '')[:10]}"
        safe_arguments_payload, argument_redactions = redact_secrets({"arguments": request.arguments or {}})
        safe_arguments = safe_arguments_payload.get("arguments", {})
        logger.info(
            "call_mcp_tool server=%s tool=%s role=%s argument_redactions=%s arguments=%s",
            request.server_id,
            request.tool_name,
            role,
            argument_redactions,
            safe_arguments,
        )
        identifier = f"{workspace_id}:{role}:{auth.get('api_key', '')[:10]}"
        
        try:
            # Determine operation type (read vs write)
            write_operations = ["create", "update", "delete", "write", "append", "modify"]
            is_write = any(op in request.tool_name.lower() for op in write_operations)
            operation = "write" if is_write else "read"
            
            # Validate access
            allowed, reason = mcp_acl.validate_request(
                role=role,
                server_id=request.server_id,
                operation_type="tool",
                operation_name=request.tool_name,
                operation=operation,
                identifier=identifier
            )
            
            if not allowed:
                raise HTTPException(status_code=403, detail=reason)

            caller_id = auth.get("api_key") or identifier
            confirmation_decision = evaluate_write_confirmation_gate(
                store=write_confirmation_store,
                requested_by=caller_id,
                server_id=request.server_id,
                tool_name=request.tool_name,
                arguments=request.arguments,
                confirm=request.confirm,
                confirmation_id=request.confirmation_id,
            )
            if confirmation_decision.status_code:
            caller_id = f"{workspace_id}:{auth.get('api_key') or identifier}"
            requires_confirmation = requires_write_confirmation(request.tool_name)
            if request.confirmation_id and not request.confirm:
                raise HTTPException(
                    status_code=confirmation_decision.status_code,
                    detail=confirmation_decision.reason or "confirmation gate denied tool call",
                )
            if confirmation_decision.pending_plan:
                pending_plan = confirmation_decision.pending_plan
                latency_ms = (time.time() - start_time) * 1000
                metrics.record_request(latency_ms, is_mcp=True)
                return {
                    "server_id": request.server_id,
                    "tool_name": request.tool_name,
                    "status": "pending_confirmation",
                    "confirmation_required": True,
                    "message": (
                        "Write action requires explicit confirmation. "
                        "Re-send the exact same call with confirm=true and confirmation_id."
                    ),
                    "confirmation_id": pending_plan.confirmation_id,
                    "planned_call": pending_plan.to_public_dict(),
                }

            if requires_confirmation:
                if request.confirm and request.confirmation_id:
                    plan_matches, mismatch_reason = write_confirmation_store.consume_plan(
                        confirmation_id=request.confirmation_id,
                        requested_by=caller_id,
                        server_id=request.server_id,
                        tool_name=request.tool_name,
                        arguments=tool_arguments,
                    )
                    if not plan_matches:
                        raise HTTPException(status_code=409, detail=mismatch_reason)
                elif not request.confirm:
                    pending_plan = write_confirmation_store.create_plan(
                        requested_by=caller_id,
                        server_id=request.server_id,
                        tool_name=request.tool_name,
                        arguments=tool_arguments,
                    )
                    safe_pending_plan, pending_plan_redactions = redact_secrets(pending_plan.to_public_dict())
                    if pending_plan_redactions:
                        logger.warning(
                            "call_mcp_tool_pending_confirmation_redacted server=%s tool=%s redactions=%s",
                            request.server_id,
                            request.tool_name,
                            pending_plan_redactions,
                        )
                    latency_ms = (time.time() - start_time) * 1000
                    metrics.record_request(latency_ms, is_mcp=True)
                    return {
                        "server_id": request.server_id,
                        "workspace_id": workspace_id,
                        "tool_name": request.tool_name,
                        "status": "pending_confirmation",
                        "confirmation_required": True,
                        "message": (
                            "Write action requires explicit confirmation. "
                            "Re-send the exact same call with confirm=true and confirmation_id."
                        ),
                        "confirmation_id": pending_plan.confirmation_id,
                        "planned_call": safe_pending_plan,
                        "planned_call_redactions": pending_plan_redactions,
                    }
            
            # Call tool
            result = await mcp_client.call_tool(
                request.server_id,
                request.tool_name,
                tool_arguments
            )
            safe_result, result_redactions = redact_secrets(result)
            if result_redactions:
                logger.warning(
                    "call_mcp_tool_result_redacted server=%s tool=%s redactions=%s",
                    request.server_id,
                    request.tool_name,
                    result_redactions,
                )
            
            latency_ms = (time.time() - start_time) * 1000
            metrics.record_request(latency_ms, is_mcp=True)
            
            return {
                "server_id": request.server_id,
                "workspace_id": workspace_id,
                "tool_name": request.tool_name,
                "result": safe_result,
                "result_redactions": result_redactions,
            }
        except HTTPException:
            metrics.record_request((time.time() - start_time) * 1000, error=True, is_mcp=True)
            raise
        except Exception as e:
            safe_error, error_redactions = redact_secrets(str(e))
            logger.error(
                "Error calling tool server=%s tool=%s error=%s argument_redactions=%s error_redactions=%s",
                request.server_id,
                request.tool_name,
                safe_error,
                argument_redactions,
                error_redactions,
            )
            metrics.record_request((time.time() - start_time) * 1000, error=True, is_mcp=True)
            raise HTTPException(status_code=500, detail=safe_error)


@app.get("/mcp/acl/role")
async def get_acl_role_info(auth: Dict[str, Any] = Depends(verify_api_key)):
    """Get ACL role information for authenticated user."""
    if not mcp_acl:
        raise HTTPException(status_code=503, detail="MCP ACL not initialized")
    
    role = auth.get("role", "readonly")
    role_summary = mcp_acl.get_role_summary(role)
    
    return role_summary


# No-op span for when tracing is disabled
class NoOpSpan:
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        pass


# Authentication error handler
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Custom exception handler for authentication errors."""
    if exc.status_code == 401:
        metrics.record_auth_failure()
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "type": "authentication_error" if exc.status_code == 401 else "error"
        }
    )


if __name__ == "__main__":
    logger.info("Starting MCPJungle Gateway...")
    logger.info(f"MAX Serve URL: {MAX_SERVE_URL}")
    logger.info(f"Qdrant: {QDRANT_HOST}:{QDRANT_PORT}")
    logger.info(f"Redis: {REDIS_HOST}:{REDIS_PORT}")
    logger.info(f"Telemetry: {'enabled' if ENABLE_TELEMETRY else 'disabled'}")
    logger.info(f"MCP Servers Config: {MCP_SERVERS_CONFIG_PATH}")
    logger.info(f"MCP ACL Config: {MCP_ACL_CONFIG_PATH}")
    logger.info(f"API Keys loaded: {len(API_KEYS)}")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=9100,
        log_level="info",
        access_log=True
    )
