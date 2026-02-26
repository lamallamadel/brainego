# Instructions for Codex: Using Docker Build Cloud + Testcontainers Cloud

This guide tells Codex how to generate code and tests that leverage Docker Build Cloud and Testcontainers Cloud.

## Context for Codex

You are working in the **brainego** project—a next-generation AI model with microservices architecture:

- **API Server** (FastAPI, port 8000): OpenAI-compatible chat completion API
- **Gateway Service** (port 9000): Request routing and orchestration  
- **MCPJungle** (port 9100): MCP server integration and management
- **Infrastructure**: Redis, PostgreSQL, Qdrant, MinIO, Neo4j

Your changes should:
1. ✅ Follow existing patterns (see `api_server.py`, `gateway_service.py`, etc.)
2. ✅ Include **unit tests** in `tests/unit/`
3. ✅ Include **integration tests** in `tests/integration/`
4. ✅ Use **Testcontainers** for any database/service dependencies
5. ✅ Update `requirements.txt` if adding dependencies

---

## Workflow Overview

```
You (Codex) Create Code
    ↓
Push to feature/codex/* branch
    ↓
GitHub Actions Triggers
    ├── Build images via Docker Build Cloud
    ├── Run unit tests
    ├── Run integration tests (Testcontainers Cloud)
    └── Security scan
    ↓
Results in PR
```

---

## Rules for Generated Code

### 1. API Changes

If modifying `api_server.py`:

```python
# ✅ GOOD: New endpoint with type hints
@app.post("/v1/feature-name")
async def feature_endpoint(request: FeatureRequest) -> FeatureResponse:
    """
    Your endpoint description.
    
    Args:
        request: The feature request
        
    Returns:
        FeatureResponse with results
    """
    # Implementation
    pass
```

### 2. Unit Tests

Create in `tests/unit/test_*.py`:

```python
import pytest
from unittest.mock import patch, AsyncMock
from api_server import your_function

@pytest.mark.asyncio
async def test_your_function_success():
    """Test the happy path"""
    result = await your_function()
    assert result is not None

@pytest.mark.asyncio  
async def test_your_function_error_handling():
    """Test error handling"""
    with pytest.raises(ValueError):
        await your_function()
```

### 3. Integration Tests (Using Testcontainers Cloud)

Create in `tests/integration/test_*.py`:

```python
import pytest
from testcontainers.redis import RedisContainer
from testcontainers.postgres import PostgresContainer
from httpx import AsyncClient

@pytest.fixture(scope="module")
def redis_service():
    """Spin up Redis in Testcontainers Cloud (not local Docker)"""
    with RedisContainer() as redis:
        yield redis

@pytest.fixture(scope="module")
def postgres_service():
    """Spin up Postgres in Testcontainers Cloud"""
    with PostgresContainer(
        image="postgres:15-alpine",
        dbname="brainego_test"
    ) as postgres:
        yield postgres

@pytest.mark.asyncio
async def test_api_with_services(redis_service, postgres_service):
    """Test API against real services (running in cloud)"""
    # Get connection URLs from containers
    redis_url = redis_service.get_connection_url()
    db_url = postgres_service.get_connection_url()
    
    # Initialize app with service URLs
    app = create_app(redis_url=redis_url, db_url=db_url)
    
    # Test the integration
    client = AsyncClient(app=app, base_url="http://test")
    response = await client.post("/v1/feature", json={"data": "test"})
    
    assert response.status_code == 200
```

### 4. Dependencies

If you add new packages, update `requirements.txt`:

```bash
# Example: Adding a new library
pip install new_library

# Freeze versions
pip freeze > requirements-new.txt

# Merge into requirements.txt
# Keep existing, add new ones at the end
```

---

## Common Patterns for brainego

### Pattern 1: Adding a RAG Endpoint

```python
# In api_server.py

from qdrant_client.async_client import AsyncQdrantClient
from sentence_transformers import SentenceTransformer

class RAGRequest(BaseModel):
    query: str
    top_k: int = 5

class RAGResponse(BaseModel):
    results: list[dict]
    
@app.post("/v1/rag/search")
async def rag_search(request: RAGRequest) -> RAGResponse:
    """Search knowledge base using RAG"""
    embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
    query_embedding = embedding_model.encode(request.query).tolist()
    
    qdrant_client = AsyncQdrantClient(url="http://qdrant:6333")
    results = await qdrant_client.search(
        collection_name="brainego_knowledge",
        query_vector=query_embedding,
        limit=request.top_k
    )
    
    return RAGResponse(results=[...])
```

**Test it**:
```python
# tests/integration/test_rag_search.py

@pytest.fixture
def qdrant_service():
    """Qdrant runs in Testcontainers Cloud"""
    # Note: Testcontainers has QdrantContainer (if available)
    # Otherwise, use Docker image directly
    pass

@pytest.mark.asyncio
async def test_rag_search_endpoint(qdrant_service):
    """Test RAG endpoint"""
    # Setup test data
    # Call endpoint
    # Assert results
    pass
```

### Pattern 2: Adding a Memory Feature

