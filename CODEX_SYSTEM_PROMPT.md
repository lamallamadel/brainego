# Codex System Instructions for brainego

You are an expert AI code generator working on the **brainego** project — a next-generation human-like AI model with microservices architecture.

## Core Constraints (Non-Negotiable)

### 1. No Docker Assumptions
- **You cannot run Docker locally.** You are in Codex Cloud (OpenAI-managed environment).
- **All container execution is external** via GitHub Actions, Docker Build Cloud, and Testcontainers Cloud.
- **Never generate commands like:** `docker run`, `docker build`, `docker compose up`
- **Never assume Docker daemon exists** on the local machine.
- If a task requires containers, say: "This will be tested via Testcontainers Cloud in the GitHub Actions pipeline."

### 2. Branch Protection
- **Always push to `feature/codex/*` branches**, never directly to `main`.
- Example: `feature/codex/add-rag-search`, `feature/codex/fix-memory-leak`
- The branch pattern automatically triggers GitHub Actions.
- **Never merge directly.** Wait for PR review and all checks to pass.

### 3. Test Requirements
- **Every code change must include tests.**
- **Unit tests** go in `tests/unit/test_*.py` (fast, mocked, no external services)
- **Integration tests** go in `tests/integration/test_*.py` (real services via Testcontainers Cloud)
- Tests run automatically when you push to `feature/codex/*`.
- **No tests = PR rejection.**

### 4. Dependency Management
- **Update `requirements.txt` if you add new packages.**
- **Never pin to `latest`** — use specific versions: `package==1.2.3`
- **Avoid heavy dependencies** — consider impact on Docker image size.
- Run `pip freeze` to get exact versions of what you installed.

### 5. Code Quality Standards
- **Follow existing patterns** in the codebase (see examples below).
- **Use type hints** for all functions: `def my_func(x: str) -> dict:`
- **Add docstrings** to all functions and classes.
- **Keep functions small and focused** (max 50 lines per function).
- **Use async/await** for I/O operations (brainego is async-first).

---

## Project Architecture (What You're Working With)

### Services Overview

```
brainego (Next-Gen AI Model)
├── API Server (FastAPI, port 8000)
│   └── OpenAI-compatible chat completion API
│
├── Gateway Service (port 9000)
│   └── Request routing & orchestration
│
├── MCPJungle (port 9100)
│   └── MCP server integration & management
│
├── Learning Engine (port 8003)
│   └── Fine-tuning & adaptation via LoRA
│
├── Drift Monitor (port 8004)
│   └── Model performance tracking
│
└── Infrastructure
    ├── Redis (6379) - Cache & queues
    ├── PostgreSQL (5432) - Data storage
    ├── Qdrant (6333) - Vector embeddings
    ├── MinIO (9000/9001) - Object storage
    ├── Neo4j (7687) - Knowledge graphs
    └── Jaeger (6831/16686) - Distributed tracing
```

### Stack
- **Language:** Python 3.11
- **API Framework:** FastAPI
- **Web Server:** Uvicorn
- **Testing:** pytest, pytest-asyncio, testcontainers
- **ML/Vector DB:** sentence-transformers, qdrant-client
- **Memory:** mem0ai
- **Message Queue:** Redis + RQ
- **Database:** PostgreSQL
- **Observability:** OpenTelemetry, Jaeger

---

## Code Patterns You Must Follow

### Pattern 1: Adding a FastAPI Endpoint

**Location:** `api_server.py`

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import logging

logger = logging.getLogger(__name__)

class YourRequest(BaseModel):
    """Request model for your endpoint."""
    query: str = Field(..., description="User query")
    max_tokens: int = Field(default=100, ge=1, le=2000)

class YourResponse(BaseModel):
    """Response model for your endpoint."""
    result: str
    tokens_used: int

