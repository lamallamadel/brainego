"""Unit tests for RAG embedding provider selection."""

import sys
import types
from unittest.mock import Mock, patch

# Stub heavy optional dependencies before importing rag_service
sentence_transformers_stub = types.ModuleType("sentence_transformers")
sentence_transformers_stub.SentenceTransformer = Mock
sys.modules.setdefault("sentence_transformers", sentence_transformers_stub)

qdrant_client_stub = types.ModuleType("qdrant_client")
qdrant_client_stub.QdrantClient = Mock
sys.modules.setdefault("qdrant_client", qdrant_client_stub)

qdrant_models_stub = types.ModuleType("qdrant_client.models")
qdrant_models_stub.Distance = Mock
qdrant_models_stub.VectorParams = Mock
qdrant_models_stub.PointStruct = Mock
qdrant_models_stub.Filter = Mock
qdrant_models_stub.FieldCondition = Mock
qdrant_models_stub.MatchValue = Mock
sys.modules.setdefault("qdrant_client.models", qdrant_models_stub)

from rag_service import HTTPEmbeddingServiceClient, RAGIngestionService


def test_http_embedding_service_client_embed_batch() -> None:
    """Client should parse OpenAI-style embedding response."""
    health_response = Mock()
    health_response.json.return_value = {"dimension": 768}
    health_response.raise_for_status.return_value = None

    embed_response = Mock()
    embed_response.json.return_value = {
        "data": [
            {"index": 0, "embedding": [0.1, 0.2]},
            {"index": 1, "embedding": [0.3, 0.4]},
        ]
    }
    embed_response.raise_for_status.return_value = None

    with patch("rag_service.httpx.get", return_value=health_response), patch(
        "rag_service.httpx.post", return_value=embed_response
    ):
        client = HTTPEmbeddingServiceClient("http://embedding-service:8003")
        result = client.embed_batch(["a", "b"])

    assert client.dimension == 768
    assert result == [[0.1, 0.2], [0.3, 0.4]]


def test_rag_service_uses_service_provider() -> None:
    """RAG service should instantiate HTTP embedding client when provider=service."""
    with patch("rag_service.HTTPEmbeddingServiceClient") as mock_client, patch(
        "rag_service.QdrantStorage"
    ) as mock_storage:
        mock_client.return_value.dimension = 768
        storage_instance = mock_storage.return_value
        storage_instance.create_collection.return_value = None

        service = RAGIngestionService(
            embedding_provider="service",
            embedding_service_url="http://embedding-service:8003",
        )

    mock_client.assert_called_once()
    mock_storage.assert_called_once()
    assert service.embedder == mock_client.return_value
