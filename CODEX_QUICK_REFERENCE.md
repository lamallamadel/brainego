# Codex Quick Reference Card

**Print or bookmark this. Share with your team.**

---

## The 5 Hard Rules

| # | Rule | DO ✅ | DON'T ❌ |
|---|------|--------|----------|
| 1 | **No Docker** | Tests run in GitHub Actions | `docker run`, `docker build`, `docker compose` |
| 2 | **Branch Pattern** | `feature/codex/your-feature` | Push to `main` directly |
| 3 | **Tests** | Unit + Integration tests | Ship code without tests |
| 4 | **Type Hints** | `def func(x: str) -> dict:` | Functions without types |
| 5 | **Dependencies** | Update `requirements.txt` | Use `latest` version |

---

## Workflow in 4 Steps

```
Step 1: Create branch
$ git checkout -b feature/codex/your-feature-name

Step 2: Write code + tests
  - Add endpoint to api_server.py
  - Add unit tests to tests/unit/
  - Add integration tests to tests/integration/
  - Update requirements.txt (if needed)

Step 3: Commit and push
$ git add .
$ git commit -m "Add your-feature: description"
$ git push origin feature/codex/your-feature-name

Step 4: GitHub Actions runs automatically
  ✅ Builds images (Docker Build Cloud)
  ✅ Runs unit tests
  ✅ Runs integration tests (Testcontainers Cloud)
  ✅ Security scan
  ✅ Results in PR (5-10 min)
```

---

## Code Patterns

### FastAPI Endpoint
```python
@app.post("/v1/endpoint-name")
async def endpoint_name(req: RequestModel) -> ResponseModel:
    """One-line description."""
    result = await process(req.query)
    return ResponseModel(result=result)
```

### Service with Database
```python
class MyService:
    async def __init__(self, redis_url: str):
        self.client = await redis.from_url(redis_url)
    
    async def get_data(self, key: str) -> str:
        """Get data from Redis."""
        return await self.client.get(key)
```

### Unit Test (Mocked)
```python
@pytest.mark.unit
async def test_endpoint(mock_redis_client):
    response = await endpoint_name(RequestModel(...))
    assert response is not None
```

### Integration Test (Real Services)
```python
@pytest.mark.integration
async def test_with_redis(redis_service):
    redis_url = redis_service.get_connection_url()
    service = MyService(redis_url=redis_url)
    result = await service.get_data("key")
    assert result is not None
```

---

## File Checklist

When you generate code, include:

- [ ] Type hints: `def func(x: str) -> dict:`
- [ ] Docstring: `"""Description and details."""`
- [ ] Unit tests: `tests/unit/test_*.py`
- [ ] Integration tests (if using services): `tests/integration/test_*.py`
- [ ] Updated `requirements.txt` (if adding packages)
- [ ] No hardcoded secrets
- [ ] Branch: `feature/codex/*`
- [ ] Clear commit message

---

## Project Services

```
API Server (8000)      → FastAPI, OpenAI-compatible
Gateway (9000)         → Request routing
MCPJungle (9100)       → MCP integrations
Learning Engine (8003) → LoRA fine-tuning
Drift Monitor (8004)   → Performance tracking

Infrastructure:
  Redis (6379)      → Cache & queues
  PostgreSQL (5432) → Database
  Qdrant (6333)     → Vector embeddings
  Neo4j (7687)      → Knowledge graphs
```

---

## Stack

```
Language:     Python 3.11
Web:          FastAPI + Uvicorn
Testing:      pytest + Testcontainers
Data:         Redis, PostgreSQL, Qdrant
Monitoring:   OpenTelemetry + Jaeger
```

---

## Useful Commands

```bash
# Testing
make test-unit                 # Run unit tests locally
make test-integration          # Run integration tests
make test-all                  # Run all tests

# Git
git checkout -b feature/codex/name    # Create feature branch
git push origin feature/codex/name    # Push and trigger CI/CD

# Dependencies
pip install package
pip freeze | grep package >> requirements.txt

# Help
make codex-help                # Show Codex instructions
cat CODEX_INSTRUCTIONS.md      # Read project rules
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Tests fail locally | May use Testcontainers Cloud in CI (normal) |
| Need to pull upstream | `git pull origin main && git rebase main` |
| Added import, tests fail | `pip install package && pip freeze >> requirements.txt` |
| Testcontainers timeout | Check workflow logs; GitHub Actions auto-sets token |
| Can't push (conflict) | `git pull --rebase && git push` |

---

## Documentation Links

| File | Purpose | Time |
|------|---------|------|
| `CODEX_INSTRUCTIONS.md` | Project rules (read first) | 15 min |
| `CODEX_DIRECT_PROMPT.md` | System prompt (reference) | 10 min |
| `CODEX_SETUP_GUIDE.md` | Configuration (setup) | 10 min |
| `GITHUB_ACTIONS_SETUP.md` | CI/CD details | 10 min |

---

## Quick Test

Ask Codex these to verify setup:

1. **"Create a feature branch for adding a new endpoint"**
   → Should mention: `feature/codex/...`

2. **"Generate an endpoint with tests"**
   → Should generate: Unit + integration tests

3. **"Add a new package. What else do I need to do?"**
   → Should mention: Update `requirements.txt`

---

## One-Liner Summary

**No Docker locally. Always `feature/codex/*`. Tests mandatory. Type hints always. Update dependencies.**

---

## Keep This Handy

**Bookmark or print this card and keep it visible while working with Codex.**

Questions? See `CODEX_INSTRUCTIONS.md` or `CODEX_SETUP_GUIDE.md`

---

**Happy coding! 🚀**
