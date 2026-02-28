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
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import httpx

from agent_router import AgentRouter, Intent
from document_ingestion_service import DocumentIngestionService
from rag_service import RAGIngestionService
from memory_service import MemoryService
from memory_scoring_config import load_memory_scoring_config
from graph_service import GraphService
from feedback_service import FeedbackService
from circuit_breaker import get_all_circuit_breaker_stats
from internal_mcp_client import InternalMCPGatewayClient

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

RAG_EMBEDDING_MODEL = os.getenv("RAG_EMBEDDING_MODEL", "nomic-ai/nomic-embed-text-v1.5")
RAG_EMBEDDING_PROVIDER = os.getenv("RAG_EMBEDDING_PROVIDER", "local")
RAG_EMBEDDING_SERVICE_URL = os.getenv("RAG_EMBEDDING_SERVICE_URL", "http://embedding-service:8003")
MCP_GATEWAY_URL = os.getenv("MCP_GATEWAY_URL", "http://mcpjungle:9100")
MCP_GATEWAY_API_KEY = os.getenv("MCP_GATEWAY_API_KEY", "")

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


class ChatRAGOptions(BaseModel):
    enabled: bool = Field(False, description="Enable retrieval-augmented generation for this request")
    query: Optional[str] = Field(
        None,
        description="Optional retrieval query override (defaults to latest user message)"
    )
    k: int = Field(5, ge=1, le=20, description="Number of chunks to retrieve")
    filters: Optional[Dict[str, Any]] = Field(None, description="Optional metadata filters")
    min_score: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Optional minimum similarity score threshold"
    )
    include_context: bool = Field(
        False,
        description="Include retrieved context chunks in non-streaming response"
    )


class ChatMemoryOptions(BaseModel):
    enabled: bool = Field(False, description="Enable long-term memory for this request")
    top_k: int = Field(5, ge=1, le=20, description="Number of memories to retrieve")
    min_score: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Optional minimum combined memory score threshold"
    )
    include_context: bool = Field(
        False,
        description="Include retrieved memories in non-streaming response"
    )
    auto_store: bool = Field(
        True,
        description="Store the latest user/assistant exchange as memory"
    )
    use_temporal_decay: bool = Field(
        True,
        description="Apply temporal decay when ranking retrieved memories"
    )


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
    rag: Optional[ChatRAGOptions] = Field(None, description="Optional per-request RAG options")
    memory: Optional[ChatMemoryOptions] = Field(
        None,
        description="Optional per-request long-term memory options"
    )


class UnifiedChatRequest(BaseModel):
    """Unified chat request with opt-in controls for transparent orchestration."""

    model: str = Field(default="llama-3.3-8b-instruct", description="Model to use")
    messages: List[ChatMessage] = Field(..., description="List of messages")
    temperature: Optional[float] = Field(0.7, ge=0.0, le=2.0, description="Sampling temperature")
    top_p: Optional[float] = Field(0.9, ge=0.0, le=1.0, description="Nucleus sampling parameter")
    max_tokens: Optional[int] = Field(2048, ge=1, description="Maximum tokens to generate")
    stream: Optional[bool] = Field(False, description="Whether to stream responses")
    user_id: Optional[str] = Field(None, description="User identifier for personalized memory")
    user: Optional[str] = Field(None, description="OpenAI-compatible user identifier")
    n: Optional[int] = Field(1, ge=1, le=1, description="Number of completions (only 1 supported)")
    stop: Optional[List[str]] = Field(None, description="Stop sequences")
    presence_penalty: Optional[float] = Field(0.0, ge=-2.0, le=2.0)
    frequency_penalty: Optional[float] = Field(0.0, ge=-2.0, le=2.0)
    use_rag: bool = Field(True, description="Enable retrieval-augmented generation")
    use_memory: bool = Field(True, description="Enable long-term memory retrieval")
    store_memory: bool = Field(True, description="Store generated exchange in memory")
    use_temporal_decay: bool = Field(True, description="Apply temporal decay for memory scoring")
    rag_k: int = Field(5, ge=1, le=20, description="Number of chunks to retrieve from RAG")
    rag_filters: Optional[Dict[str, Any]] = Field(None, description="Optional metadata filters for RAG")
    rag_min_score: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Optional minimum score threshold for RAG chunks"
    )
    memory_top_k: int = Field(5, ge=1, le=20, description="Number of memories to retrieve")
    memory_min_score: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Optional minimum combined score threshold for memories"
    )
    include_context: bool = Field(
        False,
        description="Include retrieved RAG and memory context in non-streaming responses"
    )




