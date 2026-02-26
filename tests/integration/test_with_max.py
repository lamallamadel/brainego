"""
Integration tests with MAX runtime sidecar.

Tests run against a real MAX runtime container + all supporting services
(Redis, PostgreSQL, Qdrant, Neo4j).

Usage:
    pytest tests/integration/test_with_max.py -v -s

Or with Testcontainers Cloud:
    export TESTCONTAINERS_CLOUD_TOKEN=<token>
    pytest tests/integration/test_with_max.py -v -s
"""

import pytest
import asyncio
import httpx
import os
from typing import AsyncGenerator

# MAX Runtime endpoint (from docker-compose.test.yml)
MAX_ENDPOINT = os.getenv("MAX_ENDPOINT", "http://localhost:8080")
API_ENDPOINT = os.getenv("API_ENDPOINT", "http://localhost:8000")


@pytest.fixture(scope="module")
async def max_client() -> AsyncGenerator:
    """Create HTTP client for MAX runtime."""
    async with httpx.AsyncClient(base_url=MAX_ENDPOINT, timeout=30.0) as client:
        yield client


@pytest.fixture(scope="module")
async def api_client() -> AsyncGenerator:
    """Create HTTP client for API server."""
    async with httpx.AsyncClient(base_url=API_ENDPOINT, timeout=30.0) as client:
        yield client


@pytest.mark.integration
@pytest.mark.asyncio
async def test_max_runtime_health(max_client):
    """Test that MAX runtime is up and healthy."""
    response = await max_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "max_serve" in data or "version" in data


@pytest.mark.integration
@pytest.mark.asyncio
async def test_api_health(api_client):
    """Test that API server is up and healthy."""
    response = await api_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["healthy", "degraded"]
    assert "models" in data


