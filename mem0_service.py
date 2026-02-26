#!/usr/bin/env python3
"""Dedicated Mem0 API service backed by Qdrant and Redis."""

import logging
import os
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from memory_service import MemoryService

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class MemoryAddRequest(BaseModel):
    """Request payload for adding memory entries."""

    messages: List[Dict[str, str]] = Field(..., min_length=1)
    user_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class MemorySearchRequest(BaseModel):
    """Request payload for querying memory entries."""

    query: str = Field(..., min_length=1)
    user_id: Optional[str] = None
    limit: int = Field(default=10, ge=1, le=100)
    filters: Optional[Dict[str, Any]] = None
    use_temporal_decay: bool = True


app = FastAPI(title="Mem0 Service", version="1.0.0")

memory_service = MemoryService(
    qdrant_host=os.getenv("QDRANT_HOST", "qdrant"),
    qdrant_port=int(os.getenv("QDRANT_PORT", "6333")),
    redis_host=os.getenv("REDIS_HOST", "redis"),
    redis_port=int(os.getenv("REDIS_PORT", "6379")),
    redis_db=int(os.getenv("REDIS_DB", "0")),
    memory_collection=os.getenv("QDRANT_COLLECTION", "memories"),
    temporal_decay_factor=float(os.getenv("MEMORY_TEMPORAL_DECAY_FACTOR", "0.1")),
    cosine_weight=float(os.getenv("MEMORY_COSINE_WEIGHT", "0.7")),
    temporal_weight=float(os.getenv("MEMORY_TEMPORAL_WEIGHT", "0.3")),
)


@app.get("/health")
def health() -> Dict[str, str]:
    """Service health endpoint."""
    return {"status": "ok", "service": "mem0"}


@app.post("/memory/add")
def add_memory(request: MemoryAddRequest) -> Dict[str, Any]:
    """Add conversation memory."""
    try:
        return memory_service.add_memory(
            messages=request.messages,
            user_id=request.user_id,
            metadata=request.metadata,
        )
    except Exception as exc:  # pragma: no cover - defensive API boundary
        logger.error("Failed to add memory", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to add memory: {exc}") from exc


@app.post("/memory/search")
def search_memory(request: MemorySearchRequest) -> Dict[str, Any]:
    """Search memories."""
    try:
        results = memory_service.search_memory(
            query=request.query,
            user_id=request.user_id,
            limit=request.limit,
            filters=request.filters,
            use_temporal_decay=request.use_temporal_decay,
        )
        return {"query": request.query, "results": results, "limit": request.limit}
    except Exception as exc:  # pragma: no cover - defensive API boundary
        logger.error("Failed to search memory", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to search memory: {exc}") from exc


@app.delete("/memory/forget/{memory_id}")
def forget_memory(memory_id: str) -> Dict[str, Any]:
    """Delete a memory by id."""
    try:
        return memory_service.forget_memory(memory_id)
    except Exception as exc:  # pragma: no cover - defensive API boundary
        logger.error("Failed to forget memory", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to forget memory: {exc}") from exc


@app.get("/memory/stats")
def memory_stats() -> Dict[str, Any]:
    """Return memory backend statistics."""
    try:
        return memory_service.get_memory_stats()
    except Exception as exc:  # pragma: no cover - defensive API boundary
        logger.error("Failed to fetch memory stats", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch memory stats: {exc}") from exc
