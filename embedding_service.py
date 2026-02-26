#!/usr/bin/env python3
"""Local embedding service exposing OpenAI-compatible /v1/embeddings endpoint."""

import logging
import os
import time
from typing import List, Union

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sentence_transformers import SentenceTransformer

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-ai/nomic-embed-text-v1.5")
EMBEDDING_SERVICE_HOST = os.getenv("EMBEDDING_SERVICE_HOST", "0.0.0.0")
EMBEDDING_SERVICE_PORT = int(os.getenv("EMBEDDING_SERVICE_PORT", "8003"))

app = FastAPI(
    title="Local Embedding Service",
    description="OpenAI-compatible embeddings endpoint for local model inference",
    version="1.0.0",
)

_model = None
_model_dimension = None


class EmbeddingRequest(BaseModel):
    model: str = Field(default=EMBEDDING_MODEL, description="Embedding model name")
    input: Union[str, List[str]] = Field(..., description="Text input or list of texts")


class EmbeddingData(BaseModel):
    object: str = "embedding"
    index: int
    embedding: List[float]


class EmbeddingUsage(BaseModel):
    prompt_tokens: int
    total_tokens: int


class EmbeddingResponse(BaseModel):
    object: str = "list"
    data: List[EmbeddingData]
    model: str
    usage: EmbeddingUsage


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _load_model() -> None:
    global _model, _model_dimension
    if _model is None:
        logger.info("Loading embedding model: %s", EMBEDDING_MODEL)
        _model = SentenceTransformer(EMBEDDING_MODEL, trust_remote_code=True)
        _model_dimension = _model.get_sentence_embedding_dimension()
        logger.info("Embedding model loaded with dimension: %s", _model_dimension)


@app.on_event("startup")
def startup_event() -> None:
    _load_model()


@app.get("/health")
def health() -> dict:
    return {
        "status": "healthy",
        "model": EMBEDDING_MODEL,
        "dimension": _model_dimension,
    }


@app.post("/v1/embeddings", response_model=EmbeddingResponse)
def create_embeddings(request: EmbeddingRequest) -> EmbeddingResponse:
    try:
        _load_model()
        inputs = request.input if isinstance(request.input, list) else [request.input]
        if not inputs:
            raise HTTPException(status_code=400, detail="Input list cannot be empty")

        started = time.time()
        vectors = _model.encode(inputs, convert_to_numpy=True, show_progress_bar=False)
        elapsed_ms = (time.time() - started) * 1000

        data = [
            EmbeddingData(index=i, embedding=vector.tolist())
            for i, vector in enumerate(vectors)
        ]
        prompt_tokens = sum(_estimate_tokens(text) for text in inputs)

        logger.info(
            "Generated %s embeddings in %.2f ms",
            len(data),
            elapsed_ms,
        )

        return EmbeddingResponse(
            data=data,
            model=request.model,
            usage=EmbeddingUsage(prompt_tokens=prompt_tokens, total_tokens=prompt_tokens),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Embedding generation failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Embedding generation failed: {str(exc)}")


if __name__ == "__main__":
    uvicorn.run(app, host=EMBEDDING_SERVICE_HOST, port=EMBEDDING_SERVICE_PORT)