class MCPGatewayRequest(BaseModel):
    action: str = Field(..., description="MCP action: list_tools/call_tool/list_resources/read_resource")
    server_id: str = Field(..., description="MCP server identifier")
    tool_name: Optional[str] = Field(None, description="Required for call_tool")
    uri: Optional[str] = Field(None, description="Required for read_resource")
    arguments: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Optional tool arguments")


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


class DocumentIngestTextRequest(BaseModel):
    text: str = Field(..., description="Raw text content to ingest")
    source: str = Field(..., description="Source identifier (e.g. slack, github, upload)")
    project: str = Field(..., description="Project identifier")
    created_at: Optional[str] = Field(None, description="Optional document creation timestamp")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Optional additional metadata")


class DocumentIngestResponse(BaseModel):
    document_id: str
    metadata: Dict[str, Any]
    chunks: List[Dict[str, Any]]
    chunks_created: int


class RAGSearchRequest(BaseModel):
    query: str = Field(..., description="Search query text")
    limit: int = Field(10, ge=1, le=100, description="Maximum number of results")
    filters: Optional[Dict[str, Any]] = Field(None, description="Optional metadata filters")


class RAGSearchResponse(BaseModel):
    results: List[Dict[str, Any]]
    query: str
    limit: int


class RAGSemanticSearchRequest(BaseModel):
    query: str = Field(..., description="Search query text")
    top_k: int = Field(10, ge=1, le=100, description="Top-k nearest neighbors to return")
    filters: Optional[Dict[str, Any]] = Field(None, description="Optional metadata filters")
    collection_name: Optional[str] = Field(None, description="Optional Qdrant collection override")


class RAGSemanticSearchResponse(BaseModel):
    results: List[Dict[str, Any]]
    query: str
    top_k: int
    collection_name: Optional[str] = None


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
    include_graph_context: Optional[bool] = Field(
        True,
        description="Whether to enrich retrieval with Neo4j graph context when available",
    )
    graph_limit: int = Field(
        5,
        ge=1,
        le=20,
        description="Maximum number of graph neighbors to retrieve per extracted entity",
    )


class RAGQueryResponse(BaseModel):
    id: str
    object: str = "rag.query.completion"
    created: int
    query: str
    context: Optional[List[Dict[str, Any]]] = Field(None, description="Retrieved context chunks")
    graph_context: Optional[Dict[str, Any]] = Field(None, description="Optional Neo4j graph context")
    graph_context_formatted: Optional[str] = Field(
        None,
        description="Formatted graph relationships injected into the LLM prompt",
    )
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
    min_query_chars: int = Field(10, ge=1, description="Minimum query length")
    min_response_chars: int = Field(20, ge=1, description="Minimum response length")
    deduplicate: bool = Field(True, description="Remove duplicate query/response pairs")


class FinetuningExportResponse(BaseModel):
    status: str
    output_path: str
    total_samples: int
    positive_samples: int
    negative_samples: int
    total_weight: float
    filtered_out_samples: int
    start_date: Optional[str]
    end_date: Optional[str]


class MCPToolProxyRequest(BaseModel):
    server_id: str = Field(..., description="Target MCP server ID")
    tool_name: str = Field(..., description="MCP tool name")
    arguments: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Tool call arguments")
    context: Optional[str] = Field(None, description="Optional caller context for logging")


class MCPToolProxyResponse(BaseModel):
    ok: bool
    tool_name: str
    latency_ms: float
    status_code: int
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


