#!/usr/bin/env python3
"""
OpenAI-compatible API server for MAX Serve with Llama 3.3 8B Instruct.
Exposes /v1/chat/completions and /health endpoints.
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
        "message": "OpenAI-Compatible API for MAX Serve",
        "version": "1.0.0",
        "endpoints": {
            "chat": "/v1/chat/completions",
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
