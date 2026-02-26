"""
Integration tests using Testcontainers Cloud.

These tests use real containers running in Testcontainers Cloud:
- No local Docker required
- No docker-in-docker required
- GitHub Actions automatically connects to cloud services

To run locally with Testcontainers Cloud:
1. Set TESTCONTAINERS_CLOUD_TOKEN environment variable
2. Install: pip install testcontainers
3. Run: pytest tests/integration/ -v -s
"""

import pytest
import asyncio
import json
from typing import AsyncGenerator

# Optional: Import Testcontainers if available
# If not installed, tests will be skipped in local dev
try:
    from testcontainers.redis import RedisContainer
    from testcontainers.postgres import PostgresContainer
    HAS_TESTCONTAINERS = True
except ImportError:
    HAS_TESTCONTAINERS = False


@pytest.mark.integration
@pytest.mark.skipif(not HAS_TESTCONTAINERS, reason="testcontainers not installed")
@pytest.fixture(scope="module")
def redis_service():
    """
    Start Redis in Testcontainers Cloud.
    
    In GitHub Actions: Runs in cloud via Testcontainers Cloud agent
    Locally: Requires TESTCONTAINERS_CLOUD_TOKEN or local Docker
    """
    with RedisContainer(image="redis:7-alpine") as container:
        yield container


@pytest.mark.integration
@pytest.mark.skipif(not HAS_TESTCONTAINERS, reason="testcontainers not installed")
@pytest.fixture(scope="module")
def postgres_service():
    """
    Start PostgreSQL in Testcontainers Cloud.
    
    In GitHub Actions: Runs in cloud
    Locally: Requires cloud token or Docker
    """
    with PostgresContainer(
        image="postgres:15-alpine",
        dbname="brainego_test",
        username="testuser",
        password="testpass"
    ) as container:
        yield container


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_TESTCONTAINERS, reason="testcontainers not installed")
async def test_redis_connection(redis_service):
    """Test that Redis container is accessible."""
    import redis
    
    # Get connection URL from container
    redis_url = redis_service.get_connection_url()
    
    # Connect using the URL
    client = redis.from_url(redis_url, decode_responses=True)
    
    # Test basic operations
    client.set("test_key", "test_value")
    result = client.get("test_key")
    
    assert result == "test_value"
    
    client.close()


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_TESTCONTAINERS, reason="testcontainers not installed")
async def test_postgres_connection(postgres_service):
    """Test that PostgreSQL container is accessible."""
    import psycopg2
    
    # Get connection details from container
    conn = psycopg2.connect(
        host=postgres_service.get_container_host_ip(),
        port=postgres_service.get_exposed_port(5432),
        database="brainego_test",
        user="testuser",
        password="testpass"
    )
    
    cursor = conn.cursor()
    cursor.execute("SELECT 1")
    result = cursor.fetchone()
    
    assert result[0] == 1
    
    cursor.close()
    conn.close()


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_TESTCONTAINERS, reason="testcontainers not installed")
async def test_api_with_redis_backend(redis_service):
    """
    Integration test: API with Redis backend.
    
    This demonstrates how to test your API against a real Redis instance
    running in Testcontainers Cloud.
    """
    import redis
    from httpx import AsyncClient
    
    # from api_server import app  # Your FastAPI app
    
    redis_url = redis_service.get_connection_url()
    redis_client = redis.from_url(redis_url, decode_responses=True)
    
    # Store test data in Redis
    redis_client.set("user:123", json.dumps({"name": "Test User"}))
    
    # In a real test, you'd start your API pointing to this Redis
    # async with AsyncClient(app=app, base_url="http://test") as client:
    #     response = await client.get("/v1/users/123")
    #     assert response.status_code == 200
    #     data = response.json()
    #     assert data["name"] == "Test User"
    
    # Verify data was stored correctly
    stored = redis_client.get("user:123")
    assert json.loads(stored)["name"] == "Test User"
    
    redis_client.close()


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_TESTCONTAINERS, reason="testcontainers not installed")
async def test_database_schema_migration(postgres_service):
    """
    Integration test: Test database migrations.
    
    Demonstrates how to test schema changes against a real PostgreSQL instance.
    """
    import psycopg2
    
    conn = psycopg2.connect(
        host=postgres_service.get_container_host_ip(),
        port=postgres_service.get_exposed_port(5432),
        database="brainego_test",
        user="testuser",
        password="testpass"
    )
    
    cursor = conn.cursor()
    
    # Create a test table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255),
            email VARCHAR(255),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    
    # Test insert
    cursor.execute(
        "INSERT INTO users (name, email) VALUES (%s, %s) RETURNING id",
        ("Test User", "test@example.com")
    )
    user_id = cursor.fetchone()[0]
    conn.commit()
    
    # Test select
    cursor.execute("SELECT name, email FROM users WHERE id = %s", (user_id,))
    result = cursor.fetchone()
    
    assert result[0] == "Test User"
    assert result[1] == "test@example.com"
    
    cursor.close()
    conn.close()


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_TESTCONTAINERS, reason="testcontainers not installed")
async def test_concurrent_redis_operations(redis_service):
    """
    Integration test: Concurrent operations.
    
    Demonstrates how to test concurrent operations against Testcontainers.
    """
    import redis
    
    redis_url = redis_service.get_connection_url()
    client = redis.from_url(redis_url, decode_responses=True)
    
    # Concurrent set operations
    tasks = [
        asyncio.create_task(asyncio.to_thread(
            client.set,
            f"key:{i}",
            f"value:{i}"
        ))
        for i in range(100)
    ]
    
    await asyncio.gather(*tasks)
    
    # Verify all keys were set
    for i in range(100):
        value = client.get(f"key:{i}")
        assert value == f"value:{i}"
    
    client.close()