# Metrics storage
class MetricsStore:
    def __init__(self):
        self.request_count = 0
        self.total_latency = 0.0
        self.latencies = []
        self.errors = 0
        self.memory_requests = 0
        self.memory_hits = 0
        self.memory_context_items_total = 0
        self.memory_scores = []

    def record_request(self, latency: float, error: bool = False):
        self.tokens_generated = 0
        self.model_stats: Dict[str, Dict[str, Any]] = {}

    def record_request(
        self,
        latency: float,
        error: bool = False,
        model: Optional[str] = None,
        completion_tokens: int = 0
    ):
        self.request_count += 1
        if model:
            model_bucket = self.model_stats.setdefault(
                model,
                {
                    "request_count": 0,
                    "errors": 0,
                    "total_latency": 0.0,
                    "latencies": [],
                    "tokens_generated": 0
                }
            )
            model_bucket["request_count"] += 1

        if not error:
            self.total_latency += latency
            self.latencies.append(latency)
            self.tokens_generated += completion_tokens

            if model:
                model_bucket["total_latency"] += latency
                model_bucket["latencies"].append(latency)
                model_bucket["tokens_generated"] += completion_tokens

            # Keep only last 1000 latencies
            if len(self.latencies) > 1000:
                self.latencies = self.latencies[-1000:]
            if model and len(model_bucket["latencies"]) > 1000:
                model_bucket["latencies"] = model_bucket["latencies"][-1000:]
        else:
            self.errors += 1
            if model:
                model_bucket["errors"] += 1

    @staticmethod
    def _rate(errors: int, total: int) -> float:
        return round((errors / total) * 100, 2) if total else 0.0

    @staticmethod
    def _tokens_per_second(tokens: int, total_latency_ms: float) -> float:
        return round(tokens / (total_latency_ms / 1000), 2) if total_latency_ms > 0 else 0.0

    def record_memory_telemetry(
        self,
        memory_metadata: Optional[Dict[str, Any]],
        memory_context: Optional[List[Dict[str, Any]]] = None
    ):
        """Record request-level memory telemetry for dashboarding."""
        if not memory_metadata or not memory_metadata.get("enabled"):
            return

        self.memory_requests += 1

        memories_retrieved = int(memory_metadata.get("memories_retrieved", 0) or 0)
        if memories_retrieved > 0:
            self.memory_hits += 1

        context_size = len(memory_context or [])
        self.memory_context_items_total += context_size

        avg_score = memory_metadata.get("avg_score")
        top_score = memory_metadata.get("top_score")
        if isinstance(avg_score, (int, float)):
            self.memory_scores.append(float(avg_score))
        if isinstance(top_score, (int, float)):
            self.memory_scores.append(float(top_score))

        if len(self.memory_scores) > 2000:
            self.memory_scores = self.memory_scores[-2000:]

    def get_stats(self) -> Dict[str, Any]:
        memory_telemetry = {
            "memory_requests": self.memory_requests,
            "memory_hits": self.memory_hits,
            "memory_hit_rate": round(self.memory_hits / self.memory_requests, 4)
            if self.memory_requests
            else 0.0,
            "avg_memory_context_size": round(
                self.memory_context_items_total / self.memory_requests,
                4
            ) if self.memory_requests else 0.0,
            "score_distribution": {
                "0.0-0.2": 0,
                "0.2-0.4": 0,
                "0.4-0.6": 0,
                "0.6-0.8": 0,
                "0.8-1.0": 0
            },
            "avg_memory_score": 0.0,
            "p50_memory_score": 0.0,
            "p95_memory_score": 0.0
        }

        if self.memory_scores:
            sorted_scores = sorted(self.memory_scores)
            score_count = len(sorted_scores)
            memory_telemetry["avg_memory_score"] = round(sum(sorted_scores) / score_count, 4)
            memory_telemetry["p50_memory_score"] = round(sorted_scores[int(score_count * 0.50)], 4)
            memory_telemetry["p95_memory_score"] = round(sorted_scores[int(score_count * 0.95)], 4)

            distribution = memory_telemetry["score_distribution"]
            for score in sorted_scores:
                clamped_score = max(0.0, min(1.0, score))
                if clamped_score < 0.2:
                    distribution["0.0-0.2"] += 1
                elif clamped_score < 0.4:
                    distribution["0.2-0.4"] += 1
                elif clamped_score < 0.6:
                    distribution["0.4-0.6"] += 1
                elif clamped_score < 0.8:
                    distribution["0.6-0.8"] += 1
                else:
                    distribution["0.8-1.0"] += 1

        if not self.latencies:
            return {
                "request_count": self.request_count,
                "errors": self.errors,
                "error_rate_percent": self._rate(self.errors, self.request_count),
                "avg_latency_ms": 0,
                "p50_latency_ms": 0,
                "p95_latency_ms": 0,
                "p99_latency_ms": 0,
                "memory_telemetry": memory_telemetry
                "tokens_generated": self.tokens_generated,
                "tokens_per_second": self._tokens_per_second(self.tokens_generated, self.total_latency)
            }
        
        sorted_latencies = sorted(self.latencies)
        n = len(sorted_latencies)
        
        return {
            "request_count": self.request_count,
            "errors": self.errors,
            "error_rate_percent": self._rate(self.errors, self.request_count),
            "avg_latency_ms": round(self.total_latency / len(self.latencies), 2),
            "p50_latency_ms": round(sorted_latencies[int(n * 0.50)], 2),
            "p95_latency_ms": round(sorted_latencies[int(n * 0.95)], 2),
            "p99_latency_ms": round(sorted_latencies[int(n * 0.99)], 2),
            "memory_telemetry": memory_telemetry
            "tokens_generated": self.tokens_generated,
            "tokens_per_second": self._tokens_per_second(self.tokens_generated, self.total_latency)
        }

    def get_model_stats(self) -> Dict[str, Any]:
        """Return per-model latency, error-rate, and throughput metrics."""
        model_metrics: Dict[str, Any] = {}
        for model_name, data in self.model_stats.items():
            sorted_latencies = sorted(data["latencies"])
            n = len(sorted_latencies)
            model_metrics[model_name] = {
                "request_count": data["request_count"],
                "errors": data["errors"],
                "error_rate_percent": self._rate(data["errors"], data["request_count"]),
                "avg_latency_ms": round(data["total_latency"] / n, 2) if n else 0,
                "p50_latency_ms": round(sorted_latencies[int(n * 0.50)], 2) if n else 0,
                "p95_latency_ms": round(sorted_latencies[int(n * 0.95)], 2) if n else 0,
                "p99_latency_ms": round(sorted_latencies[int(n * 0.99)], 2) if n else 0,
                "tokens_generated": data["tokens_generated"],
                "tokens_per_second": self._tokens_per_second(data["tokens_generated"], data["total_latency"])
            }
        return model_metrics


