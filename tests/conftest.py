"""
Pytest configuration and fixtures for brainego tests.

This file provides shared fixtures for both unit and integration tests.
Testcontainers Cloud is used for integration tests (no local Docker required).
"""

import pytest
import asyncio
import os
from typing import AsyncGenerator, Generator

# Integration test fixtures (Testcontainers Cloud)


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def api_base_url() -> str:
    """Base URL for API tests."""
    return "http://localhost:8000"


@pytest.fixture
def testcontainers_config() -> dict:
    """Configuration for Testcontainers Cloud."""
    return {
        # Testcontainers Cloud token is read from TESTCONTAINERS_CLOUD_TOKEN env var
        # Set in GitHub Actions secrets automatically
        "cloud_enabled": os.getenv("TESTCONTAINERS_CLOUD_TOKEN") is not None,
        "timeout_seconds": int(os.getenv("TESTCONTAINERS_TIMEOUT", "60")),
    }


# Mock fixtures for unit tests


@pytest.fixture
def mock_redis_client():
    """Mock Redis client for unit tests."""
    from unittest.mock import AsyncMock, MagicMock
    
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=b"test_value")
    mock_client.set = AsyncMock(return_value=True)
    mock_client.delete = AsyncMock(return_value=1)
    mock_client.lpush = AsyncMock(return_value=1)
    mock_client.lpop = AsyncMock(return_value=b"test_item")
    
    return mock_client


@pytest.fixture
def mock_qdrant_client():
    """Mock Qdrant client for unit tests."""
    from unittest.mock import AsyncMock
    
    mock_client = AsyncMock()
    mock_client.search = AsyncMock(return_value=[
        {
            "id": 1,
            "score": 0.95,
            "payload": {"text": "test embedding"}
        }
    ])
    mock_client.upsert = AsyncMock(return_value={"status": "completed"})
    
    return mock_client


@pytest.fixture
def mock_postgres_client():
    """Mock Postgres client for unit tests."""
    from unittest.mock import AsyncMock
    
    mock_client = AsyncMock()
    mock_client.execute = AsyncMock(return_value=[{"id": 1, "data": "test"}])
    mock_client.fetchrow = AsyncMock(return_value={"id": 1, "data": "test"})
    mock_client.close = AsyncMock()
    
    return mock_client


@pytest.fixture
def mock_httpx_client():
    """Mock httpx client for unit tests."""
    from unittest.mock import AsyncMock
    
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=AsyncMock(
        status_code=200,
        json=AsyncMock(return_value={"result": "success"})
    ))
    mock_client.get = AsyncMock(return_value=AsyncMock(
        status_code=200,
        json=AsyncMock(return_value={"status": "ok"})
    ))
    
    return mock_client


# Markers for test categorization


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "unit: mark test as a unit test (no external services)"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as integration test (requires services)"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow (>5 seconds)"
    )
    config.addinivalue_line(
        "markers", "asyncio: mark test as async"
    )
