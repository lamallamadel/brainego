#!/usr/bin/env python3
"""
OpenAI-compatible API server for MAX Serve with Llama 3.3 8B Instruct.
Exposes /v1/chat/completions, /v1/rag/ingest, and /health endpoints.
"""

import os
import time
import json
import uuid
import logging
from typing import List, Dict, Optional, Any
from datetime import datetime

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import httpx

from rag_service import RAGIngestionService
from memory_service import MemoryService

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

# Create FastAPI app
app = FastAPI(
    title="OpenAI-Compatible API for MAX Serve",
    description="OpenAI-compatible chat completions API backed by MAX Serve with Llama 3.3 8B Instruct",
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

# Initialize RAG service (lazy loading)
rag_service = None
memory_service = None


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
    """Call MAX Serve API and return response text and token counts."""
    
    payload = {
        "prompt": prompt,
        "max_tokens": params.get("max_tokens", 2048),
        "temperature": params.get("temperature", 0.7),
        "top_p": params.get("top_p", 0.9),
        "stop": params.get("stop", ["<|eot_id|>", "<|end_of_text|>"]),
    }
    
    async with httpx.AsyncClient(timeout=300.0) as client:
        try:
            response = await client.post(MAX_SERVE_GENERATE_URL, json=payload)
            response.raise_for_status()
            
            result = response.json()
            generated_text = result.get("text", "")
            
            # Clean up the response
            generated_text = generated_text.strip()
            
            # Estimate tokens
            prompt_tokens = estimate_tokens(prompt)
            completion_tokens = estimate_tokens(generated_text)
            
            return generated_text, prompt_tokens, completion_tokens
            
        except httpx.HTTPError as e:
            logger.error(f"MAX Serve API error: {e}")
            raise HTTPException(status_code=503, detail=f"MAX Serve error: {str(e)}")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "OpenAI-Compatible API for MAX Serve with RAG and Memory",
        "version": "1.0.0",
        "endpoints": {
            "chat": "/v1/chat/completions",
            "health": "/health",
            "metrics": "/metrics",
            "rag_ingest": "/v1/rag/ingest",
            "rag_ingest_batch": "/v1/rag/ingest/batch",
            "rag_search": "/v1/rag/search",
            "rag_query": "/v1/rag/query",
            "rag_delete": "/v1/rag/documents/{document_id}",
            "rag_stats": "/v1/rag/stats",
            "memory_add": "POST /memory/add",
            "memory_search": "GET /memory/search",
            "memory_forget": "DELETE /memory/forget/{memory_id}",
            "memory_stats": "GET /memory/stats"
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
    
    return HealthResponse(
        status="healthy" if max_serve_status == "healthy" else "degraded",
        timestamp=datetime.utcnow().isoformat(),
        model="llama-3.3-8b-instruct",
        max_serve_status=max_serve_status
    )


@app.get("/metrics")
async def get_metrics():
    """Get performance metrics."""
    return {
        "metrics": metrics.get_stats(),
        "timestamp": datetime.utcnow().isoformat()
    }


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest, raw_request: Request):
    """
    OpenAI-compatible chat completions endpoint.
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
        
        # Call MAX Serve
        params = {
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "top_p": request.top_p,
            "stop": request.stop or ["<|eot_id|>", "<|end_of_text|>"],
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


@app.post("/v1/models")
async def list_models():
    """List available models (OpenAI-compatible)."""
    return {
        "object": "list",
        "data": [
            {
                "id": "llama-3.3-8b-instruct",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "modular",
                "permission": [],
                "root": "llama-3.3-8b-instruct",
                "parent": None,
            }
        ]
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
        generated_text, prompt_tokens, completion_tokens = await call_max_serve(prompt, params)
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


if __name__ == "__main__":
    logger.info("Starting OpenAI-compatible API server...")
    logger.info(f"MAX Serve URL: {MAX_SERVE_URL}")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
        access_log=True
    )