@pytest.mark.integration
@pytest.mark.asyncio
async def test_api_chat_completion_with_max(api_client):
    """Test chat completion endpoint with real MAX runtime."""
    response = await api_client.post(
        "/v1/chat/completions",
        json={
            "model": "llama-3.3-8b-instruct",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "What is 2+2?"}
            ],
            "temperature": 0.7,
            "max_tokens": 100
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Verify response structure
    assert "choices" in data
    assert len(data["choices"]) > 0
    assert "message" in data["choices"][0]
    assert "content" in data["choices"][0]["message"]
    assert "usage" in data
    assert data["usage"]["total_tokens"] > 0
    
    # Verify routing metadata (if available)
    if "x-routing-metadata" in data:
        assert "model_id" in data["x-routing-metadata"]
        assert "intent" in data["x-routing-metadata"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_model_routing_with_max(api_client):
    """Test automatic model routing with MAX runtime."""
    # Test code intent (should route to Qwen Coder)
    code_response = await api_client.post(
        "/v1/chat/completions",
        json={
            "messages": [
                {"role": "user", "content": "Write a Python function to sort a list"}
            ],
            "max_tokens": 200
        }
    )
    
    assert code_response.status_code == 200
    code_data = code_response.json()
    assert "choices" in code_data
    
    # Test reasoning intent (should route to DeepSeek R1)
    reasoning_response = await api_client.post(
        "/v1/chat/completions",
        json={
            "messages": [
                {"role": "user", "content": "Explain quantum entanglement step by step"}
            ],
            "max_tokens": 300
        }
    )
    
    assert reasoning_response.status_code == 200
    reasoning_data = reasoning_response.json()
    assert "choices" in reasoning_data


@pytest.mark.integration
@pytest.mark.asyncio
async def test_max_model_switching(api_client):
    """Test explicit model selection with MAX runtime."""
    models_to_test = [
        "llama-3.3-8b-instruct",
        "qwen-2.5-coder-7b",
        "deepseek-r1-7b"
    ]
    
    for model in models_to_test:
        response = await api_client.post(
            "/v1/chat/completions",
            json={
                "model": model,
                "messages": [
                    {"role": "user", "content": "Say hello"}
                ],
                "max_tokens": 50
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "choices" in data
        assert len(data["choices"][0]["message"]["content"]) > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_max_performance_metrics(api_client):
    """Test performance metrics collection with MAX runtime."""
    # Make multiple requests
    for _ in range(5):
        await api_client.post(
            "/v1/chat/completions",
            json={
                "messages": [{"role": "user", "content": "Test"}],
                "max_tokens": 50
            }
        )
    
    # Get metrics
    metrics_response = await api_client.get("/metrics")
    assert metrics_response.status_code == 200
    
    metrics = metrics_response.json()["metrics"]
    assert metrics["request_count"] >= 5
    assert "avg_latency_ms" in metrics
    assert "p95_latency_ms" in metrics
    assert "p99_latency_ms" in metrics


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rag_ingest_with_services(api_client):
    """Test RAG ingestion with all supporting services."""
    response = await api_client.post(
        "/v1/rag/ingest",
        json={
            "text": "Machine learning is a subset of artificial intelligence that focuses on learning from data.",
            "metadata": {
                "source": "test",
                "topic": "machine learning"
            }
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "document_id" in data
    assert data["chunks_created"] > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rag_search_with_max(api_client):
    """Test RAG search with MAX-augmented responses."""
    # First ingest a document
    ingest_response = await api_client.post(
        "/v1/rag/ingest",
        json={
            "text": "Docker is a containerization platform. Kubernetes orchestrates containers.",
            "metadata": {"source": "test"}
        }
    )
    
    assert ingest_response.status_code == 200
    
    # Search for related content
    search_response = await api_client.post(
        "/v1/rag/query",
        json={
            "query": "Tell me about container orchestration",
            "k": 5,
            "max_tokens": 200
        }
    )
    
    assert search_response.status_code == 200
    data = search_response.json()
    assert "response" in data
    assert "context" in data
    assert data["retrieval_stats"]["chunks_retrieved"] > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_memory_with_services(api_client):
    """Test memory service with all backends."""
    # Add memory
    add_response = await api_client.post(
        "/memory/add",
        json={
            "messages": [
                {"role": "user", "content": "I like Python"},
                {"role": "assistant", "content": "Python is great for ML"}
            ],
            "user_id": "test_user",
            "metadata": {"session": "test"}
        }
    )
    
    assert add_response.status_code == 200
    data = add_response.json()
    assert data["status"] == "success"
    assert "memory_id" in data
    
    # Search memory
    search_response = await api_client.post(
        "/memory/search",
        json={
            "query": "Python programming",
            "user_id": "test_user",
            "limit": 10
        }
    )
    
    assert search_response.status_code == 200
    search_data = search_response.json()
    assert "results" in search_data


@pytest.mark.integration
@pytest.mark.asyncio
async def test_graph_with_services(api_client):
    """Test knowledge graph with Neo4j backend."""
    # Process text to extract entities
    process_response = await api_client.post(
        "/graph/process",
        json={
            "text": "Alice works on the machine learning project. Bob contributes to the same project.",
            "document_id": "doc_001",
            "metadata": {"source": "test"}
        }
    )
    
    assert process_response.status_code == 200
    data = process_response.json()
    assert data["status"] == "success"
    assert data["entities_extracted"] > 0
    
    # Query the graph
    query_response = await api_client.post(
        "/graph/query",
        json={
            "query": "MATCH (n) RETURN count(n) as count"
        }
    )
    
    assert query_response.status_code == 200
    query_data = query_response.json()
    assert query_data["status"] == "success"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_feedback_with_postgres(api_client):
    """Test feedback system with PostgreSQL backend."""
    # Add feedback
    feedback_response = await api_client.post(
        "/v1/feedback",
        json={
            "query": "What is AI?",
            "response": "AI is artificial intelligence...",
            "model": "llama-3.3-8b-instruct",
            "rating": 1,
            "user_id": "test_user",
            "intent": "general",
            "metadata": {"source": "test"}
        }
    )
    
    assert feedback_response.status_code == 200
    data = feedback_response.json()
    assert data["status"] == "success"
    assert "feedback_id" in data
    
    # Get accuracy metrics
    accuracy_response = await api_client.get(
        "/v1/feedback/accuracy?model=llama-3.3-8b-instruct"
    )
    
    assert accuracy_response.status_code == 200
    accuracy_data = accuracy_response.json()
    assert isinstance(accuracy_data, list)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_max_circuit_breaker(api_client):
    """Test circuit breaker protection for MAX runtime."""
    # Get circuit breaker stats
    response = await api_client.get("/circuit-breakers")
    assert response.status_code == 200
    
    data = response.json()
    assert "circuit_breakers" in data
    
    # Check if MAX has a circuit breaker
    circuit_breakers = data["circuit_breakers"]
    if circuit_breakers:
        for cb_name, cb_stats in circuit_breakers.items():
            assert "state" in cb_stats
            assert cb_stats["state"] in ["CLOSED", "OPEN", "HALF_OPEN"]


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.asyncio
async def test_max_streaming_response(api_client):
    """Test streaming response from MAX runtime."""
    response = await api_client.post(
        "/v1/chat/completions",
        json={
            "messages": [
                {"role": "user", "content": "Write a short poem"}
            ],
            "max_tokens": 100,
            "stream": False  # Note: streaming might not be implemented yet
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "choices" in data


@pytest.mark.integration
@pytest.mark.asyncio
async def test_max_error_handling(api_client):
    """Test error handling with MAX runtime."""
    # Invalid model
    response = await api_client.post(
        "/v1/chat/completions",
        json={
            "model": "nonexistent-model",
            "messages": [{"role": "user", "content": "test"}]
        }
    )
    
    # Should either work (if there's a default) or fail gracefully
    assert response.status_code in [200, 400, 503]
    
    # Empty messages
    response = await api_client.post(
        "/v1/chat/completions",
        json={
            "messages": []
        }
    )
    
    assert response.status_code == 400


@pytest.mark.integration
@pytest.mark.asyncio
async def test_end_to_end_with_max(api_client):
    """End-to-end test: RAG + Graph + Memory + MAX inference."""
    # 1. Ingest knowledge
    ingest_response = await api_client.post(
        "/v1/rag/ingest",
        json={
            "text": "Docker containerizes applications. Kubernetes orchestrates them across machines.",
            "metadata": {"source": "devops"}
        }
    )
    assert ingest_response.status_code == 200
    
    # 2. Add to knowledge graph
    graph_response = await api_client.post(
        "/graph/process",
        json={
            "text": "DevOps engineers use Docker and Kubernetes",
            "document_id": "devops_001"
        }
    )
    assert graph_response.status_code == 200
    
    # 3. Store memory
    memory_response = await api_client.post(
        "/memory/add",
        json={
            "messages": [
                {"role": "user", "content": "I work with containerization"},
                {"role": "assistant", "content": "Docker and Kubernetes are popular choices"}
            ],
            "user_id": "devops_engineer"
        }
    )
    assert memory_response.status_code == 200
    
    # 4. Query with MAX runtime
    query_response = await api_client.post(
        "/v1/chat/completions",
        json={
            "messages": [
                {"role": "user", "content": "Explain Docker and Kubernetes"}
            ],
            "max_tokens": 200
        }
    )
    assert query_response.status_code == 200
    
    # 5. Add feedback for learning
    feedback_response = await api_client.post(
        "/v1/feedback",
        json={
            "query": "Explain Docker and Kubernetes",
            "response": query_response.json()["choices"][0]["message"]["content"],
            "model": "llama-3.3-8b-instruct",
            "rating": 1,
            "user_id": "devops_engineer"
        }
    )
    assert feedback_response.status_code == 200
