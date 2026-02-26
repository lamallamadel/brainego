# GitHub Secrets Setup for Codex CI/CD

## Required Secrets

Add these secrets to your GitHub repository settings (`Settings → Secrets and variables → Actions`):

### 1. Docker Build Cloud Token
**Secret Name**: `DOCKER_BUILD_CLOUD_TOKEN`

```bash
# Get from Docker Dashboard:
# https://app.docker.com/settings/tokens
# Create a Personal Access Token with build permissions
```

**In workflow**: Uses buildx with cloud builder

### 2. Testcontainers Cloud Token  
**Secret Name**: `TESTCONTAINERS_CLOUD_TOKEN`

```bash
# Get from:
# https://cloud.testcontainers.com/
# Settings → API Tokens → Create Token
```

**In workflow**: Enables cloud Docker daemon for integration tests

### 3. GitHub Container Registry (GHCR)
- Uses `GITHUB_TOKEN` automatically (no setup needed)
- Requires `packages: write` permission in workflow

---

## Environment Variables (Optional)

Add to `.env.github-actions` in your repo:

```bash
# Build concurrency
BUILDX_PARALLEL: 4

# Caching strategy
BUILDX_CACHE_MODE: max

# Test configuration
PYTEST_TIMEOUT: 300
TESTCONTAINERS_TIMEOUT: 60
```

---

## Docker Build Cloud Setup

### 1. Enable Docker Build Cloud

```bash
# Login locally first (on your dev machine)
docker login

# Create/select a builder
docker buildx create --name docker-cloud --driver docker-container

# If you have Build Cloud subscription:
docker buildx create --name cloud-builder --platform linux/amd64,linux/arm64 \
  --driver docker-container \
  --driver-opt image=moby/buildkit:latest

# Set as default
docker buildx use cloud-builder
```

### 2. In GitHub Actions

The workflow automatically:
- ✅ Sets up buildx with cloud driver
- ✅ Uses `docker/build-push-action@v6`
- ✅ Caches layers in registry
- ✅ Pushes to GHCR

---

## Testcontainers Cloud Setup

### 1. Get Token

```bash
# Visit: https://cloud.testcontainers.com/
# Settings → API Tokens
# Create a token and copy it
```

### 2. Add to GitHub Secrets

```
TESTCONTAINERS_CLOUD_TOKEN: <your-token>
```

### 3. How It Works in CI

```bash
# Workflow installs agent
curl -fsSL https://testcontainers.cloud/install.sh | bash
./testcontainers-cloud-agent &

# Tests automatically connect to cloud Docker daemon
# No docker-in-docker needed!
```

---

## Example: Codex-Generated Test File

When Codex creates a test, it should use this structure:

```python
# tests/integration/test_api_with_containers.py
import pytest
from testcontainers.redis import RedisContainer
from testcontainers.postgres import PostgresContainer
from httpx import AsyncClient

@pytest.fixture(scope="module")
def redis_container():
    """Testcontainers Cloud: Runs Redis in the cloud"""
    with RedisContainer() as redis:
        yield redis

@pytest.fixture(scope="module")
def postgres_container():
    """Testcontainers Cloud: Runs Postgres in the cloud"""
    with PostgresContainer(
        image="postgres:15-alpine",
        dbname="brainego_test",
        username="test",
        password="test"
    ) as postgres:
        yield postgres

@pytest.mark.asyncio
async def test_api_with_redis(redis_container):
    """Test API with cloud Redis instance"""
    redis_url = redis_container.get_connection_url()
    
    # Your test logic
    client = AsyncClient(app=app, base_url="http://test")
    response = await client.get("/health")
    
    assert response.status_code == 200
```

---

## Multi-Architecture Builds (Optional)

To build for ARM64 (Apple Silicon) + AMD64:

```yaml
# In workflow: build-and-push step
platforms: linux/amd64,linux/arm64

# Full example:
- name: Build multi-arch image
  uses: docker/build-push-action@v6
  with:
    context: .
    file: ./Dockerfile.api
    platforms: linux/amd64,linux/arm64
    push: true
    tags: ghcr.io/${{ github.repository }}/api:latest
```

---

## Debugging Failed Builds

### Check Build Logs
```bash
docker buildx du
docker buildx logs

# Or in GitHub: Actions → Workflow Run → Build and push step → View Logs
```

### Common Issues

1. **Rate limiting on image pulls**
   → Use specific version tags in FROM
   → Increase cache retention

2. **Testcontainers timeout**
   → Increase `TESTCONTAINERS_TIMEOUT` env var
   → Check cloud agent token is valid

3. **GHCR auth fails**
   → Ensure `packages: write` permission in job
   → Verify secrets are set correctly

---

## Workflow File Location

```
brainego/
├── .github/
│   └── workflows/
│       └── codex-build.yml  ← This is your CI/CD pipeline
├── tests/
│   ├── unit/
│   ├── integration/
│   └── conftest.py
├── Dockerfile.api
├── Dockerfile.gateway
├── Dockerfile.mcpjungle
└── requirements.txt
```

---

## How Codex Uses This

### Step 1: Codex Creates Code
```bash
# Codex on feature/codex/new-feature branch
feature/codex/new-feature
├── api_server.py (modified)
├── tests/integration/test_new_feature.py (created)
└── requirements.txt (updated)
```

### Step 2: Codex Pushes
```bash
git push origin feature/codex/new-feature
```

### Step 3: GitHub Actions Triggers
- Automatically runs `.github/workflows/codex-build.yml`
- Builds 3 images (API, gateway, MCPJungle) via Docker Build Cloud
- Runs tests with Testcontainers Cloud
- Publishes results back to the PR

### Step 4: Codex Receives Feedback
- PR comments with test results
- Build status visible in GitHub
- Artifacts available for download

---

## Quick Start Checklist

- [ ] Add `TESTCONTAINERS_CLOUD_TOKEN` to GitHub Secrets
- [ ] Copy `.github/workflows/codex-build.yml` to your repo
- [ ] Create `tests/` directory with unit and integration folders
- [ ] Update `requirements.txt` with test dependencies:
  ```
  pytest>=7.4.0
  pytest-asyncio>=0.21.0
  pytest-cov>=4.1.0
  testcontainers>=3.7.0
  ```
- [ ] Create test example file in `tests/integration/`
- [ ] Push to a `feature/codex/test` branch to verify workflow runs

---

## Monitoring & Observability

### View Build Status
```
GitHub → Actions → Codex Feature Build & Test → Latest Run
```

### Docker Build Cloud Console
```
https://dashboard.docker.com/build
```

### Testcontainers Cloud Console
```
https://cloud.testcontainers.com/
```

---

## Scaling: Multi-Arch Builds

Your current buildx shows:

```
desktop-linux    docker    linux/amd64 (+4)
```

To enable ARM64 builds (for Apple Silicon / AWS Graviton):

```yaml
platforms: linux/amd64,linux/arm64
cache-from: type=registry,ref=ghcr.io/.../buildcache
```

Docker Build Cloud will handle cross-compilation automatically.

---

## Next Steps

1. **Set GitHub Secrets** (2 min)
2. **Push workflow file** (1 min)
3. **Create test example** (5 min)
4. **Push to feature/codex/test** (verify it works)
5. **Give Codex instructions** (see CODEX_INSTRUCTIONS.md)

Let me know if you need help with any step!
