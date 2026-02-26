#!/usr/bin/env python3
"""
OpenAI-compatible API server for MAX Serve with multi-model routing.
Supports Llama 3.3 8B (general), Qwen 2.5 Coder 7B (code), DeepSeek R1 7B (reasoning).
Exposes /v1/chat/completions, /v1/rag/ingest, and /health endpoints.
"""

import os
import time
import json
import uuid
import logging
import asyncio
from typing import List, Dict, Optional, Any
from datetime import datetime

import uvicorn
import signal
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import httpx

from agent_router import AgentRouter
from rag_service import RAGIngestionService
from memory_service import MemoryService
from graph_service import GraphService
from feedback_service import FeedbackService
from circuit_breaker import get_all_circuit_breaker_stats

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
AGENT_ROUTER_CONFIG = os.getenv("AGENT_ROUTER_CONFIG", "configs/agent-router.yaml")

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "documents")

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "neo4j_password")

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB = os.getenv("POSTGRES_DB", "ai_platform")
POSTGRES_USER = os.getenv("POSTGRES_USER", "ai_user")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "ai_password")

# Create FastAPI app
app = FastAPI(
    title="OpenAI-Compatible API for MAX Serve with Agent Router",
    description="Multi-model API with intelligent routing: Llama 3.3 8B (general), Qwen 2.5 Coder 7B (code), DeepSeek R1 7B (reasoning)",
    version="2.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request/Response Models
class ChatMessage(BaseModel):
    role: str = Field(..., description="Role of the message author (system, user, assistant)")
    content: str = Field(..., description="Content of the message")
    name: Optional[str] = Field(None, description="Optional name of the participant")


class ChatCompletionRequest(BaseModel):
    model: str = Field(default="llama-3.3-8b-instruct", description="Model to use")
    messages: List[ChatMessage] = Field(..., description="List of messages")
    temperature: Optional[float] = Field(0.7, ge=0.0, le=2.0, description="Sampling temperature")
    top_p: Optional[float] = Field(0.9, ge=0.0, le=1.0, description="Nucleus sampling parameter")
    max_tokens: Optional[int] = Field(2048, ge=1, description="Maximum tokens to generate")
    stream: Optional[bool] = Field(False, description="Whether to stream responses")
    n: Optional[int] = Field(1, ge=1, le=1, description="Number of completions (only 1 supported)")
    stop: Optional[List[str]] = Field(None, description="Stop sequences")
    presence_penalty: Optional[float] = Field(0.0, ge=-2.0, le=2.0)
    frequency_penalty: Optional[float] = Field(0.0, ge=-2.0, le=2.0)
    user: Optional[str] = Field(None, description="Unique user identifier")


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


class HealthResponse(BaseModel):
    status: str
    timestamp: str
    model: str
    max_serve_status: str


class RAGIngestRequest(BaseModel):
    text: str = Field(..., description="Text content to ingest")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Optional metadata for the document")


class RAGIngestBatchRequest(BaseModel):
    documents: List[Dict[str, Any]] = Field(..., description="List of documents to ingest")


class RAGIngestResponse(BaseModel):
    status: str
    document_id: str
    chunks_created: int
    points_stored: int
    point_ids: List[str]
    metadata: Dict[str, Any]


class RAGIngestBatchResponse(BaseModel):
    status: str
    documents_processed: int
    total_chunks: int
    total_points: int
    results: List[Dict[str, Any]]


class RAGSearchRequest(BaseModel):
    query: str = Field(..., description="Search query text")
    limit: int = Field(10, ge=1, le=100, description="Maximum number of results")
    filters: Optional[Dict[str, Any]] = Field(None, description="Optional metadata filters")


class RAGSearchResponse(BaseModel):
    results: List[Dict[str, Any]]
    query: str
    limit: int


class RAGStatsResponse(BaseModel):
    collection_info: Dict[str, Any]


class RAGQueryRequest(BaseModel):
    query: str = Field(..., description="Query text to search for relevant context")
    messages: Optional[List[ChatMessage]] = Field(None, description="Optional chat history messages")
    k: int = Field(5, ge=1, le=20, description="Number of top results to retrieve (top-k)")
    filters: Optional[Dict[str, Any]] = Field(None, description="Optional metadata filters")
    temperature: Optional[float] = Field(0.7, ge=0.0, le=2.0, description="Sampling temperature")
    top_p: Optional[float] = Field(0.9, ge=0.0, le=1.0, description="Nucleus sampling parameter")
    max_tokens: Optional[int] = Field(2048, ge=1, description="Maximum tokens to generate")
    include_context: Optional[bool] = Field(True, description="Whether to include retrieved context in response")


class RAGQueryResponse(BaseModel):
    id: str
    object: str = "rag.query.completion"
    created: int
    query: str
    context: Optional[List[Dict[str, Any]]] = Field(None, description="Retrieved context chunks")
    response: str = Field(..., description="Generated response augmented with context")
    usage: ChatCompletionUsage
    retrieval_stats: Dict[str, Any] = Field(..., description="Statistics about retrieval")


class RAGGraphSearchRequest(BaseModel):
    query: str = Field(..., description="Search query text")
    limit: int = Field(10, ge=1, le=100, description="Maximum number of vector search results")
    filters: Optional[Dict[str, Any]] = Field(None, description="Optional metadata filters")
    graph_depth: int = Field(1, ge=1, le=3, description="Maximum depth for graph traversal")
    graph_limit: int = Field(10, ge=1, le=50, description="Maximum number of graph neighbors per entity")
    include_entity_context: bool = Field(True, description="Include entity descriptions from graph")


class RAGGraphSearchResponse(BaseModel):
    query: str
    vector_results: List[Dict[str, Any]]
    graph_context: Optional[Dict[str, Any]]
    enriched: bool
    stats: Dict[str, Any]


class RAGGraphQueryRequest(BaseModel):
    query: str = Field(..., description="Query text to search for relevant context")
    messages: Optional[List[ChatMessage]] = Field(None, description="Optional chat history messages")
    k: int = Field(5, ge=1, le=20, description="Number of top results to retrieve (top-k)")
    filters: Optional[Dict[str, Any]] = Field(None, description="Optional metadata filters")
    graph_depth: int = Field(1, ge=1, le=3, description="Maximum depth for graph traversal")
    graph_limit: int = Field(10, ge=1, le=50, description="Maximum number of graph neighbors per entity")
    temperature: Optional[float] = Field(0.7, ge=0.0, le=2.0, description="Sampling temperature")
    top_p: Optional[float] = Field(0.9, ge=0.0, le=1.0, description="Nucleus sampling parameter")
    max_tokens: Optional[int] = Field(2048, ge=1, description="Maximum tokens to generate")
    include_context: Optional[bool] = Field(True, description="Whether to include retrieved context in response")


class RAGGraphQueryResponse(BaseModel):
    id: str
    object: str = "rag.graph.query.completion"
    created: int
    query: str
    vector_context: Optional[List[Dict[str, Any]]] = Field(None, description="Retrieved vector context chunks")
    graph_context: Optional[Dict[str, Any]] = Field(None, description="Knowledge graph context")
    graph_context_formatted: Optional[str] = Field(None, description="Formatted graph context for LLM")
    response: str = Field(..., description="Generated response augmented with vector and graph context")
    usage: ChatCompletionUsage
    retrieval_stats: Dict[str, Any] = Field(..., description="Statistics about retrieval")


class MemoryAddRequest(BaseModel):
    messages: List[Dict[str, str]] = Field(..., description="Conversation messages to store")
    user_id: Optional[str] = Field(None, description="Optional user identifier")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Optional metadata")


class MemoryAddResponse(BaseModel):
    status: str
    memory_id: str
    timestamp: str
    user_id: str
    facts_extracted: int


class MemorySearchRequest(BaseModel):
    query: str = Field(..., description="Search query text")
    user_id: Optional[str] = Field(None, description="Optional user ID to filter memories")
    limit: int = Field(10, ge=1, le=100, description="Maximum number of results")
    filters: Optional[Dict[str, Any]] = Field(None, description="Optional metadata filters")
    use_temporal_decay: bool = Field(True, description="Apply temporal decay to scores")


class MemorySearchResponse(BaseModel):
    query: str
    results: List[Dict[str, Any]]
    limit: int


class MemoryForgetResponse(BaseModel):
    status: str
    memory_id: str
    message: str


class MemoryStatsResponse(BaseModel):
    collection_name: str
    qdrant_points: int
    redis_memories: int
    vector_dimension: int
    distance_metric: str


class GraphProcessRequest(BaseModel):
    text: str = Field(..., description="Text to process for entity and relation extraction")
    document_id: Optional[str] = Field(None, description="Optional document identifier")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Optional metadata")


class GraphProcessResponse(BaseModel):
    status: str
    document_id: str
    entities_extracted: int
    entities_added: int
    relations_extracted: int
    relations_added: int
    relations_by_method: Dict[str, int]


class GraphQueryRequest(BaseModel):
    query: str = Field(..., description="Cypher query to execute")
    parameters: Optional[Dict[str, Any]] = Field(None, description="Query parameters")


class GraphQueryResponse(BaseModel):
    status: str
    results: List[Dict[str, Any]]
    count: int


class GraphNeighborsResponse(BaseModel):
    entity: str
    entity_type: Optional[str]
    neighbors_count: int
    neighbors: List[Dict[str, Any]]


class GraphSearchRequest(BaseModel):
    search_text: str = Field(..., description="Text to search for entities")
    entity_types: Optional[List[str]] = Field(None, description="Filter by entity types")
    limit: int = Field(20, ge=1, le=100, description="Maximum results")


class GraphSearchResponse(BaseModel):
    search_text: str
    results: List[Dict[str, Any]]
    count: int


class GraphStatsResponse(BaseModel):
    total_nodes: int
    total_relationships: int
    nodes_by_type: Dict[str, int]
    relationships_by_type: Dict[str, int]


class FeedbackRequest(BaseModel):
    query: str = Field(..., description="Original user query")
    response: str = Field(..., description="Model response")
    model: str = Field(..., description="Model identifier")
    rating: int = Field(..., description="Feedback rating: 1 (thumbs-up) or -1 (thumbs-down)")
    memory_used: int = Field(0, description="Memory used in bytes")
    tools_called: Optional[List[str]] = Field(None, description="List of tools/functions called")
    user_id: Optional[str] = Field(None, description="User identifier")
    session_id: Optional[str] = Field(None, description="Session identifier")
    intent: Optional[str] = Field(None, description="Detected intent (code, reasoning, general)")
    project: Optional[str] = Field(None, description="Project identifier")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class FeedbackResponse(BaseModel):
    status: str
    feedback_id: str
    id: int
    timestamp: str
    rating: int
    model: str


class FeedbackUpdateRequest(BaseModel):
    rating: Optional[int] = Field(None, description="Updated rating (1 or -1)")
    intent: Optional[str] = Field(None, description="Updated intent")
    project: Optional[str] = Field(None, description="Updated project")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata to merge")


class ModelAccuracyResponse(BaseModel):
    model: str
    intent: Optional[str]
    project: Optional[str]
    total_feedback: int
    positive_feedback: int
    negative_feedback: int
    accuracy_percentage: float
    last_updated: str


class FeedbackStatsResponse(BaseModel):
    total_feedback: int
    positive_count: int
    negative_count: int
    positive_percentage: float
    avg_memory_used: int
    unique_users: int
    unique_sessions: int
    days: int
    filters: Dict[str, Optional[str]]


class FinetuningExportRequest(BaseModel):
    output_path: str = Field(..., description="Output file path")
    start_date: Optional[str] = Field(None, description="Start date (ISO format)")
    end_date: Optional[str] = Field(None, description="End date (ISO format)")
    format: str = Field("jsonl", description="Export format (jsonl)")


class FinetuningExportResponse(BaseModel):
    status: str
    output_path: str
    total_samples: int
    positive_samples: int
    negative_samples: int
    total_weight: float
    start_date: Optional[str]
    end_date: Optional[str]


# Metrics storage
class MetricsStore:
    def __init__(self):
        self.request_count = 0
        self.total_latency = 0.0
        self.latencies = []
        self.errors = 0

    def record_request(self, latency: float, error: bool = False):
        self.request_count += 1
        if not error:
            self.total_latency += latency
            self.latencies.append(latency)
            # Keep only last 1000 latencies
            if len(self.latencies) > 1000:
                self.latencies = self.latencies[-1000:]
        else:
            self.errors += 1

    def get_stats(self) -> Dict[str, Any]:
        if not self.latencies:
            return {
                "request_count": self.request_count,
                "errors": self.errors,
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
            "avg_latency_ms": round(self.total_latency / len(self.latencies), 2),
            "p50_latency_ms": round(sorted_latencies[int(n * 0.50)], 2),
            "p95_latency_ms": round(sorted_latencies[int(n * 0.95)], 2),
            "p99_latency_ms": round(sorted_latencies[int(n * 0.99)], 2)
        }


metrics = MetricsStore()

# Initialize services (lazy loading)
agent_router = None
rag_service = None
memory_service = None
graph_service = None
feedback_service = None

# Graceful shutdown flag
shutdown_in_progress = False


def get_agent_router() -> AgentRouter:
    """Get or initialize Agent Router."""
    global agent_router
    if agent_router is None:
        logger.info("Initializing Agent Router...")
        agent_router = AgentRouter(config_path=AGENT_ROUTER_CONFIG)
        logger.info("Agent Router initialized")
    return agent_router


def get_rag_service() -> RAGIngestionService:
    """Get or initialize RAG service."""
    global rag_service
    if rag_service is None:
        logger.info("Initializing RAG Ingestion Service...")
        
        # Try to get graph service for enrichment
        try:
            graph_svc = get_graph_service()
            logger.info("RAG service will use graph enrichment")
        except Exception as e:
            logger.warning(f"Graph service not available for RAG: {e}")
            graph_svc = None
        
        rag_service = RAGIngestionService(
            qdrant_host=QDRANT_HOST,
            qdrant_port=QDRANT_PORT,
            collection_name=QDRANT_COLLECTION,
            chunk_size=1000,
            chunk_overlap=100,
            graph_service=graph_svc
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


def get_graph_service() -> GraphService:
    """Get or initialize Graph service."""
    global graph_service
    if graph_service is None:
        logger.info("Initializing Graph Service...")
        graph_service = GraphService(
            neo4j_uri=NEO4J_URI,
            neo4j_user=NEO4J_USER,
            neo4j_password=NEO4J_PASSWORD,
            embedding_model="sentence-transformers/all-MiniLM-L6-v2",
            spacy_model="en_core_web_sm"
        )
        logger.info("Graph Service initialized")
    return graph_service


def get_feedback_service() -> FeedbackService:
    """Get or initialize Feedback service."""
    global feedback_service
    if feedback_service is None:
        logger.info("Initializing Feedback Service...")
        feedback_service = FeedbackService(
            db_host=POSTGRES_HOST,
            db_port=POSTGRES_PORT,
            db_name=POSTGRES_DB,
            db_user=POSTGRES_USER,
            db_password=POSTGRES_PASSWORD
        )
        logger.info("Feedback Service initialized")
    return feedback_service


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


async def stream_chat_completion_response(
    completion_id: str,
    created: int,
    model: str,
    content: str,
    finish_reason: str = "stop"
):
    """
    Stream an OpenAI-compatible chat completion response over SSE.

    This yields an initial role chunk, a content chunk, and a final stop chunk,
    followed by the standard [DONE] marker.
    """

    role_chunk = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{
            "index": 0,
            "delta": {"role": "assistant"},
            "finish_reason": None
        }]
    }
    yield f"data: {json.dumps(role_chunk)}\n\n"

    if content:
        content_chunk = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{
                "index": 0,
                "delta": {"content": content},
                "finish_reason": None
            }]
        }
        yield f"data: {json.dumps(content_chunk)}\n\n"

    final_chunk = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{
            "index": 0,
            "delta": {},
            "finish_reason": finish_reason
        }]
    }
    yield f"data: {json.dumps(final_chunk)}\n\n"
    await asyncio.sleep(0)
    yield "data: [DONE]\n\n"


