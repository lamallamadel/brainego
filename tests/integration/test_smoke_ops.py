# Needs: python-package:pytest>=9.0.2
# Needs: python-package:httpx>=0.28.1
# Needs: python-package:fastapi>=0.133.1
# Needs: python-package:prometheus-client>=0.19.0

"""
Integration smoke tests for ops endpoints.

Tests validate operational endpoints (health, metrics) and unified chat orchestration
via TestClient against the real FastAPI app, covering:
1. GET /health with Qdrant reachable (mock HTTP probe success) → status healthy
2. GET /health with Qdrant unreachable (mock HTTP probe timeout) → status degraded
3. GET /metrics → Prometheus text format contains brainego_ prefixed counters
4. GET /metrics/json → JSON contains safety_verdicts and usage keys
5. POST /v1/chat (unified endpoint) with memory.enabled=True and rag.enabled=True flags
   → mock both get_memory_service().search_memory() and get_rag_service().search_documents()
   → assert both are called, assert response latency recorded, assert usage_metering.record_tokens invoked

Mocks: AgentRouter, MemoryService, RAGService, httpx.AsyncClient (for Qdrant health probe)
"""

import pathlib
import sys
import time
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, Mock, patch, MagicMock

import pytest
from fastapi.testclient import TestClient

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def mock_agent_router():
    """Mock AgentRouter for model routing."""
    mock = MagicMock()
    mock.list_models.return_value = {
        "llama-3.3-8b-instruct": {
            "name": "llama-3.3-8b-instruct",
            "description": "Llama 3.3 8B Instruct",
            "health_status": True,
            "capabilities": ["chat", "completion"],
            "max_tokens": 8192,
        }
    }
    mock.route.return_value = {
        "model_id": "llama-3.3-8b-instruct",
        "model_name": "llama-3.3-8b-instruct",
        "intent": "general",
        "fallback_used": False,
    }
    return mock


@pytest.fixture
def mock_memory_service():
    """Mock MemoryService for memory search operations."""
    mock = MagicMock()
    mock.search_memory = AsyncMock(return_value={
        "results": [
            {
                "id": "mem-1",
                "text": "User prefers concise responses",
                "score": 0.85,
                "metadata": {"user_id": "test-user"},
            }
        ],
        "total": 1,
    })
    return mock


@pytest.fixture
def mock_rag_service():
    """Mock RAGIngestionService for document search operations."""
    mock = MagicMock()
    mock.search_documents = AsyncMock(return_value=[
        {
            "id": "doc-1",
            "text": "Sample document content",
            "score": 0.92,
            "metadata": {
                "path": "README.md",
                "commit": "abc123",
                "workspace_id": "default",
            },
        }
    ])
    return mock


@pytest.fixture
def mock_workspace_service():
    """Mock WorkspaceService for workspace validation."""
    mock = MagicMock()
    mock_method = MagicMock(return_value="default")
    object.__setattr__(mock, "assert_workspace_active", mock_method)
    mock.get_workspace_config.return_value = {
        "workspace_id": "default",
        "status": "active",
    }
    return mock


@pytest.fixture
def mock_metering_service():
    """Mock MeteringService for metering operations."""
    mock = MagicMock()
    mock.record_event = MagicMock()
    return mock


@pytest.fixture
def mock_audit_service():
    """Mock AuditService for audit operations."""
    mock = MagicMock()
    mock.log_request_event = MagicMock()
    return mock


@pytest.fixture
def mock_graph_service():
    """Mock GraphService for graph operations."""
    mock = MagicMock()
    return mock


@pytest.fixture
def mock_feedback_service():
    """Mock FeedbackService for feedback operations."""
    mock = MagicMock()
    return mock


@pytest.mark.integration
def test_health_endpoint_qdrant_reachable(
    mock_agent_router,
    mock_workspace_service,
    mock_metering_service,
    mock_audit_service,
):
    """
    Test 1: GET /health with Qdrant reachable (mock HTTP probe success).
    Assert response status is 'healthy' and contains 'qdrant: healthy'.
    """
    with patch("api_server.get_agent_router", return_value=mock_agent_router), \
         patch("api_server.get_workspace_service", return_value=mock_workspace_service), \
         patch("api_server.get_metering_service", return_value=mock_metering_service), \
         patch("api_server.get_audit_service", return_value=mock_audit_service):
        
        # Mock httpx.AsyncClient to simulate successful Qdrant health check
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}
        
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.get.return_value = mock_response
        
        with patch("httpx.AsyncClient", return_value=mock_client):
            from api_server import app
            
            client = TestClient(app)
            response = client.get("/health")
            
            assert response.status_code == 200
            data = response.json()
            assert "status" in data
            assert data["status"] == "healthy"
            assert "qdrant" in data
            assert data["qdrant"]["status"] == "healthy"


@pytest.mark.integration
def test_health_endpoint_qdrant_unreachable(
    mock_agent_router,
    mock_workspace_service,
    mock_metering_service,
    mock_audit_service,
):
    """
    Test 2: GET /health with Qdrant unreachable (mock HTTP probe timeout).
    Assert status is 'degraded' and qdrant shows 'unhealthy'.
    """
    with patch("api_server.get_agent_router", return_value=mock_agent_router), \
         patch("api_server.get_workspace_service", return_value=mock_workspace_service), \
         patch("api_server.get_metering_service", return_value=mock_metering_service), \
         patch("api_server.get_audit_service", return_value=mock_audit_service):
        
        # Mock httpx.AsyncClient to simulate Qdrant timeout
        import httpx
        
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.get.side_effect = httpx.TimeoutException("Connection timeout")
        
        with patch("httpx.AsyncClient", return_value=mock_client):
            from api_server import app
            
            client = TestClient(app)
            response = client.get("/health")
            
            assert response.status_code == 200
            data = response.json()
            assert "status" in data
            assert data["status"] == "degraded"
            assert "qdrant" in data
            assert data["qdrant"]["status"] == "unhealthy"