```python
# In memory_service.py

from mem0ai import MemoryClient
import redis

async def store_interaction(user_id: str, interaction: dict):
    """Store conversation in memory"""
    mem0_client = MemoryClient()
    redis_client = redis.Redis(host="redis", port=6379)
    
    # Store in Mem0
    memory_id = await mem0_client.add(
        messages=[interaction],
        user_id=user_id
    )
    
    # Cache in Redis
    redis_client.setex(
        f"memory:{user_id}",
        3600,  # 1 hour
        memory_id
    )
    
    return memory_id
```

**Test it**:
```python
# tests/integration/test_memory_service.py

@pytest.fixture
def redis_service():
    with RedisContainer() as redis:
        yield redis

@pytest.mark.asyncio
async def test_store_interaction(redis_service):
    redis_url = redis_service.get_connection_url()
    # Test the store_interaction function
    pass
```

### Pattern 3: Adding an MCP Integration

```python
# In mcp_client.py (MCP toolkit integration)

from mcp import ClientSession
from mcp.types import Tool

async def call_mcp_tool(tool_name: str, arguments: dict):
    """Call an MCP tool"""
    async with ClientSession() as session:
        # List available tools
        tools = await session.list_tools()
        
        # Find and call the tool
        for tool in tools:
            if tool.name == tool_name:
                result = await session.call_tool(
                    name=tool_name,
                    arguments=arguments
                )
                return result
```

---

## Submission Checklist

Before pushing a feature branch:

- [ ] Code follows existing patterns in the codebase
- [ ] Added/updated unit tests in `tests/unit/`
- [ ] Added/updated integration tests in `tests/integration/`
- [ ] Used Testcontainers for any services (Redis, Postgres, etc.)
- [ ] Updated `requirements.txt` if adding dependencies
- [ ] Updated docstrings with clear descriptions
- [ ] No hardcoded credentials (use environment variables)
- [ ] Follows async/await patterns (FastAPI uses async)

---

## Expected GitHub Actions Results

When you push to `feature/codex/*`:

**GitHub Actions will**:
1. ✅ Build 3 Docker images (API, gateway, MCPJungle) via Docker Build Cloud
2. ✅ Push images to GHCR: `ghcr.io/yourusername/brainego/api:sha`
3. ✅ Run unit tests (local, fast)
4. ✅ Run integration tests using Testcontainers Cloud (real services, no local Docker)
5. ✅ Security scan with Trivy
6. ✅ Post results back to the PR

**Example PR comment**:
```
✅ Build Successful
- api:abc123def456 pushed
- gateway:abc123def456 pushed  
- mcpjungle:abc123def456 pushed

✅ Tests Passed
- 42 unit tests passed (2.3s)
- 8 integration tests passed (45s)

✅ Security: No critical vulnerabilities
```

---

## Example: Complete Feature Branch Flow

### You Create Feature

```bash
# You generate code on feature/codex/rag-search
feature/codex/rag-search
├── api_server.py (added /v1/rag/search endpoint)
├── tests/integration/test_rag_search.py (new)
├── tests/unit/test_rag_utils.py (new)
└── requirements.txt (added: qdrant-client if needed)
```

### You Push Code

```bash
git add .
git commit -m "Add RAG search endpoint"
git push origin feature/codex/rag-search
```

### GitHub Actions Automatically

```
Workflow: codex-build.yml starts
│
├─ build-and-test
│  ├─ Build API image → Docker Build Cloud
│  ├─ Build gateway image → Docker Build Cloud
│  ├─ Build MCPJungle image → Docker Build Cloud
│  ├─ Run pytest (unit tests)
│  ├─ Run pytest (integration tests with Testcontainers Cloud)
│  └─ ✅ All tests passed
│
├─ security-scan  
│  └─ ✅ Trivy scan passed
│
└─ PR auto-commented with results
```

### PR Review

Maintainer sees:
- ✅ All builds passed
- ✅ All tests passed
- ✅ Security approved
- Can merge with confidence

---

## Troubleshooting

### "Testcontainers Cloud timeout"
**Fix**: Increase timeout in workflow
```yaml
env:
  TESTCONTAINERS_TIMEOUT: 120  # 2 minutes
```

### "Image pull rate limited"
**Fix**: Use specific version tags
```python
# Instead of: FROM python:3.11-slim
# Use: FROM python:3.11.8-slim
```

### "Test hangs"
**Fix**: Add pytest timeout
```python
@pytest.mark.timeout(30)  # 30-second timeout
async def test_something():
    pass
```

---

## Key Takeaway for Codex

When you generate code:

1. **Always include tests** (unit + integration)
2. **Use Testcontainers** for any services (Redis, Postgres, etc.)
3. **Push to `feature/codex/*`** branch
4. **GitHub Actions handles the rest** (builds, tests, security)
5. **You get feedback** in the PR within 5-10 minutes

The CI/CD pipeline is fully automated and ready to use. Just follow the patterns above, and your code will be validated in the cloud! 🚀

---

## Still Need Help?

See:
- `GITHUB_ACTIONS_SETUP.md` - Technical setup details
- `ARCHITECTURE.md` - Project architecture overview
- `requirements.txt` - Available dependencies
- `.github/workflows/codex-build.yml` - The actual workflow file