metrics = MetricsStore()

# Initialize services (lazy loading)
agent_router = None
rag_service = None
memory_service = None
graph_service = None
feedback_service = None
document_ingestion_service = None
mcp_gateway_client = None

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
            embedding_model=RAG_EMBEDDING_MODEL,
            embedding_provider=RAG_EMBEDDING_PROVIDER,
            embedding_service_url=RAG_EMBEDDING_SERVICE_URL,
            graph_service=graph_svc
        )
        logger.info("RAG Ingestion Service initialized")
    return rag_service


def get_document_ingestion_service() -> DocumentIngestionService:
    """Get or initialize document ingestion service."""
    global document_ingestion_service
    if document_ingestion_service is None:
        logger.info("Initializing Document Ingestion Service...")
        document_ingestion_service = DocumentIngestionService(
            chunk_size=1000,
            chunk_overlap=100
        )
        logger.info("Document Ingestion Service initialized")
    return document_ingestion_service


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


def get_mcp_gateway_client() -> InternalMCPGatewayClient:
    """Get or initialize internal MCP gateway client."""
    global mcp_gateway_client
    if mcp_gateway_client is None:
        logger.info("Initializing internal MCP gateway client...")
        mcp_gateway_client = InternalMCPGatewayClient.from_env()
        logger.info("Internal MCP gateway client initialized")
    return mcp_gateway_client


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
        preferred_model=params.get("preferred_model"),
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
            "chat_unified": "/v1/chat",
            "models": "/v1/models",
            "health": "/health",
            "metrics": "/metrics",
            "router_info": "/router/info",
            "rag_ingest": "/v1/rag/ingest",
            "rag_ingest_batch": "/v1/rag/ingest/batch",
            "rag_search": "/v1/rag/search",
            "rag_query": "/v1/rag/query",
            "rag_query_api": "/v1/rag/queryAPI",
            "rag_delete": "/v1/rag/documents/{document_id}",
            "rag_stats": "/v1/rag/stats",
            "memory_add": "POST /memory/add",
            "memory_search": "POST|GET /memory/search",
            "memory_forget": "DELETE /memory/forget/{memory_id} or /memory/forget?memory_id=...",
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
            "feedback_export": "POST /v1/feedback/export/finetuning",
            "mcp_tool_proxy": "POST /internal/mcp/tools/call"
        },
        "prometheus_metrics": "http://localhost:8001/metrics"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint with multi-model status."""
    
    router = get_agent_router()
    models_info = router.list_models()

    has_models = bool(models_info)
    all_healthy = has_models and all(model['health_status'] for model in models_info.values())

    if not has_models:
        overall_status = "unhealthy"
    else:
        overall_status = "healthy" if all_healthy else "degraded"

    qdrant_status = "unhealthy"
    qdrant_error = None
    qdrant_url = f"http://{QDRANT_HOST}:{QDRANT_PORT}/healthz"
    qdrant_probe_urls = [
        qdrant_url,
        f"http://{QDRANT_HOST}:{QDRANT_PORT}/health"
    ]

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            for probe_url in qdrant_probe_urls:
                try:
                    qdrant_response = await client.get(probe_url)
                    qdrant_response.raise_for_status()
                    qdrant_status = "healthy"
                    qdrant_url = probe_url
                    break
                except Exception:
                    continue

        if qdrant_status != "healthy":
            raise RuntimeError(
                f"Qdrant health probe failed for endpoints: {', '.join(qdrant_probe_urls)}"
            )
    except Exception as exc:
        qdrant_error = str(exc)
        overall_status = "degraded" if has_models else "unhealthy"
    
    payload = {
        "status": overall_status,
        "timestamp": datetime.utcnow().isoformat(),
        "models": {
            model_id: {
                "name": info['name'],
                "status": "healthy" if info['health_status'] else "unhealthy",
                "endpoint": info['endpoint']
            }
            for model_id, info in models_info.items()
        },
        "summary": {
            "total_models": len(models_info),
            "healthy_models": sum(1 for info in models_info.values() if info['health_status'])
        },
        "dependencies": {
            "qdrant": {
                "status": qdrant_status,
                "endpoint": qdrant_url,
                "error": qdrant_error
            }
        }
    }

    status_code = 200 if all_healthy and qdrant_status == "healthy" else 503
    return JSONResponse(content=payload, status_code=status_code)


@app.post("/v1/mcp")
async def proxy_mcp_gateway(request: MCPGatewayRequest):
    """Proxy MCP calls through the MCPJungle gateway service."""
    headers = {"content-type": "application/json"}
    if MCP_GATEWAY_API_KEY:
        headers["authorization"] = f"Bearer {MCP_GATEWAY_API_KEY}"

    payload = request.model_dump(exclude_none=True)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{MCP_GATEWAY_URL}/mcp",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"MCP gateway unreachable: {exc}")


@app.get("/metrics")
async def get_metrics():
    """Get performance metrics."""
    return {
        "metrics": metrics.get_stats(),
        "per_model_metrics": metrics.get_model_stats(),
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/circuit-breakers")
async def get_circuit_breakers():
    """Get circuit breaker statistics."""
    return {
        "circuit_breakers": get_all_circuit_breaker_stats(),
        "timestamp": datetime.utcnow().isoformat()
    }


@app.post("/internal/mcp/tools/call", response_model=MCPToolProxyResponse)
async def internal_mcp_tool_call(request: MCPToolProxyRequest):
    """Route internal tool calls to MCP gateway /mcp endpoint with structured result."""
    client = get_mcp_gateway_client()
    result = await client.call_tool(
        server_id=request.server_id,
        tool_name=request.tool_name,
        arguments=request.arguments or {},
        context=request.context or "api.internal",
    )

    payload = result.to_dict()
    if not result.ok:
        return JSONResponse(status_code=result.status_code, content=payload)
    return payload


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
        
        messages_for_generation = list(request.messages)
        rag_context_data = None
        rag_metadata = None
        memory_context_data = None
        memory_metadata = None

        if request.memory and request.memory.enabled:
            latest_user_message = next(
                (msg.content for msg in reversed(request.messages) if msg.role == "user"),
                None
            )

            if latest_user_message:
                try:
                    service = get_memory_service()
                    memory_results = service.search_memory(
                        query=latest_user_message,
                        user_id=request.user,
                        limit=request.memory.top_k,
                        use_temporal_decay=request.memory.use_temporal_decay
                    )

                    if request.memory.min_score is not None:
                        memory_results = [
                            result
                            for result in memory_results
                            if result.get("score", 0.0) >= request.memory.min_score
                        ]

                    if memory_results:
                        memory_chunks = [
                            (
                                f"- {result.get('text', '')} "
                                f"(score={result.get('score', 0.0):.4f})"
                            )
                            for result in memory_results
                        ]
                        memory_system_message = ChatMessage(
                            role="system",
                            content=(
                                "Use the following remembered user facts and preferences when "
                                "they are relevant. Do not invent facts that are not listed.\n\n"
                                "Remembered context:\n" + "\n".join(memory_chunks)
                            )
                        )
                        messages_for_generation = [memory_system_message, *messages_for_generation]

                    memory_scores = [result.get("score", 0.0) for result in memory_results]
                    memory_metadata = {
                        "enabled": True,
                        "query": latest_user_message,
                        "top_k": request.memory.top_k,
                        "min_score": request.memory.min_score,
                        "use_temporal_decay": request.memory.use_temporal_decay,
                        "memories_retrieved": len(memory_results),
                        "top_score": round(max(memory_scores), 4) if memory_scores else None,
                        "avg_score": (
                            round(sum(memory_scores) / len(memory_scores), 4)
                            if memory_scores
                            else None
                        )
                    }

                    if request.memory.include_context:
                        memory_context_data = memory_results
                except Exception as exc:
                    logger.warning("Memory retrieval failed: %s", exc)
            else:
                logger.info("Memory enabled but no user message was found for retrieval query")

        if request.rag and request.rag.enabled:
            service = get_rag_service()
            latest_user_message = next(
                (msg.content for msg in reversed(request.messages) if msg.role == "user"),
                None
            )
            retrieval_query = request.rag.query or latest_user_message

            if not retrieval_query:
                raise HTTPException(
                    status_code=400,
                    detail="RAG requires at least one user message or rag.query"
                )

            retrieval_start = time.time()
            rag_results = service.search_documents(
                query=retrieval_query,
                limit=request.rag.k,
                filters=request.rag.filters
            )
            retrieval_time_ms = (time.time() - retrieval_start) * 1000

            if request.rag.min_score is not None:
                rag_results = [r for r in rag_results if r.get("score", 0.0) >= request.rag.min_score]

            if rag_results:
                context_chunks = [f"[Context {i + 1}]\n{r['text']}" for i, r in enumerate(rag_results)]
                rag_system_message = ChatMessage(
                    role="system",
                    content=(
                        "Use the provided context from the user's documents when relevant. "
                        "If the context does not answer the question, say what is missing and provide "
                        "the best available answer.\n\n"
                        "Context:\n" + "\n\n".join(context_chunks)
                    )
                )
                messages_for_generation = [rag_system_message, *messages_for_generation]

            rag_scores = [r.get("score", 0.0) for r in rag_results]
            rag_metadata = {
                "enabled": True,
                "query": retrieval_query,
                "k": request.rag.k,
                "filters": request.rag.filters,
                "min_score": request.rag.min_score,
                "chunks_retrieved": len(rag_results),
                "retrieval_time_ms": round(retrieval_time_ms, 2),
                "top_score": round(max(rag_scores), 4) if rag_scores else None,
                "avg_score": round(sum(rag_scores) / len(rag_scores), 4) if rag_scores else None
            }

            if request.rag.include_context:
                rag_context_data = [
                    {
                        "id": r.get("id"),
                        "score": round(r.get("score", 0.0), 4),
                        "text": r.get("text"),
                        "metadata": r.get("metadata")
                    }
                    for r in rag_results
                ]

        # Format prompt
        prompt = format_chat_prompt(messages_for_generation)
        logger.info(f"Processing chat completion request with {len(request.messages)} messages")
        
        # Call Agent Router
        params = {
            "preferred_model": request.model,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "top_p": request.top_p,
            "stop": request.stop or ["<|eot_id|>", "<|end_of_text|>"],
        }
        
        generated_text, prompt_tokens, completion_tokens, routing_metadata = await generate_with_router(
            messages=messages_for_generation,
            prompt=prompt,
            params=params
        )
        
        completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
        created = int(time.time())
        response_model = routing_metadata.get('model_name', request.model)

        # Calculate latency
        latency_ms = (time.time() - start_time) * 1000
        metrics.record_request(
            latency_ms,
            model=response_model,
            completion_tokens=completion_tokens
        )

        if request.memory and request.memory.enabled and request.memory.auto_store:
            try:
                memory_service_instance = get_memory_service()
                latest_user_message = next(
                    (msg.content for msg in reversed(request.messages) if msg.role == "user"),
                    None
                )
                if latest_user_message:
                    memory_messages = [
                        {"role": "user", "content": latest_user_message},
                        {"role": "assistant", "content": generated_text}
                    ]
                    store_result = memory_service_instance.add_memory(
                        messages=memory_messages,
                        user_id=request.user,
                        metadata={
                            "source": "chat.completions",
                            "model": response_model
                        }
                    )
                    if memory_metadata is None:
                        memory_metadata = {"enabled": True}
                    memory_metadata["memory_stored"] = True
                    memory_metadata["stored_memory_id"] = store_result.get("memory_id")
                else:
                    logger.info("No user message found, skipping automatic memory storage")
            except Exception as exc:
                logger.warning("Automatic memory storage failed: %s", exc)
                if memory_metadata is None:
                    memory_metadata = {"enabled": True}
                memory_metadata["memory_stored"] = False
                memory_metadata["storage_error"] = str(exc)

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

        if rag_metadata:
            response_data["x-rag-metadata"] = rag_metadata
            if rag_context_data is not None:
                response_data["rag_context"] = rag_context_data

        if memory_metadata:
            response_data["x-memory-metadata"] = memory_metadata
            if memory_context_data is not None:
                response_data["memory_context"] = memory_context_data

        metrics.record_memory_telemetry(memory_metadata, memory_context_data)

        logger.info(
            f"Request completed in {latency_ms:.2f}ms "
            f"[model={routing_metadata.get('model_id')}, "
            f"intent={routing_metadata.get('intent')}, "
            f"fallback={routing_metadata.get('fallback_used')}]"
        )
        
        return response_data
        
    except HTTPException:
        metrics.record_request((time.time() - start_time) * 1000, error=True, model=request.model)
        raise
    except Exception as e:
        metrics.record_request((time.time() - start_time) * 1000, error=True, model=request.model)
        logger.error(f"Unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/chat")
async def unified_chat(request: UnifiedChatRequest, raw_request: Request):
    """
    Unified chat endpoint that transparently orchestrates memory, RAG, and completion.

    This endpoint keeps client payloads simple while enabling both memory retrieval
    and document retrieval by default.
    """
    resolved_user = request.user_id or request.user

    completion_request = ChatCompletionRequest(
        model=request.model,
        messages=request.messages,
        temperature=request.temperature,
        top_p=request.top_p,
        max_tokens=request.max_tokens,
        stream=request.stream,
        n=request.n,
        stop=request.stop,
        presence_penalty=request.presence_penalty,
        frequency_penalty=request.frequency_penalty,
        user=resolved_user,
        rag=ChatRAGOptions(
            enabled=request.use_rag,
            k=request.rag_k,
            filters=request.rag_filters,
            min_score=request.rag_min_score,
            include_context=request.include_context
        ) if request.use_rag else None,
        memory=ChatMemoryOptions(
            enabled=request.use_memory,
            top_k=request.memory_top_k,
            min_score=request.memory_min_score,
            include_context=request.include_context,
            auto_store=request.store_memory,
            use_temporal_decay=request.use_temporal_decay
        ) if request.use_memory else None
    )
    response = await chat_completions(completion_request, raw_request)
    if isinstance(response, dict):
        routing_metadata = response.get("x-routing-metadata", {})
        logger.info(
            "Unified chat intent classification: intent=%s model=%s fallback=%s",
            routing_metadata.get("intent"),
            routing_metadata.get("model_id"),
            routing_metadata.get("fallback_used"),
        )
    return response


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
        "routing_plans": {
            "code": router.get_routing_plan(Intent.CODE),
            "reasoning": router.get_routing_plan(Intent.REASONING),
            "general": router.get_routing_plan(Intent.GENERAL)
        },
        "fallback_chains": router.routing_config.fallback_chains,
        "health_check": {
            "enabled": router.health_check_enabled,
            "interval_seconds": router.health_check_interval
        },
        "prometheus_metrics": "http://localhost:8001/metrics"
    }


@app.post("/v1/documents/ingest/text", response_model=DocumentIngestResponse)
async def ingest_document_text(request: DocumentIngestTextRequest):
    """Ingest raw text and return UTF-8 normalized overlapping chunks."""
    try:
        service = get_document_ingestion_service()
        result = service.ingest_text(
            text=request.text,
            source=request.source,
            project=request.project,
            created_at=request.created_at,
            metadata=request.metadata
        )
        return DocumentIngestResponse(
            document_id=result["document_id"],
            metadata=result["metadata"],
            chunks=result["chunks"],
            chunks_created=result["chunks_created"]
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error ingesting text document: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Document ingestion error: {str(e)}")


@app.post("/v1/documents/ingest/file", response_model=DocumentIngestResponse)
async def ingest_document_file(
    file: UploadFile = File(...),
    source: str = Form(...),
    project: str = Form(...),
    created_at: Optional[str] = Form(None),
    metadata: Optional[str] = Form(None)
):
    """Ingest file bytes and return UTF-8 normalized overlapping chunks."""
    try:
        parsed_metadata = json.loads(metadata) if metadata else None
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid metadata JSON: {str(e)}")

    try:
        service = get_document_ingestion_service()
        content = await file.read()
        result = service.ingest_file(
            file_bytes=content,
            filename=file.filename or "uploaded-file",
            source=source,
            project=project,
            created_at=created_at,
            metadata=parsed_metadata
        )
        return DocumentIngestResponse(
            document_id=result["document_id"],
            metadata=result["metadata"],
            chunks=result["chunks"],
            chunks_created=result["chunks_created"]
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error ingesting file document: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Document ingestion error: {str(e)}")


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


@app.post("/v1/rag/semantic-search", response_model=RAGSemanticSearchResponse)
async def rag_semantic_search(request: RAGSemanticSearchRequest):
    """
    Perform semantic similarity search over Qdrant collections.

    Args:
        query: Search query text
        top_k: Maximum number of nearest neighbors (1-100)
        filters: Optional metadata filters (equality or {"any": [...]})
        collection_name: Optional Qdrant collection override

    Returns:
        Top-k semantic search results with scores and metadata
    """
    try:
        service = get_rag_service()
        results = service.semantic_search(
            query=request.query,
            top_k=request.top_k,
            filters=request.filters,
            collection_name=request.collection_name,
        )
        logger.info(
            "Semantic search completed: %s results (top_k=%s, collection=%s) for query: %s...",
            len(results),
            request.top_k,
            request.collection_name or DEFAULT_COLLECTION,
            request.query[:50],
        )
        return RAGSemanticSearchResponse(
            results=results,
            query=request.query,
            top_k=request.top_k,
            collection_name=request.collection_name,
        )
    except Exception as e:
        logger.error(f"Error in semantic search: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Semantic search error: {str(e)}")


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
@app.post("/v1/rag/queryAPI", response_model=RAGQueryResponse)
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

        graph_context = None
        graph_context_formatted = ""
        relationships_found = 0
        entities_in_graph = 0

        should_enrich_with_graph = bool(
            request.include_graph_context and service.graph_service is not None
        )

        if should_enrich_with_graph:
            try:
                enriched_results = service.search_with_graph_enrichment(
                    query=request.query,
                    limit=request.k,
                    filters=request.filters,
                    graph_depth=1,
                    graph_limit=request.graph_limit,
                )
                if enriched_results.get("enriched"):
                    results = enriched_results.get("vector_results", results)
                    graph_context = enriched_results.get("graph_context")
                    graph_context_formatted = service.format_graph_context_for_llm(graph_context)
                    graph_stats = enriched_results.get("stats", {})
                    relationships_found = graph_stats.get("relationships_found", 0)
                    entities_in_graph = graph_stats.get("entities_in_graph", 0)
            except Exception as graph_error:
                logger.warning("Graph enrichment unavailable, using vector-only retrieval: %s", graph_error)

        retrieval_time_ms = (time.time() - retrieval_start) * 1000

        logger.info(
            "Retrieved %s context chunks in %.2fms (graph relationships=%s)",
            len(results),
            retrieval_time_ms,
            relationships_found,
        )

        if not results:
            logger.warning("No context found for query, generating response without RAG")
            context_text = ""
            retrieval_stats = {
                "chunks_retrieved": 0,
                "retrieval_time_ms": round(retrieval_time_ms, 2),
                "top_score": None,
                "avg_score": None,
                "entities_in_graph": entities_in_graph,
                "relationships_found": relationships_found,
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
                "min_score": round(min(scores), 4) if scores else None,
                "entities_in_graph": entities_in_graph,
                "relationships_found": relationships_found,
            }

        messages_list = []

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


@app.get("/memory/search", response_model=MemorySearchResponse)
async def memory_search_get(
    response: Response,
    query: str = Query(..., description="Search query text"),
    user_id: Optional[str] = Query(None, description="Optional user ID to filter memories"),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of results"),
    use_temporal_decay: bool = Query(True, description="Apply temporal decay to scores"),
    filters: Optional[str] = Query(
        None,
        description=(
            "Optional URL-encoded JSON object for metadata filters. "
            "Use POST /memory/search for complex filters."
        ),
        examples=[
            "{\"project\":\"brainego\"}",
            "%7B%22project%22%3A%22brainego%22%7D"
        ],
    ),
):
    """
    Search memories using query parameters.

    Notes:
    - This endpoint mirrors POST /memory/search for clients that require GET.
    - `filters` must be a JSON object encoded as a string (URL-encoded is supported).
    - POST /memory/search is recommended for complex filters due to URL length limits.
    - Adds Cache-Control: no-store to reduce accidental caching of user-specific searches.
    """
    response.headers["Cache-Control"] = "no-store"

    parsed_filters: Optional[Dict[str, Any]] = None
    if filters:
        try:
            parsed_candidate = json.loads(filters)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid filters JSON: {exc}") from exc

        if not isinstance(parsed_candidate, dict):
            raise HTTPException(status_code=400, detail="Invalid filters JSON: expected an object")

        parsed_filters = parsed_candidate

    request = MemorySearchRequest(
        query=query,
        user_id=user_id,
        limit=limit,
        filters=parsed_filters,
        use_temporal_decay=use_temporal_decay,
    )
    return await memory_search(request)


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


@app.delete("/memory/forget", response_model=MemoryForgetResponse)
async def memory_forget_by_query(memory_id: str):
    """
    Delete a memory by query parameter.

    This endpoint mirrors DELETE /memory/forget/{memory_id} for clients that
    cannot pass path parameters.
    """
    return await memory_forget(memory_id)


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
        "instruction": "Respond to the user input accurately and helpfully.",
        "input": "...",
        "output": "...",
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
            format=request.format,
            min_query_chars=request.min_query_chars,
            min_response_chars=request.min_response_chars,
            deduplicate=request.deduplicate,
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