@pytest.mark.integration
@pytest.mark.slow  # Mark as slow test
@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_TESTCONTAINERS, reason="testcontainers not installed")
async def test_large_data_load(postgres_service):
    """
    Integration test: Large data operations (marked as slow).
    
    To skip slow tests: pytest -m "not slow"
    """
    import psycopg2
    
    conn = psycopg2.connect(
        host=postgres_service.get_container_host_ip(),
        port=postgres_service.get_exposed_port(5432),
        database="brainego_test",
        user="testuser",
        password="testpass"
    )
    
    cursor = conn.cursor()
    
    # Create table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id SERIAL PRIMARY KEY,
            message TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    
    # Insert 1000 rows
    for i in range(1000):
        cursor.execute(
            "INSERT INTO logs (message) VALUES (%s)",
            (f"Log message {i}",)
        )
    conn.commit()
    
    # Count rows
    cursor.execute("SELECT COUNT(*) FROM logs")
    count = cursor.fetchone()[0]
    
    assert count == 1000
    
    cursor.close()
    conn.close()


@pytest.mark.integration
def test_multiple_containers_simultaneously(redis_service, postgres_service):
    """
    Integration test: Multiple services at once.
    
    This test demonstrates using Redis and PostgreSQL together
    in the same test.
    """
    import redis
    import psycopg2
    import json
    
    # Setup Redis
    redis_url = redis_service.get_connection_url()
    redis_client = redis.from_url(redis_url, decode_responses=True)
    
    # Setup PostgreSQL
    pg_conn = psycopg2.connect(
        host=postgres_service.get_container_host_ip(),
        port=postgres_service.get_exposed_port(5432),
        database="brainego_test",
        user="testuser",
        password="testpass"
    )
    
    # Store data in both
    test_data = {"id": 1, "name": "Test"}
    
    redis_client.set("cache:1", json.dumps(test_data))
    
    cursor = pg_conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS items (id INT, name TEXT)")
    cursor.execute("INSERT INTO items VALUES (%s, %s)", (1, "Test"))
    pg_conn.commit()
    
    # Verify both stores
    redis_data = json.loads(redis_client.get("cache:1"))
    assert redis_data["name"] == "Test"
    
    cursor.execute("SELECT name FROM items WHERE id = 1")
    pg_data = cursor.fetchone()
    assert pg_data[0] == "Test"
    
    cursor.close()
    pg_conn.close()
    redis_client.close()
