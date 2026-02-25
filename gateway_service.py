#!/usr/bin/env python3
"""
Unified API Gateway Service for AI Platform.

Features:
- API key authentication
- Request routing to MAX Serve, RAG, and Memory services
- Unified /v1/chat endpoint with memory + RAG + inference integration
- Performance monitoring and metrics
- OpenAI-compatible endpoints
"""

import os
import time
import json
import uuid
import logging
import signal
import asyncio
from typing import List, Dict, Optional, Any, Annotated
from datetime import datetime

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Header, Depends, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
import httpx

from rag_service import RAGIngestionService
from memory_service import MemoryService
from circuit_breaker import get_circuit_breaker, CircuitBreakerConfig, CircuitBreakerError, get_all_circuit_breaker_stats

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

# Create FastAPI app
app = FastAPI(
    title="AI Platform API Gateway",
    description="Unified API Gateway with Memory, RAG, and Inference",
    version="1.0.0"
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
        logger.warning(f"Invalid API key attempted: {api_key[:10]}...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )
    
    return {
        "api_key": api_key,
        **API_KEYS[api_key]
    }


# Pydantic models
class ChatMessage(BaseModel):
    role: str = Field(..., description="Role of the message author")
    content: str = Field(..., description="Content of the message")
    name: Optional[str] = Field(None, description="Optional name")


class ChatCompletionRequest(BaseModel):
    model: str = Field(default="llama-3.3-8b-instruct", description="Model to use")
    messages: List[ChatMessage] = Field(..., description="List of messages")
    temperature: Optional[float] = Field(0.7, ge=0.0, le=2.0)
    top_p: Optional[float] = Field(0.9, ge=0.0, le=1.0)
    max_tokens: Optional[int] = Field(2048, ge=1)
    stream: Optional[bool] = Field(False)
    user: Optional[str] = Field(None, description="User identifier")


class UnifiedChatRequest(BaseModel):
    model: str = Field(default="llama-3.3-8b-instruct", description="Model to use")
    messages: List[ChatMessage] = Field(..., description="List of messages")
    temperature: Optional[float] = Field(0.7, ge=0.0, le=2.0)
    top_p: Optional[float] = Field(0.9, ge=0.0, le=1.0)
    max_tokens: Optional[int] = Field(2048, ge=1)
    user_id: Optional[str] = Field(None, description="User ID for personalized memory")
    use_memory: Optional[bool] = Field(True, description="Enable memory retrieval")
    use_rag: Optional[bool] = Field(True, description="Enable RAG context retrieval")
    rag_k: Optional[int] = Field(3, ge=1, le=10, description="Number of RAG documents to retrieve")
    memory_limit: Optional[int] = Field(5, ge=1, le=20, description="Number of memories to retrieve")
    store_memory: Optional[bool] = Field(True, description="Store this conversation in memory")


class ChatCompletionChoice(BaseModel):
    index: int
    message: ChatMessage
    finish_reason: str


class ChatCompletionUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[ChatCompletionChoice]
    usage: ChatCompletionUsage


class UnifiedChatResponse(BaseModel):
    id: str
    object: str = "unified.chat.completion"
    created: int
    model: str
    choices: List[ChatCompletionChoice]
    usage: ChatCompletionUsage
    context: Optional[Dict[str, Any]] = Field(None, description="Retrieved context from memory and RAG")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


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

    def record_request(self, latency: float, error: bool = False):
        self.request_count += 1
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
            "errors": self.errors,
            "auth_failures": self.auth_failures,
            "avg_latency_ms": round(self.total_latency / len(self.latencies), 2),
            "p50_latency_ms": round(sorted_latencies[int(n * 0.50)], 2),
            "p95_latency_ms": round(sorted_latencies[int(n * 0.95)], 2),
            "p99_latency_ms": round(sorted_latencies[int(n * 0.99)], 2)
        }


metrics = MetricsStore()

# Service instances (lazy initialization)
rag_service = None
memory_service = None

# Circuit breaker for MAX Serve
max_serve_breaker = get_circuit_breaker(
    "max_serve_gateway",
    CircuitBreakerConfig(
        failure_threshold=3,
        timeout_seconds=5.0,
        recovery_timeout_seconds=30.0,
        success_threshold=2
    )
)

# Graceful shutdown flag
shutdown_in_progress = False


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
        memory_service = MemoryService(
            qdrant_host=QDRANT_HOST,
            qdrant_port=QDRANT_PORT,
            redis_host=REDIS_HOST,
            redis_port=REDIS_PORT,
            redis_db=REDIS_DB,
            memory_collection="memories",
            embedding_model="sentence-transformers/all-MiniLM-L6-v2",
            temporal_decay_factor=0.1
        )
        logger.info("Memory Service initialized")
    return memory_service


def format_chat_prompt(messages: List[ChatMessage]) -> str:
    """Format messages into Llama 3.3 chat format."""
    prompt_parts = []
    
    for message in messages:
        role = message.role
        content = message.content
        
        if role == "system":
            prompt_parts.append(f"<|start_header_id|>system<|end_header_id|>\n\n{content}<|eot_id|>")
        elif role == "user":
            prompt_parts.append(f"<|start_header_id|>user<|end_header_id|>\n\n{content}<|eot_id|>")
        elif role == "assistant":
            prompt_parts.append(f"<|start_header_id|>assistant<|end_header_id|>\n\n{content}<|eot_id|>")
    
    # Add assistant header for response
    prompt_parts.append("<|start_header_id|>assistant<|end_header_id|>\n\n")
    
    return "".join(prompt_parts)


def estimate_tokens(text: str) -> int:
    """Rough token estimation (4 chars ≈ 1 token)."""
    return len(text) // 4


async def call_max_serve(prompt: str, params: Dict[str, Any]) -> tuple[str, int, int]:
    """Call MAX Serve API with circuit breaker protection."""
    
    payload = {
        "prompt": prompt,
        "max_tokens": params.get("max_tokens", 2048),
        "temperature": params.get("temperature", 0.7),
        "top_p": params.get("top_p", 0.9),
        "stop": params.get("stop", ["<|eot_id|>", "<|end_of_text|>"]),
    }
    
    async def make_request():
        """Inner function for circuit breaker."""
        async with httpx.AsyncClient() as client:
            response = await client.post(MAX_SERVE_GENERATE_URL, json=payload)
            response.raise_for_status()
            
            result = response.json()
            generated_text = result.get("text", "").strip()
            
            # Estimate tokens
            prompt_tokens = estimate_tokens(prompt)
            completion_tokens = estimate_tokens(generated_text)
            
            return generated_text, prompt_tokens, completion_tokens
    
    try:
        return await max_serve_breaker.call(make_request)
    except CircuitBreakerError as e:
        logger.error(f"Circuit breaker open for MAX Serve: {e}")
        raise HTTPException(status_code=503, detail="MAX Serve temporarily unavailable (circuit breaker open)")
    except httpx.HTTPError as e:
        logger.error(f"MAX Serve API error: {e}")
        raise HTTPException(status_code=503, detail=f"MAX Serve error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error calling MAX Serve: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


# Endpoints

@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "AI Platform API Gateway",
        "version": "1.0.0",
        "docs_url": "/docs",
        "endpoints": {
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
        import redis
        r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, socket_timeout=5)
        r.ping()
        redis_status = "healthy"
    except Exception as e:
        logger.warning(f"Redis health check failed: {e}")
        redis_status = "unreachable"
    
    overall_status = "healthy"
    if max_serve_status != "healthy":
        overall_status = "degraded"
    
    return HealthResponse(
        status=overall_status,
        timestamp=datetime.utcnow().isoformat(),
        services={
            "max_serve": max_serve_status,
            "qdrant": qdrant_status,
            "redis": redis_status
        }
    )


@app.get("/metrics")
async def get_metrics(auth: Dict[str, Any] = Depends(verify_api_key)):
    """Get performance metrics. Requires authentication."""
    return {
        "metrics": metrics.get_stats(),
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/circuit-breakers")
async def get_circuit_breakers_stats(auth: Dict[str, Any] = Depends(verify_api_key)):
    """Get circuit breaker statistics. Requires authentication."""
    return {
        "circuit_breakers": get_all_circuit_breaker_stats(),
        "timestamp": datetime.utcnow().isoformat()
    }


@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(
    request: ChatCompletionRequest,
    auth: Dict[str, Any] = Depends(verify_api_key)
):
    """
    OpenAI-compatible chat completions endpoint with authentication.
    """
    start_time = time.time()
    
    try:
        # Validate request
        if not request.messages:
            raise HTTPException(status_code=400, detail="Messages list cannot be empty")
        
        # Format prompt
        prompt = format_chat_prompt(request.messages)
        logger.info(f"Processing chat completion request from {auth['name']}")
        
        # Call MAX Serve
        params = {
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "top_p": request.top_p,
            "stop": ["<|eot_id|>", "<|end_of_text|>"],
        }
        
        generated_text, prompt_tokens, completion_tokens = await call_max_serve(prompt, params)
        
        # Calculate latency
        latency_ms = (time.time() - start_time) * 1000
        metrics.record_request(latency_ms)
        
        # Build response
        response = ChatCompletionResponse(
            id=f"chatcmpl-{uuid.uuid4().hex[:24]}",
            created=int(time.time()),
            model=request.model,
            choices=[
                ChatCompletionChoice(
                    index=0,
                    message=ChatMessage(role="assistant", content=generated_text),
                    finish_reason="stop"
                )
            ],
            usage=ChatCompletionUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens
            )
        )
        
        logger.info(f"Request completed in {latency_ms:.2f}ms")
        
        return response
        
    except HTTPException:
        metrics.record_request((time.time() - start_time) * 1000, error=True)
        raise
    except Exception as e:
        metrics.record_request((time.time() - start_time) * 1000, error=True)
        logger.error(f"Unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/chat", response_model=UnifiedChatResponse)
async def unified_chat(
    request: UnifiedChatRequest,
    auth: Dict[str, Any] = Depends(verify_api_key)
):
    """
    Unified chat endpoint integrating Memory + RAG + Inference.
    
    This endpoint provides a complete conversational AI experience:
    
    1. **Memory Retrieval**: Retrieves relevant memories based on conversation context
    2. **RAG Context**: Fetches relevant documents from knowledge base
    3. **Augmented Inference**: Generates response with memory and RAG context
    4. **Memory Storage**: Optionally stores the conversation for future reference
    
    Performance target: < 3s end-to-end latency
    
    Args:
        model: Model to use for generation
        messages: Conversation messages
        user_id: User identifier for personalized memory
        use_memory: Enable memory retrieval
        use_rag: Enable RAG context retrieval
        rag_k: Number of RAG documents to retrieve
        memory_limit: Number of memories to retrieve
        store_memory: Store this conversation in memory
        temperature: Sampling temperature
        top_p: Nucleus sampling parameter
        max_tokens: Maximum tokens to generate
    
    Returns:
        Generated response with context information and usage stats
    """
    start_time = time.time()
    
    try:
        if not request.messages:
            raise HTTPException(status_code=400, detail="Messages list cannot be empty")
        
        logger.info(f"Unified chat request from {auth['name']} (user_id: {request.user_id})")
        
        # Initialize context storage
        memory_context = []
        rag_context = []
        retrieval_stats = {}
        
        # Extract query from last user message
        user_query = None
        for msg in reversed(request.messages):
            if msg.role == "user":
                user_query = msg.content
                break
        
        if not user_query:
            raise HTTPException(status_code=400, detail="No user message found")
        
        # Step 1: Retrieve memories (if enabled)
        if request.use_memory:
            memory_start = time.time()
            try:
                memory_svc = get_memory_service()
                memory_results = memory_svc.search_memory(
                    query=user_query,
                    user_id=request.user_id,
                    limit=request.memory_limit,
                    use_temporal_decay=True
                )
                memory_context = memory_results
                memory_time_ms = (time.time() - memory_start) * 1000
                retrieval_stats["memory_retrieval_ms"] = round(memory_time_ms, 2)
                retrieval_stats["memories_retrieved"] = len(memory_results)
                logger.info(f"Retrieved {len(memory_results)} memories in {memory_time_ms:.2f}ms")
            except Exception as e:
                logger.warning(f"Memory retrieval failed: {e}")
                retrieval_stats["memory_error"] = str(e)
        
        # Step 2: Retrieve RAG context (if enabled)
        if request.use_rag:
            rag_start = time.time()
            try:
                rag_svc = get_rag_service()
                rag_results = rag_svc.search_documents(
                    query=user_query,
                    limit=request.rag_k
                )
                rag_context = rag_results
                rag_time_ms = (time.time() - rag_start) * 1000
                retrieval_stats["rag_retrieval_ms"] = round(rag_time_ms, 2)
                retrieval_stats["rag_documents_retrieved"] = len(rag_results)
                logger.info(f"Retrieved {len(rag_results)} RAG documents in {rag_time_ms:.2f}ms")
            except Exception as e:
                logger.warning(f"RAG retrieval failed: {e}")
                retrieval_stats["rag_error"] = str(e)
        
        # Step 3: Build augmented prompt
        messages_list = []
        
        # Construct system message with context
        context_parts = []
        
        if memory_context:
            memory_texts = [
                f"- {m['text'][:200]}..." if len(m.get('text', '')) > 200 else f"- {m.get('text', '')}"
                for m in memory_context[:3]  # Limit to top 3 memories
            ]
            context_parts.append("**Relevant Memories:**\n" + "\n".join(memory_texts))
        
        if rag_context:
            rag_texts = [
                f"[Doc {i+1}] {r['text'][:300]}..." if len(r.get('text', '')) > 300 else f"[Doc {i+1}] {r.get('text', '')}"
                for i, r in enumerate(rag_context[:request.rag_k])
            ]
            context_parts.append("**Knowledge Base Context:**\n" + "\n".join(rag_texts))
        
        if context_parts:
            system_content = (
                "You are a helpful AI assistant with access to user memories and a knowledge base. "
                "Use the following context to provide personalized and informed responses. "
                "If the context doesn't contain relevant information, rely on your general knowledge.\n\n"
                + "\n\n".join(context_parts)
            )
        else:
            system_content = "You are a helpful AI assistant."
        
        messages_list.append(ChatMessage(role="system", content=system_content))
        
        # Add conversation history
        messages_list.extend(request.messages)
        
        # Step 4: Generate response
        prompt = format_chat_prompt(messages_list)
        
        params = {
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "top_p": request.top_p,
            "stop": ["<|eot_id|>", "<|end_of_text|>"],
        }
        
        generation_start = time.time()
        generated_text, prompt_tokens, completion_tokens = await call_max_serve(prompt, params)
        generation_time_ms = (time.time() - generation_start) * 1000
        retrieval_stats["generation_ms"] = round(generation_time_ms, 2)
        
        # Step 5: Store memory (if enabled)
        if request.store_memory:
            try:
                memory_svc = get_memory_service()
                # Add the new assistant response to messages
                conversation_messages = [
                    {"role": msg.role, "content": msg.content}
                    for msg in request.messages
                ]
                conversation_messages.append({
                    "role": "assistant",
                    "content": generated_text
                })
                
                memory_result = memory_svc.add_memory(
                    messages=conversation_messages,
                    user_id=request.user_id,
                    metadata={
                        "timestamp": datetime.utcnow().isoformat(),
                        "source": "unified_chat"
                    }
                )
                retrieval_stats["memory_stored"] = True
                retrieval_stats["memory_id"] = memory_result.get("memory_id")
                logger.info(f"Stored conversation in memory: {memory_result.get('memory_id')}")
            except Exception as e:
                logger.warning(f"Failed to store memory: {e}")
                retrieval_stats["memory_store_error"] = str(e)
        
        # Calculate total latency
        total_latency_ms = (time.time() - start_time) * 1000
        retrieval_stats["total_latency_ms"] = round(total_latency_ms, 2)
        metrics.record_request(total_latency_ms)
        
        # Build context response
        context_info = {}
        if memory_context:
            context_info["memories"] = [
                {
                    "text": m.get("text", "")[:200],
                    "score": m.get("score", 0),
                    "timestamp": m.get("timestamp")
                }
                for m in memory_context[:3]
            ]
        if rag_context:
            context_info["rag_documents"] = [
                {
                    "text": r.get("text", "")[:200],
                    "score": r.get("score", 0),
                    "metadata": r.get("metadata")
                }
                for r in rag_context[:request.rag_k]
            ]
        
        # Build response
        response = UnifiedChatResponse(
            id=f"unified-{uuid.uuid4().hex[:24]}",
            created=int(time.time()),
            model=request.model,
            choices=[
                ChatCompletionChoice(
                    index=0,
                    message=ChatMessage(role="assistant", content=generated_text),
                    finish_reason="stop"
                )
            ],
            usage=ChatCompletionUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens
            ),
            context=context_info if context_info else None,
            metadata=retrieval_stats
        )
        
        logger.info(
            f"Unified chat completed in {total_latency_ms:.2f}ms "
            f"(target: <3000ms, {'✓' if total_latency_ms < 3000 else '✗'})"
        )
        
        return response
        
    except HTTPException:
        metrics.record_request((time.time() - start_time) * 1000, error=True)
        raise
    except Exception as e:
        metrics.record_request((time.time() - start_time) * 1000, error=True)
        logger.error(f"Unexpected error in unified chat: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# Authentication error handler
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Custom exception handler for authentication errors."""
    if exc.status_code == 401:
        metrics.record_auth_failure()
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "type": "authentication_error" if exc.status_code == 401 else "error"}
    )


@app.on_event("shutdown")
async def shutdown_event():
    """Graceful shutdown handler."""
    global shutdown_in_progress
    shutdown_in_progress = True
    
    logger.info("Shutting down Gateway gracefully...")
    
    # Wait for in-flight requests
    logger.info("Waiting for in-flight requests to complete...")
    await asyncio.sleep(5)
    
    logger.info("Gateway shutdown complete")


def handle_sigterm(signum, frame):
    """Handle SIGTERM for graceful shutdown."""
    logger.info("Received SIGTERM signal, initiating graceful shutdown...")
    raise KeyboardInterrupt


# Register signal handlers
signal.signal(signal.SIGTERM, handle_sigterm)
signal.signal(signal.SIGINT, handle_sigterm)


if __name__ == "__main__":
    logger.info("Starting AI Platform API Gateway...")
    logger.info(f"MAX Serve URL: {MAX_SERVE_URL}")
    logger.info(f"Qdrant: {QDRANT_HOST}:{QDRANT_PORT}")
    logger.info(f"Redis: {REDIS_HOST}:{REDIS_PORT}")
    logger.info(f"API Keys loaded: {len(API_KEYS)}")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=9000,
        log_level="info",
        access_log=True
    )