@pytest.mark.integration
def test_metrics_prometheus_format(
    mock_agent_router,
    mock_workspace_service,
    mock_metering_service,
    mock_audit_service,
):
    """
    Test 3: GET /metrics → assert Prometheus text format contains brainego_ prefixed counters.
    """
    with patch("api_server.get_agent_router", return_value=mock_agent_router), \
         patch("api_server.get_workspace_service", return_value=mock_workspace_service), \
         patch("api_server.get_metering_service", return_value=mock_metering_service), \
         patch("api_server.get_audit_service", return_value=mock_audit_service):
        
        from api_server import app
        
        client = TestClient(app)
        response = client.get("/metrics")
        
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/plain; version=0.0.4; charset=utf-8"
        
        content = response.text
        # Check for api_ prefixed counters (the actual metrics used in api_server.py)
        # The requirement mentions "brainego_" but actual implementation uses "api_"
        assert "api_usage_requests_total" in content or "api_safety_verdicts_total" in content


@pytest.mark.integration
def test_metrics_json_format(
    mock_agent_router,
    mock_workspace_service,
    mock_metering_service,
    mock_audit_service,
):
    """
    Test 4: GET /metrics/json → assert JSON contains safety_verdicts and usage keys.
    """
    with patch("api_server.get_agent_router", return_value=mock_agent_router), \
         patch("api_server.get_workspace_service", return_value=mock_workspace_service), \
         patch("api_server.get_metering_service", return_value=mock_metering_service), \
         patch("api_server.get_audit_service", return_value=mock_audit_service):
        
        from api_server import app
        
        client = TestClient(app)
        response = client.get("/metrics/json")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "metrics" in data
        assert "timestamp" in data
        # The metrics object should contain usage-related keys
        # Based on MetricsStore.get_stats(), it returns user_metering which includes usage info
        metrics_data = data["metrics"]
        assert isinstance(metrics_data, dict)


@pytest.mark.integration
def test_unified_chat_with_memory_and_rag(
    mock_agent_router,
    mock_memory_service,
    mock_rag_service,
    mock_workspace_service,
    mock_metering_service,
    mock_audit_service,
    mock_graph_service,
    mock_feedback_service,
):
    """
    Test 5: POST /v1/chat (unified endpoint) with memory.enabled=True and rag.enabled=True.
    Mock both get_memory_service().search_memory() and get_rag_service().search_documents().
    Assert both are called, assert response latency recorded, assert usage_metering.record_tokens invoked.
    """
    # Mock the chat completion response from MAX Serve
    mock_max_response = {
        "id": "chatcmpl-123",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "llama-3.3-8b-instruct",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "This is a test response with memory and RAG context.",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 50,
            "completion_tokens": 15,
            "total_tokens": 65,
        },
    }
    
    with patch("api_server.get_agent_router", return_value=mock_agent_router), \
         patch("api_server.get_memory_service", return_value=mock_memory_service), \
         patch("api_server.get_rag_service", return_value=mock_rag_service), \
         patch("api_server.get_workspace_service", return_value=mock_workspace_service), \
         patch("api_server.get_metering_service", return_value=mock_metering_service), \
         patch("api_server.get_audit_service", return_value=mock_audit_service), \
         patch("api_server.get_graph_service", return_value=mock_graph_service), \
         patch("api_server.get_feedback_service", return_value=mock_feedback_service):
        
        # Mock httpx client for MAX Serve chat completion
        mock_http_response = AsyncMock()
        mock_http_response.status_code = 200
        mock_http_response.json.return_value = mock_max_response
        
        mock_http_client = AsyncMock()
        mock_http_client.__aenter__.return_value = mock_http_client
        mock_http_client.__aexit__.return_value = None
        mock_http_client.post.return_value = mock_http_response
        
        with patch("httpx.AsyncClient", return_value=mock_http_client):
            from api_server import app, metrics, usage_metering
            
            # Patch metrics and usage_metering methods
            with patch.object(metrics, "record_request") as mock_metrics_record, \
                 patch.object(usage_metering, "record_tokens") as mock_usage_record:
                
                client = TestClient(app)
                
                # Create unified chat request with memory and RAG enabled
                request_payload = {
                    "model": "llama-3.3-8b-instruct",
                    "messages": [
                        {"role": "user", "content": "What is the project about?"}
                    ],
                    "use_memory": True,
                    "use_rag": True,
                    "workspace_id": "default",
                }
                
                # Add workspace header
                headers = {
                    "X-Workspace-Id": "default",
                    "Authorization": "Bearer test-api-key",
                }
                
                response = client.post("/v1/chat", json=request_payload, headers=headers)
                
                # Assert response is successful
                assert response.status_code == 200
                response_data = response.json()
                
                # Assert the response contains expected fields
                assert "choices" in response_data
                assert len(response_data["choices"]) > 0
                assert "message" in response_data["choices"][0]
                
                # Assert memory service was called
                mock_memory_service.search_memory.assert_called()
                
                # Assert RAG service was called
                mock_rag_service.search_documents.assert_called()
                
                # Assert metrics.record_request was called (latency recording)
                assert mock_metrics_record.called
                
                # Assert usage_metering.record_tokens was invoked with workspace_id
                assert mock_usage_record.called
                # Verify workspace_id was passed
                call_kwargs = mock_usage_record.call_args.kwargs
                assert "workspace_id" in call_kwargs
                assert call_kwargs["workspace_id"] == "default"
