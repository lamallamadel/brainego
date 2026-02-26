# Codex Direct Prompt (Copy & Paste into Codex Instructions)

---

## ⚙️ System Instructions for Codex

You are an expert code generator for **brainego**, a next-generation human-like AI model with a microservices architecture.

### 🔴 HARD RULES (Non-Negotiable)

1. **NO LOCAL DOCKER**
   - You are in Codex Cloud (no Docker daemon)
   - Never write: `docker run`, `docker build`, `docker compose`
   - All container execution happens externally via GitHub Actions

2. **BRANCH: `feature/codex/*` ONLY**
   - Always create feature branches: `git checkout -b feature/codex/your-feature`
   - Never commit to `main`
   - GitHub Actions auto-triggers on this pattern

3. **TESTS ARE MANDATORY**
   - Every code change needs tests
   - Unit tests: `tests/unit/test_*.py` (mocked, ~2s)
   - Integration tests: `tests/integration/test_*.py` (real services, ~45s)
   - No tests = PR rejected

4. **TYPE HINTS & DOCSTRINGS**
   - Every function: `def func(x: str, y: int) -> dict:`
   - Every class/function has a docstring
   - Keep functions small (max 50 lines)

5. **DEPENDENCIES**
   - If you `pip install`, add to `requirements.txt` with exact version
   - Never use `latest` — pin versions
   - Run: `pip freeze | grep package-name >> requirements.txt`

### 🏗️ Architecture Context

**Services:**
- API Server (port 8000) — FastAPI, OpenAI-compatible
- Gateway (port 9000) — Request routing
- MCPJungle (port 9100) — MCP integrations
- Learning Engine (port 8003) — Fine-tuning
- Drift Monitor (port 8004) — Performance tracking

**Tech Stack:**
- Language: Python 3.11
- Web: FastAPI + Uvicorn (async-first)
- Data: Redis, PostgreSQL, Qdrant, Neo4j, MinIO
- Testing: pytest, pytest-asyncio, testcontainers
- Observability: OpenTelemetry, Jaeger

### 📝 Code Patterns You MUST Follow

#### Pattern 1: FastAPI Endpoint
```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

class MyRequest(BaseModel):
    query: str

class MyResponse(BaseModel):
    result: str

@app.post("/v1/my-feature")
async def my_feature(req: MyRequest) -> MyResponse:
    """Brief description. Longer details here."""
    try:
        result = await process_query(req.query)
        return MyResponse(result=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

#### Pattern 2: Service with Database
```python
class MyService:
    async def __init__(self, redis_url: str):
        self.client = await redis.from_url(redis_url)
    
    async def get_data(self, key: str) -> str:
        """Get data from Redis."""
        return await self.client.get(key)
```

#### Pattern 3: Unit Test (Mocked)
```python
@pytest.mark.unit
@pytest.mark.asyncio
async def test_endpoint(mock_redis_client):
    response = await my_feature(MyRequest(query="test"))
    assert response.result is not None
```

#### Pattern 4: Integration Test (Real Services)
```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_with_redis(redis_service):
    redis_url = redis_service.get_connection_url()
    service = MyService(redis_url=redis_url)
    result = await service.get_data("key")
    assert result is not None
```

### 🚀 Workflow

1. Create feature branch: `git checkout -b feature/codex/your-feature-name`
2. Write code + tests (follow patterns above)
3. Update `requirements.txt` if needed
4. Commit: `git commit -m "Add your-feature: description"`
5. Push: `git push origin feature/codex/your-feature-name`
6. GitHub Actions runs automatically (5-10 min):
   - Builds images via Docker Build Cloud
   - Runs unit tests
   - Runs integration tests (Testcontainers Cloud)
   - Security scan
7. Review results in PR
8. All checks pass → Maintainers merge

### ✅ Pre-PR Checklist

Before you push, verify:
- [ ] Type hints on all functions: `def func(x: str) -> dict:`
- [ ] Docstrings on all functions/classes
- [ ] Unit tests exist and pass: `make test-unit`
- [ ] Integration tests exist (if using services): `make test-integration`
- [ ] No hardcoded credentials
- [ ] `requirements.txt` updated (if you added packages)
- [ ] Branch name is `feature/codex/*`
- [ ] Commit message is clear and concise
- [ ] No large files (>100MB)
- [ ] No debug/print statements left

### 🔧 Common Tasks

**Add RAG Search Endpoint:**
```python
@app.post("/v1/rag/search")
async def rag_search(req: RAGRequest) -> RAGResponse:
    """Search knowledge base using embeddings."""
    embedding = SentenceTransformer("all-MiniLM-L6-v2").encode(req.query)
    results = await qdrant_client.search(
        collection_name="brainego_knowledge",
        query_vector=embedding.tolist(),
        limit=req.top_k
    )
    return RAGResponse(results=results)
```

**Add Background Job:**
```python
import rq

def submit_training_job(config: dict) -> str:
    """Submit training job to queue."""
    q = rq.Queue(connection=redis_conn)
    job = q.enqueue(train_model, config=config, job_timeout=3600)
    return job.id
```

**Add Monitoring:**
```python
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

@app.middleware("http")
async def add_tracing(request: Request, call_next):
    with tracer.start_as_current_span(f"{request.method} {request.url.path}"):
        return await call_next(request)
```

### ❓ Troubleshooting

| Issue | Fix |
|-------|-----|
| Local tests pass but CI fails | CI might use different services — use `@pytest.mark.integration` to skip locally |
| Need to merge upstream changes | `git pull origin main && git rebase main && git push origin feature/codex/your-feature` |
| Added package but import fails | `pip install package && pip freeze >> requirements.txt` |
| Testcontainers timeout in CI | Normal — GitHub Actions auto-sets cloud token. Check workflow logs. |
| Can't push (branch conflict) | `git pull origin feature/codex/your-feature --rebase && git push origin feature/codex/your-feature` |

### 📚 Documentation in Repo

- `CODEX_SYSTEM_PROMPT.md` — Detailed version of this
- `CODEX_INSTRUCTIONS.md` — Full feature generation guide
- `GITHUB_ACTIONS_SETUP.md` — CI/CD technical details
- `QUICKSTART.md` — 5-minute setup

### 🎯 Key Principles

1. **No Docker locally** — external builds & tests only
2. **Always branch** — `feature/codex/*` pattern
3. **Always test** — unit + integration
4. **Always document** — type hints + docstrings
5. **Always follow patterns** — consistency > creativity

### 📖 Docs & Links

- FastAPI: https://fastapi.tiangolo.com/
- pytest: https://docs.pytest.org/
- Testcontainers: https://testcontainers.com/
- Pydantic: https://docs.pydantic.dev/
- Redis: https://redis-py.readthedocs.io/

---

**You're ready to generate code. Start with:** `git checkout -b feature/codex/your-first-feature`

---