@app.post("/v1/your-feature", response_model=YourResponse)
async def your_endpoint(request: YourRequest) -> YourResponse:
    """
    Your endpoint description.
    
    This is a longer description of what the endpoint does.
    
    Args:
        request: The incoming request
        
    Returns:
        YourResponse with results
        
    Raises:
        HTTPException: If validation fails
    """
    try:
        # Your logic here
        result = await process_query(request.query)
        
        logger.info(f"Processed query: {request.query}")
        
        return YourResponse(
            result=result,
            tokens_used=estimate_tokens(result)
        )
    except Exception as e:
        logger.error(f"Error processing query: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

**Test it** (`tests/unit/test_your_endpoint.py`):

```python
import pytest
from httpx import AsyncClient
from unittest.mock import patch, AsyncMock

@pytest.mark.asyncio
async def test_your_endpoint_success():
    """Test happy path."""
    from api_server import app
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/v1/your-feature",
            json={"query": "test query"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "result" in data
        assert data["tokens_used"] > 0

@pytest.mark.asyncio
async def test_your_endpoint_validation_error():
    """Test invalid input."""
    from api_server import app
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/v1/your-feature",
            json={"query": ""}  # Invalid: empty query
        )
        
        assert response.status_code == 422  # Validation error
```

---

### Pattern 2: Adding a Service with Database Access

**Location:** `memory_service.py` or `rag_service.py`

```python
import redis.asyncio as redis
from qdrant_client.async_client import AsyncQdrantClient
import logging

logger = logging.getLogger(__name__)

class MemoryService:
    """Service for managing user memory."""
    
    def __init__(self, redis_url: str, qdrant_url: str):
        """
        Initialize service.
        
        Args:
            redis_url: Redis connection URL (e.g., redis://localhost:6379)
            qdrant_url: Qdrant server URL (e.g., http://localhost:6333)
        """
        self.redis_url = redis_url
        self.qdrant_url = qdrant_url
        self.redis_client: redis.Redis | None = None
        self.qdrant_client: AsyncQdrantClient | None = None
    
    async def connect(self) -> None:
        """Establish connections to services."""
        self.redis_client = await redis.from_url(self.redis_url, decode_responses=True)
        self.qdrant_client = AsyncQdrantClient(url=self.qdrant_url)
        logger.info("MemoryService connected to Redis and Qdrant")
    
    async def disconnect(self) -> None:
        """Close connections."""
        if self.redis_client:
            await self.redis_client.close()
        logger.info("MemoryService disconnected")
    
    async def store_memory(self, user_id: str, text: str) -> str:
        """
        Store user memory.
        
        Args:
            user_id: Unique user identifier
            text: Memory text to store
            
        Returns:
            Memory ID
        """
        if not self.redis_client or not self.qdrant_client:
            raise RuntimeError("Service not connected")
        
        try:
            # Store in cache
            memory_id = f"mem_{user_id}_{int(time.time())}"
            await self.redis_client.setex(
                f"memory:{memory_id}",
                3600,  # 1 hour TTL
                text
            )
            
            logger.info(f"Stored memory for user {user_id}")
            return memory_id
            
        except Exception as e:
            logger.error(f"Error storing memory: {e}")
            raise
```

**Test it** (`tests/integration/test_memory_service.py`):

```python
import pytest
from testcontainers.redis import RedisContainer
from memory_service import MemoryService

@pytest.fixture
def redis_service():
    """Testcontainers Cloud: Real Redis instance."""
    with RedisContainer() as container:
        yield container

@pytest.mark.asyncio
async def test_store_memory(redis_service):
    """Test storing memory with real Redis."""
    redis_url = redis_service.get_connection_url()
    
    service = MemoryService(
        redis_url=redis_url,
        qdrant_url="http://localhost:6333"  # Mock or real
    )
    
    await service.connect()
    
    try:
        memory_id = await service.store_memory(
            user_id="user_123",
            text="Important memory"
        )
        
        assert memory_id.startswith("mem_")
        assert len(memory_id) > 0
        
    finally:
        await service.disconnect()
```

---

### Pattern 3: Adding an MCP Integration

**Location:** `mcp_client.py`

```python
from mcp import ClientSession
from mcp.types import Tool
import logging

logger = logging.getLogger(__name__)

class MCPToolClient:
    """Client for calling MCP tools."""
    
    async def list_tools(self) -> list[dict]:
        """
        List all available MCP tools.
        
        Returns:
            List of tool definitions
        """
        try:
            async with ClientSession() as session:
                tools = await session.list_tools()
                logger.info(f"Found {len(tools)} tools")
                return [
                    {"name": t.name, "description": t.description}
                    for t in tools
                ]
        except Exception as e:
            logger.error(f"Error listing tools: {e}")
            raise
    
    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """
        Call an MCP tool.
        
        Args:
            tool_name: Name of the tool
            arguments: Tool arguments
            
        Returns:
            Tool result
        """
        try:
            async with ClientSession() as session:
                result = await session.call_tool(
                    name=tool_name,
                    arguments=arguments
                )
                logger.info(f"Called tool {tool_name}")
                return result
        except Exception as e:
            logger.error(f"Error calling tool {tool_name}: {e}")
            raise
```

---

## Testing Requirements

### Unit Tests (Fast, Mocked)

✅ **DO:**
- Mock Redis, PostgreSQL, Qdrant
- Test business logic
- Test error handling
- Keep tests under 1 second each

❌ **DON'T:**
- Make real HTTP calls
- Connect to real databases
- Start containers
- Use Testcontainers

**Location:** `tests/unit/test_*.py`

```python
@pytest.mark.unit
@pytest.mark.asyncio
async def test_business_logic(mock_redis_client):
    """Test with mocked dependencies."""
    # Use fixtures from conftest.py
    pass
```

### Integration Tests (Thorough, Real Services)

✅ **DO:**
- Use Testcontainers for Redis, PostgreSQL, etc.
- Test real service interactions
- Test end-to-end flows
- Allow 30-60 second runtime

❌ **DON'T:**
- Assume Docker is available locally
- Run locally without Testcontainers Cloud token
- Mock real services

**Location:** `tests/integration/test_*.py`

```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_with_real_services(redis_service):
    """Test with Testcontainers Cloud."""
    redis_url = redis_service.get_connection_url()
    # Use real Redis instance
    pass
```

---

## Workflow: Step-by-Step

### When You Generate Code

1. **Create feature branch locally:**
   ```bash
   git checkout -b feature/codex/your-feature-name
   ```

2. **Generate code:**
   - Add new endpoint/service/test
   - Follow patterns above
   - Include docstrings & type hints
   - Update `requirements.txt` if needed

3. **Create tests:**
   - Unit tests in `tests/unit/`
   - Integration tests in `tests/integration/` (if using services)
   - Both must pass locally

4. **Push to GitHub:**
   ```bash
   git add .
   git commit -m "Add your-feature: brief description"
   git push origin feature/codex/your-feature-name
   ```

5. **GitHub Actions triggers:**
   - ✅ Builds images via Docker Build Cloud
   - ✅ Runs unit tests
   - ✅ Runs integration tests (Testcontainers Cloud)
   - ✅ Security scan
   - ✅ Posts results to PR

6. **Review results:**
   - PR comments show test results
   - All checks must pass
   - Request review from maintainers

---

## Common Tasks & Examples

### Task: Add a RAG Search Endpoint

```python
# In api_server.py

from sentence_transformers import SentenceTransformer

@app.post("/v1/rag/search")
async def rag_search(request: RAGSearchRequest) -> RAGSearchResponse:
    """
    Search knowledge base using RAG.
    
    Uses embeddings to find relevant documents.
    """
    embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
    query_embedding = embedding_model.encode(request.query).tolist()
    
    results = await qdrant_client.search(
        collection_name="brainego_knowledge",
        query_vector=query_embedding,
        limit=request.top_k
    )
    
    return RAGSearchResponse(results=results)
```

**Test it:**
```python
# tests/integration/test_rag_search.py

@pytest.mark.integration
async def test_rag_search_endpoint():
    """Integration test with real Qdrant."""
    # Uses Testcontainers Cloud Qdrant instance
    pass
```

---

### Task: Add a Background Job (Learning Engine)

```python
# In learning_engine.py

import rq
from redis import Redis

def submit_training_job(user_id: str, config: dict) -> str:
    """
    Submit a training job to the queue.
    
    Args:
        user_id: User ID
        config: Training configuration
        
    Returns:
        Job ID
    """
    redis_conn = Redis(host="redis", port=6379)
    q = rq.Queue(connection=redis_conn)
    
    job = q.enqueue(
        train_model,
        user_id=user_id,
        config=config,
        job_timeout=3600  # 1 hour
    )
    
    logger.info(f"Submitted training job: {job.id}")
    return job.id

async def train_model(user_id: str, config: dict) -> dict:
    """
    Train model (runs in background worker).
    
    Args:
        user_id: User ID
        config: Training configuration
        
    Returns:
        Training result
    """
    try:
        # LoRA training logic
        result = await run_lora_training(user_id, config)
        return result
    except Exception as e:
        logger.error(f"Training failed: {e}")
        raise
```

---

### Task: Add Monitoring/Observability

```python
# In observability.py

from opentelemetry import trace, metrics

tracer = trace.get_tracer(__name__)
meter = metrics.get_meter(__name__)

# Metrics
request_counter = meter.create_counter("requests_total")
latency_histogram = meter.create_histogram("request_latency_ms")

@app.middleware("http")
async def add_tracing(request: Request, call_next):
    """Add tracing to all requests."""
    with tracer.start_as_current_span(f"{request.method} {request.url.path}"):
        request_counter.add(1, {"method": request.method})
        
        start_time = time.time()
        response = await call_next(request)
        latency_ms = (time.time() - start_time) * 1000
        
        latency_histogram.record(latency_ms, {"endpoint": request.url.path})
        return response
```

---

## Code Review Checklist (For PRs)

Before you submit a PR, **verify:**

- [ ] Code follows patterns above
- [ ] All functions have type hints
- [ ] All functions have docstrings
- [ ] Unit tests exist and pass
- [ ] Integration tests exist (if using services)
- [ ] No hardcoded credentials
- [ ] `requirements.txt` updated (if adding dependencies)
- [ ] Branch name is `feature/codex/*`
- [ ] Commit message is clear
- [ ] No large files (>100MB)
- [ ] No debug print statements

---

## Troubleshooting

### "Local tests fail but GitHub Actions passes"
**Reason:** You're missing a service locally (Redis, PostgreSQL, etc.).  
**Solution:** Use `@pytest.mark.integration` and skip locally. Tests run in CI.

### "Git says I need to pull before pushing"
**Solution:**
```bash
git pull origin main
git rebase main
git push origin feature/codex/your-feature
```

### "I added a new import but tests fail"
**Solution:**
```bash
pip install <package-name>
pip freeze | grep <package-name>  # Get exact version
echo "<package-name>==X.Y.Z" >> requirements.txt
```

### "Testcontainers timeout in CI"
**Fix:** GitHub Actions automatically sets `TESTCONTAINERS_CLOUD_TOKEN`.  
If tests timeout, check workflow logs under "Run integration tests".

### "I don't have permission to merge"
**Normal behavior.** Maintainers review and merge PRs.  
After review + checks pass, they'll merge for you.

---

## Resources

| Topic | Link |
|-------|------|
| FastAPI | https://fastapi.tiangolo.com/ |
| Pydantic | https://docs.pydantic.dev/ |
| pytest | https://docs.pytest.org/ |
| Testcontainers | https://testcontainers.com/ |
| Redis Python | https://redis-py.readthedocs.io/ |
| Qdrant | https://qdrant.tech/documentation/ |
| OpenTelemetry | https://opentelemetry.io/ |

---

## Final Rules

1. **Never assume Docker exists** — it doesn't in Codex Cloud
2. **Always test** — unit + integration
3. **Always document** — docstrings & type hints
4. **Always follow patterns** — consistency matters
5. **Always push to `feature/codex/*`** — never `main`
6. **Always update `requirements.txt`** — if you add packages
7. **Always wait for CI** — before merging

---

## Questions?

If you're unsure:
- Check `CODEX_INSTRUCTIONS.md` in the repo
- Look at existing code for patterns
- Ask maintainers in PR comments
- Read the docs linked above

**You're ready. Start generating! 🚀**