async def generate_with_router(
    messages: List[ChatMessage],
    prompt: str,
    params: Dict[str, Any]
) -> tuple[str, int, int, Dict[str, Any]]:
    """Generate response using AgentRouter with automatic model selection and fallback."""
    
    router = get_agent_router()
    
    messages_dict = [{"role": msg.role, "content": msg.content} for msg in messages]
    
    result = await router.generate(
        messages=messages_dict,
        prompt=prompt,
        max_tokens=params.get("max_tokens"),
        temperature=params.get("temperature"),
        top_p=params.get("top_p"),
        stop=params.get("stop")
    )
    
    if not result['success']:
        error_msg = result.get('error', 'Generation failed')
        logger.error(f"Router generation failed: {error_msg}")
        raise HTTPException(status_code=503, detail=f"Generation error: {error_msg}")
    
    generated_text = result['text'].strip()
    metadata = result.get('metadata', {})
    
    prompt_tokens = estimate_tokens(prompt)
    completion_tokens = estimate_tokens(generated_text)
    
    return generated_text, prompt_tokens, completion_tokens, metadata


@app.get("/")
async def root():
    """Root endpoint."""
    router = get_agent_router()
    return {
        "message": "OpenAI-Compatible API for MAX Serve with Multi-Model Routing",
        "version": "2.0.0",
        "models": router.list_models(),
        "endpoints": {
            "chat": "/v1/chat/completions",
            "models": "/v1/models",
            "health": "/health",
            "metrics": "/metrics",
            "router_info": "/router/info",
            "rag_ingest": "/v1/rag/ingest",
            "rag_ingest_batch": "/v1/rag/ingest/batch",
            "rag_search": "/v1/rag/search",
            "rag_query": "/v1/rag/query",
            "rag_delete": "/v1/rag/documents/{document_id}",
            "rag_stats": "/v1/rag/stats",
            "memory_add": "POST /memory/add",
            "memory_search": "GET /memory/search",
            "memory_forget": "DELETE /memory/forget/{memory_id}",
            "memory_stats": "GET /memory/stats",
            "graph_process": "POST /graph/process",
            "graph_query": "POST /graph/query",
            "graph_neighbors": "GET /graph/neighbors/{entity}",
            "graph_search": "POST /graph/search",
            "graph_stats": "GET /graph/stats",
            "feedback_add": "POST /v1/feedback",
            "feedback_get": "GET /v1/feedback/{feedback_id}",
            "feedback_update": "PUT /v1/feedback/{feedback_id}",
            "feedback_delete": "DELETE /v1/feedback/{feedback_id}",
            "feedback_accuracy": "GET /v1/feedback/accuracy",
            "feedback_stats": "GET /v1/feedback/stats",
            "feedback_export": "POST /v1/feedback/export/finetuning"
        },
        "prometheus_metrics": "http://localhost:8001/metrics"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint with multi-model status."""
    
    router = get_agent_router()
    models_info = router.list_models()
    
    all_healthy = all(model['health_status'] for model in models_info.values())
    
    return {
        "status": "healthy" if all_healthy else "degraded",
        "timestamp": datetime.utcnow().isoformat(),
        "models": {
            model_id: {
                "name": info['name'],
                "status": "healthy" if info['health_status'] else "unhealthy",
                "endpoint": info['endpoint']
            }
            for model_id, info in models_info.items()
        }
    }


@app.get("/metrics")
async def get_metrics():
    """Get performance metrics."""
    return {
        "metrics": metrics.get_stats(),
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/circuit-breakers")
async def get_circuit_breakers():
    """Get circuit breaker statistics."""
    return {
        "circuit_breakers": get_all_circuit_breaker_stats(),
        "timestamp": datetime.utcnow().isoformat()
    }


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest, raw_request: Request):
    """
    OpenAI-compatible chat completions endpoint with intelligent routing.
    Automatically selects the best model based on intent classification.
    """
    start_time = time.time()
    
    try:
        # Validate request
        if not request.messages:
            raise HTTPException(status_code=400, detail="Messages list cannot be empty")
        
        if request.n != 1:
            raise HTTPException(status_code=400, detail="Only n=1 is currently supported")
        
        # Format prompt
        prompt = format_chat_prompt(request.messages)
        logger.info(f"Processing chat completion request with {len(request.messages)} messages")
        
        # Call Agent Router
        params = {
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "top_p": request.top_p,
            "stop": request.stop or ["<|eot_id|>", "<|end_of_text|>"],
        }
        
        generated_text, prompt_tokens, completion_tokens, routing_metadata = await generate_with_router(
            messages=request.messages,
            prompt=prompt,
            params=params
        )
        
        # Calculate latency
        latency_ms = (time.time() - start_time) * 1000
        metrics.record_request(latency_ms)
        
        completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
        created = int(time.time())
        response_model = routing_metadata.get('model_name', request.model)

        if request.stream:
            logger.info("Streaming response requested; returning SSE-compatible output")
            return StreamingResponse(
                stream_chat_completion_response(
                    completion_id=completion_id,
                    created=created,
                    model=response_model,
                    content=generated_text,
                    finish_reason="stop"
                ),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive"
                }
            )

        # Build response with routing metadata
        response_data = {
            "id": completion_id,
            "object": "chat.completion",
            "created": created,
            "model": response_model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": generated_text
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens
            },
            "x-routing-metadata": routing_metadata
        }
        
        logger.info(
            f"Request completed in {latency_ms:.2f}ms "
            f"[model={routing_metadata.get('model_id')}, "
            f"intent={routing_metadata.get('intent')}, "
            f"fallback={routing_metadata.get('fallback_used')}]"
        )
        
        return response_data
        
    except HTTPException:
        metrics.record_request((time.time() - start_time) * 1000, error=True)
        raise
    except Exception as e:
        metrics.record_request((time.time() - start_time) * 1000, error=True)
        logger.error(f"Unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/v1/models")
async def list_models():
    """List available models (OpenAI-compatible)."""
    router = get_agent_router()
    models_info = router.list_models()
    
    return {
        "object": "list",
        "data": [
            {
                "id": info['name'],
                "object": "model",
                "created": int(time.time()),
                "owned_by": "modular",
                "permission": [],
                "root": info['name'],
                "parent": None,
                "description": info['description'],
                "capabilities": info['capabilities'],
                "max_tokens": info['max_tokens'],
                "health_status": info['health_status']
            }
            for model_id, info in models_info.items()
        ]
    }


@app.get("/router/info")
async def router_info():
    """Get router configuration and status."""
    router = get_agent_router()
    models_info = router.list_models()
    
    return {
        "models": models_info,
        "routing_strategy": {
            "code": router.routing_config.primary_model.get("code"),
            "reasoning": router.routing_config.primary_model.get("reasoning"),
            "general": router.routing_config.primary_model.get("general")
        },
        "fallback_chains": router.routing_config.fallback_chains,
        "health_check": {
            "enabled": router.health_check_enabled,
            "interval_seconds": router.health_check_interval
        },
        "prometheus_metrics": "http://localhost:8001/metrics"
    }


@app.post("/v1/rag/ingest", response_model=RAGIngestResponse)
async def rag_ingest(request: RAGIngestRequest):
    """
    Ingest a document into the RAG system.
    
    The document will be:
    1. Chunked into 1000-character segments with 100-character overlap
    2. Tagged with provided metadata
    3. Embedded using Nomic Embed v1.5
    4. Stored in Qdrant vector database
    """
    try:
        service = get_rag_service()
        result = service.ingest_document(
            text=request.text,
            metadata=request.metadata
        )
        logger.info(f"Successfully ingested document: {result['document_id']}")
        return RAGIngestResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error ingesting document: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ingestion error: {str(e)}")


@app.post("/v1/rag/ingest/batch", response_model=RAGIngestBatchResponse)
async def rag_ingest_batch(request: RAGIngestBatchRequest):
    """
    Ingest multiple documents into the RAG system in batch.
    
    Each document should have:
    - text: Document content
    - metadata: Optional metadata dictionary
    """
    try:
        service = get_rag_service()
        result = service.ingest_documents_batch(documents=request.documents)
        logger.info(f"Successfully ingested {result['documents_processed']} documents")
        return RAGIngestBatchResponse(**result)
    except Exception as e:
        logger.error(f"Error in batch ingestion: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch ingestion error: {str(e)}")


@app.post("/v1/rag/search", response_model=RAGSearchResponse)
async def rag_search(request: RAGSearchRequest):
    """
    Search for relevant documents in the RAG system.
    
    Args:
        query: Search query text
        limit: Maximum number of results (1-100)
        filters: Optional metadata filters
    
    Returns:
        List of relevant document chunks with similarity scores
    """
    try:
        service = get_rag_service()
        results = service.search_documents(
            query=request.query,
            limit=request.limit,
            filters=request.filters
        )
        logger.info(f"Search completed: {len(results)} results for query: {request.query[:50]}...")
        return RAGSearchResponse(
            results=results,
            query=request.query,
            limit=request.limit
        )
    except Exception as e:
        logger.error(f"Error searching documents: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Search error: {str(e)}")


@app.delete("/v1/rag/documents/{document_id}")
async def rag_delete_document(document_id: str):
    """
    Delete a document and all its chunks from the RAG system.
    
    Args:
        document_id: ID of the document to delete
    """
    try:
        service = get_rag_service()
        service.delete_document(document_id)
        logger.info(f"Successfully deleted document: {document_id}")
        return {
            "status": "success",
            "document_id": document_id,
            "message": "Document deleted successfully"
        }
    except Exception as e:
        logger.error(f"Error deleting document: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Delete error: {str(e)}")


@app.get("/v1/rag/stats", response_model=RAGStatsResponse)
async def rag_stats():
    """
    Get RAG system statistics.
    
    Returns collection information including:
    - Collection name
    - Number of vectors
    - Number of points
    - Status
    """
    try:
        service = get_rag_service()
        stats = service.get_stats()
        return RAGStatsResponse(collection_info=stats)
    except Exception as e:
        logger.error(f"Error getting RAG stats: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Stats error: {str(e)}")


@app.post("/v1/rag/query", response_model=RAGQueryResponse)
async def rag_query(request: RAGQueryRequest):
    """
    RAG query endpoint: retrieves relevant context and generates augmented response.
    
    This endpoint:
    1. Performs cosine similarity search using the query embedding
    2. Retrieves top-k most relevant document chunks (default k=5)
    3. Optionally filters results by metadata
    4. Constructs an augmented prompt with retrieved context
    5. Generates a response via MAX Serve using the augmented prompt
    
    Args:
        query: User query text
        messages: Optional chat history for multi-turn conversations
        k: Number of top results to retrieve (1-20, default 5)
        filters: Optional metadata filters for retrieval
        temperature: Sampling temperature (0.0-2.0, default 0.7)
        top_p: Nucleus sampling parameter (0.0-1.0, default 0.9)
        max_tokens: Maximum tokens to generate (default 2048)
        include_context: Include retrieved context in response (default True)
    
    Returns:
        RAGQueryResponse with generated text, retrieved context, and usage stats
    """
    start_time = time.time()
    
    try:
        service = get_rag_service()
        
        logger.info(f"RAG query with k={request.k}: {request.query[:100]}...")
        
        retrieval_start = time.time()
        results = service.search_documents(
            query=request.query,
            limit=request.k,
            filters=request.filters
        )
        retrieval_time_ms = (time.time() - retrieval_start) * 1000
        
        logger.info(f"Retrieved {len(results)} context chunks in {retrieval_time_ms:.2f}ms")
        
        if not results:
            logger.warning("No context found for query, generating response without RAG")
            context_text = ""
            retrieval_stats = {
                "chunks_retrieved": 0,
                "retrieval_time_ms": round(retrieval_time_ms, 2),
                "top_score": None,
                "avg_score": None
            }
        else:
            context_chunks = []
            for idx, result in enumerate(results):
                chunk_text = f"[Context {idx + 1}]\n{result['text']}\n"
                context_chunks.append(chunk_text)
            
            context_text = "\n".join(context_chunks)
            
            scores = [r['score'] for r in results]
            retrieval_stats = {
                "chunks_retrieved": len(results),
                "retrieval_time_ms": round(retrieval_time_ms, 2),
                "top_score": round(scores[0], 4) if scores else None,
                "avg_score": round(sum(scores) / len(scores), 4) if scores else None,
                "min_score": round(min(scores), 4) if scores else None
            }
        
        messages_list = []
        
        if context_text:
            system_message = ChatMessage(
                role="system",
                content=(
                    "You are a helpful assistant. Use the following context to answer the user's question. "
                    "If the context doesn't contain relevant information, say so and provide the best answer you can.\n\n"
                    f"Context:\n{context_text}"
                )
            )
            messages_list.append(system_message)
        else:
            system_message = ChatMessage(
                role="system",
                content="You are a helpful assistant. Answer the user's question to the best of your ability."
            )
            messages_list.append(system_message)
        
        if request.messages:
            messages_list.extend(request.messages)
        
        messages_list.append(ChatMessage(role="user", content=request.query))
        
        prompt = format_chat_prompt(messages_list)
        
        params = {
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "top_p": request.top_p,
            "stop": ["<|eot_id|>", "<|end_of_text|>"],
        }
        
        generation_start = time.time()
        generated_text, prompt_tokens, completion_tokens, routing_metadata = await generate_with_router(
            messages=messages_list,
            prompt=prompt,
            params=params
        )
        generation_time_ms = (time.time() - generation_start) * 1000
        
        retrieval_stats["generation_time_ms"] = round(generation_time_ms, 2)
        retrieval_stats["total_time_ms"] = round((time.time() - start_time) * 1000, 2)
        
        logger.info(
            f"RAG query completed: {len(results)} chunks retrieved, "
            f"response generated in {generation_time_ms:.2f}ms"
        )
        
        context_data = None
        if request.include_context and results:
            context_data = [
                {
                    "text": r["text"],
                    "score": round(r["score"], 4),
                    "metadata": r.get("metadata"),
                    "id": r.get("id")
                }
                for r in results
            ]
        
        response = RAGQueryResponse(
            id=f"rag-{uuid.uuid4().hex[:24]}",
            created=int(time.time()),
            query=request.query,
            context=context_data,
            response=generated_text,
            usage=ChatCompletionUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens
            ),
            retrieval_stats=retrieval_stats
        )
        
        metrics.record_request((time.time() - start_time) * 1000)
        
        return response
        
    except HTTPException:
        metrics.record_request((time.time() - start_time) * 1000, error=True)
        raise
    except Exception as e:
        metrics.record_request((time.time() - start_time) * 1000, error=True)
        logger.error(f"Error in RAG query: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"RAG query error: {str(e)}")


@app.post("/v1/rag/search/graph-enriched", response_model=RAGGraphSearchResponse)
async def rag_graph_search(request: RAGGraphSearchRequest):
    """
    Graph-enriched RAG search: combines vector similarity with knowledge graph context.
    
    This endpoint:
    1. Performs vector similarity search to find relevant document chunks
    2. Extracts entities from the query and top search results
    3. Queries the Neo4j knowledge graph for related entities and relationships
    4. Enriches vector search results with graph context
    
    Args:
        query: Search query text
        limit: Maximum number of vector search results (1-100)
        filters: Optional metadata filters for vector search
        graph_depth: Maximum depth for graph traversal (1-3)
        graph_limit: Maximum number of graph neighbors per entity (1-50)
        include_entity_context: Include entity descriptions from graph
    
    Returns:
        Vector search results enriched with knowledge graph context
    """
    try:
        service = get_rag_service()
        
        if not service.graph_service:
            raise HTTPException(
                status_code=503,
                detail="Graph service not available. Graph-enriched search requires Neo4j."
            )
        
        logger.info(f"Graph-enriched search with depth={request.graph_depth}: {request.query[:100]}...")
        
        enriched_results = service.search_with_graph_enrichment(
            query=request.query,
            limit=request.limit,
            filters=request.filters,
            graph_depth=request.graph_depth,
            graph_limit=request.graph_limit,
            include_entity_context=request.include_entity_context
        )
        
        logger.info(
            f"Graph-enriched search completed: {enriched_results['stats']['vector_results_count']} "
            f"vector results, {enriched_results['stats']['entities_in_graph']} entities, "
            f"{enriched_results['stats']['relationships_found']} relationships"
        )
        
        return RAGGraphSearchResponse(**enriched_results)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in graph-enriched search: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Graph-enriched search error: {str(e)}")


@app.post("/v1/rag/query/graph-enriched", response_model=RAGGraphQueryResponse)
async def rag_graph_query(request: RAGGraphQueryRequest):
    """
    Graph-enriched RAG query: generates responses using both vector and graph context.
    
    This endpoint:
    1. Performs vector similarity search to find relevant document chunks
    2. Extracts entities from query and results, queries knowledge graph
    3. Enriches context with entity relationships from Neo4j
    4. Constructs an augmented prompt with both vector and graph context
    5. Generates response via MAX Serve using the enriched context
    
    Args:
        query: User query text
        messages: Optional chat history for multi-turn conversations
        k: Number of top vector results to retrieve (1-20)
        filters: Optional metadata filters for vector search
        graph_depth: Maximum depth for graph traversal (1-3)
        graph_limit: Maximum number of graph neighbors per entity (1-50)
        temperature: Sampling temperature (0.0-2.0)
        top_p: Nucleus sampling parameter (0.0-1.0)
        max_tokens: Maximum tokens to generate
        include_context: Include retrieved context in response
    
    Returns:
        Generated response augmented with vector and graph context
    """
    start_time = time.time()
    
    try:
        service = get_rag_service()
        
        if not service.graph_service:
            raise HTTPException(
                status_code=503,
                detail="Graph service not available. Graph-enriched query requires Neo4j."
            )
        
        logger.info(f"Graph-enriched RAG query with k={request.k}: {request.query[:100]}...")
        
        retrieval_start = time.time()
        enriched_results = service.search_with_graph_enrichment(
            query=request.query,
            limit=request.k,
            filters=request.filters,
            graph_depth=request.graph_depth,
            graph_limit=request.graph_limit
        )
        retrieval_time_ms = (time.time() - retrieval_start) * 1000
        
        vector_results = enriched_results['vector_results']
        graph_context = enriched_results.get('graph_context')
        
        logger.info(
            f"Retrieved {len(vector_results)} vector chunks and "
            f"{enriched_results['stats']['relationships_found']} graph relationships "
            f"in {retrieval_time_ms:.2f}ms"
        )
        
        if not vector_results:
            logger.warning("No context found for query, generating response without RAG")
            context_text = ""
            retrieval_stats = {
                "chunks_retrieved": 0,
                "retrieval_time_ms": round(retrieval_time_ms, 2),
                "entities_in_graph": 0,
                "relationships_found": 0,
                "top_score": None,
                "avg_score": None
            }
        else:
            context_chunks = []
            for idx, result in enumerate(vector_results):
                chunk_text = f"[Context {idx + 1}]\n{result['text']}\n"
                context_chunks.append(chunk_text)
            
            context_text = "\n".join(context_chunks)
            
            scores = [r['score'] for r in vector_results]
            retrieval_stats = {
                "chunks_retrieved": len(vector_results),
                "retrieval_time_ms": round(retrieval_time_ms, 2),
                "entities_in_graph": enriched_results['stats']['entities_in_graph'],
                "relationships_found": enriched_results['stats']['relationships_found'],
                "top_score": round(scores[0], 4) if scores else None,
                "avg_score": round(sum(scores) / len(scores), 4) if scores else None,
                "min_score": round(min(scores), 4) if scores else None
            }
        
        messages_list = []
        
        graph_context_formatted = ""
        if graph_context and enriched_results['enriched']:
            graph_context_formatted = service.format_graph_context_for_llm(graph_context)
        
        if context_text or graph_context_formatted:
            system_content = (
                "You are a helpful assistant. Use the following context to answer the user's question. "
                "If the context doesn't contain relevant information, say so and provide the best answer you can.\n\n"
            )
            
            if context_text:
                system_content += f"Document Context:\n{context_text}\n\n"
            
            if graph_context_formatted:
                system_content += f"{graph_context_formatted}\n"
            
            system_message = ChatMessage(role="system", content=system_content)
            messages_list.append(system_message)
        else:
            system_message = ChatMessage(
                role="system",
                content="You are a helpful assistant. Answer the user's question to the best of your ability."
            )
            messages_list.append(system_message)
        
        if request.messages:
            messages_list.extend(request.messages)
        
        messages_list.append(ChatMessage(role="user", content=request.query))
        
        prompt = format_chat_prompt(messages_list)
        
        params = {
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "top_p": request.top_p,
            "stop": ["<|eot_id|>", "<|end_of_text|>"],
        }
        
        generation_start = time.time()
        generated_text, prompt_tokens, completion_tokens, routing_metadata = await generate_with_router(
            messages=messages_list,
            prompt=prompt,
            params=params
        )
        generation_time_ms = (time.time() - generation_start) * 1000
        
        retrieval_stats["generation_time_ms"] = round(generation_time_ms, 2)
        retrieval_stats["total_time_ms"] = round((time.time() - start_time) * 1000, 2)
        
        logger.info(
            f"Graph-enriched RAG query completed: {len(vector_results)} chunks, "
            f"{retrieval_stats['relationships_found']} relationships, "
            f"response generated in {generation_time_ms:.2f}ms"
        )
        
        vector_context_data = None
        if request.include_context and vector_results:
            vector_context_data = [
                {
                    "text": r["text"],
                    "score": round(r["score"], 4),
                    "metadata": r.get("metadata"),
                    "id": r.get("id"),
                    "graph_entities": r.get("graph_entities", [])
                }
                for r in vector_results
            ]
        
        response = RAGGraphQueryResponse(
            id=f"rag-graph-{uuid.uuid4().hex[:24]}",
            created=int(time.time()),
            query=request.query,
            vector_context=vector_context_data,
            graph_context=graph_context if request.include_context else None,
            graph_context_formatted=graph_context_formatted if request.include_context else None,
            response=generated_text,
            usage=ChatCompletionUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens
            ),
            retrieval_stats=retrieval_stats
        )
        
        metrics.record_request((time.time() - start_time) * 1000)
        
        return response
        
    except HTTPException:
        metrics.record_request((time.time() - start_time) * 1000, error=True)
        raise
    except Exception as e:
        metrics.record_request((time.time() - start_time) * 1000, error=True)
        logger.error(f"Error in graph-enriched RAG query: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Graph-enriched RAG query error: {str(e)}")


@app.post("/memory/add", response_model=MemoryAddResponse)
async def memory_add(request: MemoryAddRequest):
    """
    Add memory from conversation messages with automatic fact extraction.
    
    This endpoint:
    1. Accepts conversation messages in {"role": "...", "content": "..."} format
    2. Uses Mem0 to automatically extract facts from the conversation
    3. Stores memories in Qdrant with embeddings for similarity search
    4. Stores metadata in Redis for fast key-value access
    5. Supports user-specific memories via user_id
    
    Args:
        messages: List of conversation messages
        user_id: Optional user identifier for personalized memories
        metadata: Optional metadata to store with the memory
    
    Returns:
        Memory ID, timestamp, and number of facts extracted
    """
    try:
        service = get_memory_service()
        result = service.add_memory(
            messages=request.messages,
            user_id=request.user_id,
            metadata=request.metadata
        )
        logger.info(f"Memory added: {result['memory_id']} ({result['facts_extracted']} facts)")
        return MemoryAddResponse(**result)
    except Exception as e:
        logger.error(f"Error adding memory: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Memory add error: {str(e)}")


@app.post("/memory/search", response_model=MemorySearchResponse)
async def memory_search(request: MemorySearchRequest):
    """
    Search memories with cosine similarity + temporal decay scoring.
    
    This endpoint:
    1. Embeds the search query using the same model as stored memories
    2. Performs cosine similarity search in Qdrant
    3. Applies temporal decay to favor recent memories (configurable)
    4. Combines scores: 70% cosine similarity + 30% temporal score
    5. Optionally filters by user_id and metadata
    
    Temporal decay formula:
        temporal_score = exp(-decay_factor * age_in_days)
    
    Args:
        query: Search query text
        user_id: Optional user ID to filter memories
        limit: Maximum number of results (1-100)
        filters: Optional metadata filters
        use_temporal_decay: Apply temporal decay (default: True)
    
    Returns:
        List of memories with combined scores, cosine scores, and temporal scores
    """
    try:
        service = get_memory_service()
        results = service.search_memory(
            query=request.query,
            user_id=request.user_id,
            limit=request.limit,
            filters=request.filters,
            use_temporal_decay=request.use_temporal_decay
        )
        logger.info(f"Memory search: {len(results)} results for query: {request.query[:50]}...")
        return MemorySearchResponse(
            query=request.query,
            results=results,
            limit=request.limit
        )
    except Exception as e:
        logger.error(f"Error searching memory: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Memory search error: {str(e)}")


@app.delete("/memory/forget/{memory_id}", response_model=MemoryForgetResponse)
async def memory_forget(memory_id: str):
    """
    Delete a memory by ID.
    
    This endpoint:
    1. Removes the memory from Qdrant vector store
    2. Removes the memory metadata from Redis
    3. Permanently deletes all associated data
    
    Args:
        memory_id: Memory ID to delete
    
    Returns:
        Deletion status
    """
    try:
        service = get_memory_service()
        result = service.forget_memory(memory_id)
        logger.info(f"Memory deleted: {memory_id}")
        return MemoryForgetResponse(**result)
    except Exception as e:
        logger.error(f"Error deleting memory: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Memory delete error: {str(e)}")


@app.get("/memory/stats", response_model=MemoryStatsResponse)
async def memory_stats():
    """
    Get memory system statistics.
    
    Returns:
        - Collection name
        - Number of vectors in Qdrant
        - Number of memories in Redis
        - Vector dimension
        - Distance metric used
    """
    try:
        service = get_memory_service()
        stats = service.get_memory_stats()
        return MemoryStatsResponse(**stats)
    except Exception as e:
        logger.error(f"Error getting memory stats: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Memory stats error: {str(e)}")


@app.post("/graph/process", response_model=GraphProcessResponse)
async def graph_process(request: GraphProcessRequest):
    """
    Process text to extract entities and relations, add to knowledge graph.
    
    This endpoint:
    1. Extracts named entities using SpaCy NER pipeline
    2. Identifies relations through:
       - Co-occurrence analysis (entities appearing in same context)
       - Explicit pattern matching (e.g., "X works on Y")
    3. Adds entities as nodes to Neo4j graph
    4. Creates relationships between entities
    5. Links to source document if provided
    
    Entity Types: Project, Person, Concept, Document, Problem, Lesson
    Relation Types: WORKS_ON, RELATES_TO, CAUSED_BY, SOLVED_BY, LEARNED_FROM
    
    Args:
        text: Input text for processing
        document_id: Optional document identifier
        metadata: Optional metadata (e.g., title, author, date)
    
    Returns:
        Processing statistics including entities and relations extracted/added
    """
    try:
        service = get_graph_service()
        result = service.process_document(
            text=request.text,
            document_id=request.document_id,
            metadata=request.metadata
        )
        logger.info(f"Processed document: {result['document_id']}")
        return GraphProcessResponse(**result)
    except Exception as e:
        logger.error(f"Error processing document for graph: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Graph processing error: {str(e)}")


@app.post("/graph/query", response_model=GraphQueryResponse)
async def graph_query(request: GraphQueryRequest):
    """
    Execute Cypher query on knowledge graph.
    
    Supports full Cypher query language for complex graph traversals.
    
    Example queries:
    
    1. Find all people working on a project:
       MATCH (p:Person)-[:WORKS_ON]->(proj:Project {name: "Project X"})
       RETURN p.name
    
    2. Find problems and their solutions:
       MATCH (prob:Problem)-[:SOLVED_BY]->(sol)
       RETURN prob.name, sol.name, labels(sol)[0] as solution_type
    
    3. Find lessons learned from projects:
       MATCH (lesson:Lesson)-[:LEARNED_FROM]->(proj:Project)
       RETURN lesson.name, proj.name
    
    4. Find related concepts:
       MATCH (c1:Concept)-[:RELATES_TO*1..2]-(c2:Concept)
       WHERE c1.name = "Machine Learning"
       RETURN DISTINCT c2.name
    
    Args:
        query: Cypher query string
        parameters: Optional query parameters (use $param in query)
    
    Returns:
        Query results as list of records
    """
    try:
        service = get_graph_service()
        results = service.query_graph(
            query=request.query,
            parameters=request.parameters
        )
        logger.info(f"Graph query executed: {len(results)} results")
        return GraphQueryResponse(
            status="success",
            results=results,
            count=len(results)
        )
    except Exception as e:
        logger.error(f"Error executing graph query: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Graph query error: {str(e)}")


@app.get("/graph/neighbors/{entity}", response_model=GraphNeighborsResponse)
async def graph_neighbors(
    entity: str,
    entity_type: Optional[str] = None,
    relation_types: Optional[str] = None,
    max_depth: int = 1,
    limit: int = 50
):
    """
    Get neighbors of an entity in the knowledge graph.
    
    Returns entities connected to the specified entity within the given depth.
    
    Args:
        entity: Name of the entity
        entity_type: Optional entity type filter (Project, Person, Concept, etc.)
        relation_types: Optional comma-separated relation types (e.g., "WORKS_ON,RELATES_TO")
        max_depth: Maximum traversal depth (default: 1)
        limit: Maximum number of neighbors to return (default: 50)
    
    Returns:
        List of neighbors with their types, connecting relations, and distances
    
    Example:
        GET /graph/neighbors/Alice?entity_type=Person&relation_types=WORKS_ON&max_depth=2
    """
    try:
        service = get_graph_service()
        
        # Parse relation types if provided
        rel_types_list = None
        if relation_types:
            rel_types_list = [rt.strip() for rt in relation_types.split(",")]
        
        result = service.get_neighbors(
            entity_name=entity,
            entity_type=entity_type,
            relation_types=rel_types_list,
            max_depth=max_depth,
            limit=limit
        )
        
        logger.info(f"Found {result['neighbors_count']} neighbors for {entity}")
        return GraphNeighborsResponse(**result)
    except Exception as e:
        logger.error(f"Error getting neighbors: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Graph neighbors error: {str(e)}")


@app.post("/graph/search", response_model=GraphSearchResponse)
async def graph_search(request: GraphSearchRequest):
    """
    Search for entities in the knowledge graph using full-text search.
    
    Searches entity names and descriptions across all node types.
    
    Args:
        search_text: Text to search for
        entity_types: Optional list of entity types to filter by
        limit: Maximum number of results (1-100)
    
    Returns:
        List of matching entities with relevance scores
    
    Example:
        POST /graph/search
        {
            "search_text": "machine learning",
            "entity_types": ["Concept", "Project"],
            "limit": 10
        }
    """
    try:
        service = get_graph_service()
        results = service.search_entities(
            search_text=request.search_text,
            entity_types=request.entity_types,
            limit=request.limit
        )
        logger.info(f"Graph search: {len(results)} results for '{request.search_text}'")
        return GraphSearchResponse(
            search_text=request.search_text,
            results=results,
            count=len(results)
        )
    except Exception as e:
        logger.error(f"Error searching graph: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Graph search error: {str(e)}")


@app.get("/graph/stats", response_model=GraphStatsResponse)
async def graph_stats():
    """
    Get knowledge graph statistics.
    
    Returns:
        - Total number of nodes
        - Total number of relationships
        - Breakdown by node type (Project, Person, Concept, etc.)
        - Breakdown by relationship type (WORKS_ON, RELATES_TO, etc.)
    """
    try:
        service = get_graph_service()
        stats = service.get_graph_stats()
        logger.info(f"Graph stats: {stats['total_nodes']} nodes, {stats['total_relationships']} relationships")
        return GraphStatsResponse(**stats)
    except Exception as e:
        logger.error(f"Error getting graph stats: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Graph stats error: {str(e)}")


@app.post("/v1/feedback", response_model=FeedbackResponse)
async def add_feedback(request: FeedbackRequest):
    """
    Submit feedback for a model response (thumbs-up/down).
    
    This endpoint:
    1. Stores feedback in PostgreSQL with full context
    2. Tracks query, response, model, rating, memory usage, and tools called
    3. Auto-updates accuracy metrics by model, intent, and project
    4. Enables fine-tuning dataset export with weighted samples
    
    Ratings:
    - 1: Thumbs-up (positive feedback, 2.0x weight in fine-tuning)
    - -1: Thumbs-down (negative feedback, 0.5x weight in fine-tuning)
    
    Args:
        query: Original user query
        response: Model's response
        model: Model identifier (e.g., "llama-3.3-8b-instruct")
        rating: Feedback rating (1 or -1)
        memory_used: Memory usage in bytes (optional)
        tools_called: List of tools/functions used (optional)
        user_id: User identifier (optional)
        session_id: Session identifier (optional)
        intent: Detected intent like "code", "reasoning", "general" (optional)
        project: Project identifier (optional)
        metadata: Additional metadata (optional)
    
    Returns:
        Feedback ID, timestamp, and status
    """
    try:
        service = get_feedback_service()
        result = service.add_feedback(
            query=request.query,
            response=request.response,
            model=request.model,
            rating=request.rating,
            memory_used=request.memory_used,
            tools_called=request.tools_called,
            user_id=request.user_id,
            session_id=request.session_id,
            intent=request.intent,
            project=request.project,
            metadata=request.metadata
        )
        logger.info(f"Feedback added: {result['feedback_id']} [rating={request.rating}]")
        return FeedbackResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error adding feedback: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Feedback error: {str(e)}")


@app.get("/v1/feedback/{feedback_id}")
async def get_feedback(feedback_id: str):
    """
    Retrieve feedback by ID.
    
    Args:
        feedback_id: Feedback identifier
    
    Returns:
        Complete feedback record with all metadata
    """
    try:
        service = get_feedback_service()
        result = service.get_feedback(feedback_id)
        
        if result is None:
            raise HTTPException(status_code=404, detail=f"Feedback not found: {feedback_id}")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving feedback: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Feedback retrieval error: {str(e)}")


@app.put("/v1/feedback/{feedback_id}")
async def update_feedback(feedback_id: str, request: FeedbackUpdateRequest):
    """
    Update existing feedback.
    
    Args:
        feedback_id: Feedback identifier
        rating: Updated rating (1 or -1)
        intent: Updated intent
        project: Updated project
        metadata: Additional metadata to merge
    
    Returns:
        Update status
    """
    try:
        service = get_feedback_service()
        result = service.update_feedback(
            feedback_id=feedback_id,
            rating=request.rating,
            intent=request.intent,
            project=request.project,
            metadata=request.metadata
        )
        logger.info(f"Feedback updated: {feedback_id}")
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating feedback: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Feedback update error: {str(e)}")


@app.delete("/v1/feedback/{feedback_id}")
async def delete_feedback(feedback_id: str):
    """
    Delete feedback by ID.
    
    Args:
        feedback_id: Feedback identifier
    
    Returns:
        Deletion status
    """
    try:
        service = get_feedback_service()
        result = service.delete_feedback(feedback_id)
        logger.info(f"Feedback deleted: {feedback_id}")
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error deleting feedback: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Feedback deletion error: {str(e)}")


@app.get("/v1/feedback/accuracy", response_model=List[ModelAccuracyResponse])
async def get_model_accuracy(
    model: Optional[str] = None,
    intent: Optional[str] = None,
    project: Optional[str] = None
):
    """
    Get per-model accuracy metrics by intent and project.
    
    This endpoint returns accuracy percentages calculated from feedback ratings:
    - Accuracy = (positive_feedback / total_feedback) * 100
    - Metrics are aggregated by model, intent, and project combinations
    - Auto-updated via PostgreSQL triggers on feedback insertion
    
    Args:
        model: Filter by specific model (optional)
        intent: Filter by intent (e.g., "code", "reasoning", "general") (optional)
        project: Filter by project (optional)
    
    Returns:
        List of accuracy metrics with breakdown by model/intent/project
    
    Example:
        GET /v1/feedback/accuracy?model=llama-3.3-8b-instruct&intent=code
    """
    try:
        service = get_feedback_service()
        results = service.get_model_accuracy(
            model=model,
            intent=intent,
            project=project
        )
        
        formatted_results = []
        for r in results:
            formatted_results.append(
                ModelAccuracyResponse(
                    model=r["model"],
                    intent=r["intent"],
                    project=r["project"],
                    total_feedback=r["total_feedback"],
                    positive_feedback=r["positive_feedback"],
                    negative_feedback=r["negative_feedback"],
                    accuracy_percentage=float(r["accuracy_percentage"] or 0),
                    last_updated=r["last_updated"].isoformat() if r["last_updated"] else None
                )
            )
        
        logger.info(f"Accuracy metrics retrieved: {len(formatted_results)} entries")
        return formatted_results
    except Exception as e:
        logger.error(f"Error retrieving accuracy metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Accuracy metrics error: {str(e)}")


@app.get("/v1/feedback/stats", response_model=FeedbackStatsResponse)
async def get_feedback_stats(
    model: Optional[str] = None,
    intent: Optional[str] = None,
    project: Optional[str] = None,
    days: int = 7
):
    """
    Get feedback statistics for a time period.
    
    Args:
        model: Filter by model (optional)
        intent: Filter by intent (optional)
        project: Filter by project (optional)
        days: Number of days to look back (default: 7)
    
    Returns:
        Aggregated statistics including:
        - Total feedback count
        - Positive/negative counts and percentages
        - Average memory usage
        - Unique users and sessions
    
    Example:
        GET /v1/feedback/stats?model=qwen-2.5-coder-7b&intent=code&days=30
    """
    try:
        service = get_feedback_service()
        stats = service.get_feedback_stats(
            model=model,
            intent=intent,
            project=project,
            days=days
        )
        logger.info(f"Feedback stats retrieved for {days} days")
        return FeedbackStatsResponse(**stats)
    except Exception as e:
        logger.error(f"Error retrieving feedback stats: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Feedback stats error: {str(e)}")


@app.post("/v1/feedback/export/finetuning", response_model=FinetuningExportResponse)
async def export_finetuning_dataset(request: FinetuningExportRequest):
    """
    Export weekly fine-tuning dataset with weighted samples.
    
    This endpoint:
    1. Extracts feedback from specified time range (default: last 7 days)
    2. Applies weights based on feedback rating:
       - Positive feedback (thumbs-up): 2.0x weight
       - Negative feedback (thumbs-down): 0.5x weight
    3. Exports to JSONL format suitable for fine-tuning
    
    Output format (per line):
    {
        "messages": [
            {"role": "user", "content": "..."},
            {"role": "assistant", "content": "..."}
        ],
        "weight": 2.0,
        "metadata": {
            "model": "...",
            "rating": 1,
            "timestamp": "...",
            "intent": "...",
            "project": "..."
        }
    }
    
    Args:
        output_path: Path to output JSONL file
        start_date: Start date in ISO format (optional, default: 7 days ago)
        end_date: End date in ISO format (optional, default: now)
        format: Export format (default: "jsonl")
    
    Returns:
        Export statistics including sample counts and weights
    
    Example:
        POST /v1/feedback/export/finetuning
        {
            "output_path": "/tmp/finetuning_data.jsonl",
            "start_date": "2025-01-01T00:00:00Z",
            "end_date": "2025-01-08T00:00:00Z"
        }
    """
    try:
        service = get_feedback_service()
        
        start_date = None
        end_date = None
        
        if request.start_date:
            start_date = datetime.fromisoformat(request.start_date.replace('Z', '+00:00'))
        
        if request.end_date:
            end_date = datetime.fromisoformat(request.end_date.replace('Z', '+00:00'))
        
        result = service.export_finetuning_dataset(
            output_path=request.output_path,
            start_date=start_date,
            end_date=end_date,
            format=request.format
        )
        
        logger.info(
            f"Fine-tuning dataset exported: {result['total_samples']} samples, "
            f"total weight: {result['total_weight']}"
        )
        return FinetuningExportResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error exporting fine-tuning dataset: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Export error: {str(e)}")


@app.on_event("startup")
async def startup_event():
    """Initialize services on startup."""
    logger.info("Starting up API server...")
    router = get_agent_router()
    await router.start_health_checks()
    logger.info("Agent Router health checks started")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown with graceful termination."""
    global shutdown_in_progress
    shutdown_in_progress = True
    
    logger.info("Shutting down API server gracefully...")
    
    # Wait for in-flight requests to complete (up to 30 seconds)
    logger.info("Waiting for in-flight requests to complete...")
    await asyncio.sleep(5)  # Give pending requests time to finish
    
    # Stop health checks
    if agent_router:
        await agent_router.stop_health_checks()
        logger.info("Agent Router health checks stopped")
    
    # Close database connections
    if graph_service:
        graph_service.close()
        logger.info("Graph Service closed")
    
    if feedback_service:
        feedback_service.close()
        logger.info("Feedback Service closed")
    
    logger.info("API server shutdown complete")


def handle_sigterm(signum, frame):
    """Handle SIGTERM for graceful shutdown."""
    logger.info("Received SIGTERM signal, initiating graceful shutdown...")
    raise KeyboardInterrupt


# Register signal handlers for graceful shutdown
signal.signal(signal.SIGTERM, handle_sigterm)
signal.signal(signal.SIGINT, handle_sigterm)


if __name__ == "__main__":
    logger.info("Starting OpenAI-compatible API server with Agent Router...")
    logger.info(f"Agent Router Config: {AGENT_ROUTER_CONFIG}")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
        access_log=True
    )
