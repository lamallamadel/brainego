# Production Deployment Smoke Test Suite

## Overview

The `prod_smoke_tests.py` script provides a comprehensive smoke test suite for validating production deployments. It executes synthetic transactions against production endpoints and provides one-click rollback capability if tests fail.

## Features

### 1. Authentication & Security Validation
- **Kong Authentication Enforcement**: Verifies that unauthenticated requests are properly rejected (401)
- **Kong Rate Limiting**: Validates that rate limiting is active via headers or Kong Admin API

### 2. Core API Endpoint Testing
- **Chat Completion with Workspace Quota**: Tests `/v1/chat/completions` with authenticated requests and verifies workspace quota tracking
- **RAG Query with Citation Validation**: Tests `/v1/rag/query` and validates that citations are properly returned
- **MCP Tools RBAC Enforcement**: Tests `/internal/mcp/tools/call` and verifies RBAC is enforced

### 3. Monitoring & Metrics
- **Prometheus Zero Errors**: Queries Prometheus for 5xx errors in the last 5 minutes
- **Prometheus Deployment Health**: Validates pod readiness metrics

### 4. Automatic Rollback
- One-click Helm rollback if smoke tests fail
- Configurable target revision
- Post-rollback verification

## Prerequisites

```bash
# Install dependencies
pip install -r requirements-deploy.txt

# Dependencies added:
# - httpx>=0.25.1 (async HTTP client)
# - pyyaml>=6.0.1 (already in requirements)

# Ensure you have:
# - kubectl configured with access to production cluster
# - helm installed
# - Valid authentication token for API access
```

## Usage

### Basic Smoke Tests

```bash
python scripts/deploy/prod_smoke_tests.py \
  --base-url https://api.example.com \
  --workspace-id prod-workspace \
  --auth-token $AUTH_TOKEN
```

### With Prometheus and Kong Admin Validation

```bash
python scripts/deploy/prod_smoke_tests.py \
  --base-url https://api.example.com \
  --workspace-id prod-workspace \
  --auth-token $AUTH_TOKEN \
  --prometheus-url http://prometheus:9090 \
  --kong-admin-url http://kong-admin:8001
```

### With Automatic Rollback on Failure

```bash
python scripts/deploy/prod_smoke_tests.py \
  --base-url https://api.example.com \
  --workspace-id prod-workspace \
  --auth-token $AUTH_TOKEN \
  --enable-rollback \
  --namespace ai-platform-prod \
  --release-name ai-platform
```

### With Custom Rollback Revision

```bash
python scripts/deploy/prod_smoke_tests.py \
  --base-url https://api.example.com \
  --workspace-id prod-workspace \
  --auth-token $AUTH_TOKEN \
  --enable-rollback \
  --namespace ai-platform-prod \
  --release-name ai-platform \
  --rollback-revision 3
```

## Command Line Arguments

### Required Arguments

| Argument | Description |
|----------|-------------|
| `--base-url` | Base URL of production deployment (e.g., `https://api.example.com`) |
| `--workspace-id` | Workspace ID for testing |

### Optional Authentication

| Argument | Description |
|----------|-------------|
| `--auth-token` | Authentication token (Bearer token or JWT). Can also use `AUTH_TOKEN` env var |

### Optional Monitoring Endpoints

| Argument | Description |
|----------|-------------|
| `--prometheus-url` | Prometheus URL for metrics validation (e.g., `http://prometheus:9090`) |
| `--kong-admin-url` | Kong Admin API URL (e.g., `http://kong-admin:8001`) |

### Test Configuration

| Argument | Description | Default |
|----------|-------------|---------|
| `--timeout` | Timeout per request in seconds | 30 |

### Rollback Configuration

| Argument | Description | Default |
|----------|-------------|---------|
| `--enable-rollback` | Enable automatic rollback on test failure | False |
| `--namespace` | Kubernetes namespace | ai-platform-prod |
| `--release-name` | Helm release name | ai-platform |
| `--rollback-revision` | Specific revision to rollback to | Previous revision |

### Output Options

| Argument | Description |
|----------|-------------|
| `--verbose` | Enable verbose logging |

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All tests passed |
| 1 | Tests failed, rollback disabled or not requested |
| 2 | Tests failed, rollback completed successfully |
| 3 | Tests failed, rollback also failed (manual intervention required) |

## Integration with CI/CD

### GitHub Actions Example

```yaml
- name: Run Production Smoke Tests
  run: |
    python scripts/deploy/prod_smoke_tests.py \
      --base-url ${{ secrets.PROD_BASE_URL }} \
      --workspace-id prod-workspace \
      --auth-token ${{ secrets.PROD_AUTH_TOKEN }} \
      --prometheus-url ${{ secrets.PROMETHEUS_URL }} \
      --enable-rollback \
      --namespace ai-platform-prod \
      --release-name ai-platform
```

### GitLab CI Example

```yaml
production_smoke_tests:
  stage: verify
  script:
    - python scripts/deploy/prod_smoke_tests.py
        --base-url $PROD_BASE_URL
        --workspace-id prod-workspace
        --auth-token $PROD_AUTH_TOKEN
        --enable-rollback
        --namespace ai-platform-prod
        --release-name ai-platform
  only:
    - main
```

### Integration with Existing Deployment Script

You can integrate smoke tests into `prod_deploy.py`:

```python
# After successful deployment
logger.info("Running smoke tests...")
smoke_test_cmd = [
    "python", "scripts/deploy/prod_smoke_tests.py",
    "--base-url", production_url,
    "--workspace-id", "prod-workspace",
    "--auth-token", auth_token,
    "--enable-rollback",
    "--namespace", namespace,
    "--release-name", release_name
]

result = subprocess.run(smoke_test_cmd)
if result.returncode != 0:
    logger.error("Smoke tests failed!")
    sys.exit(1)
```

## Test Details

### 1. Kong Authentication Enforcement

**Purpose**: Verify that Kong Gateway is properly rejecting unauthenticated requests.

**Test**: Send POST request to `/v1/chat/completions` without authentication.

**Expected**: 401 Unauthorized response.

**Failure Scenarios**:
- Kong authentication plugin not configured
- API is publicly accessible (security risk)

### 2. Kong Rate Limiting Active

**Purpose**: Verify that rate limiting is configured and active.

**Test**: Check for rate limit headers in responses or query Kong Admin API.

**Expected**: Rate limit headers present (e.g., `X-RateLimit-Limit-Minute`) or rate limiting plugin found in Kong.

**Failure Scenarios**:
- Rate limiting plugin not configured
- Kong misconfigured

### 3. Chat Completion with Workspace Quota

**Purpose**: Validate authenticated chat completion endpoint and workspace quota tracking.

**Test**: Send authenticated POST request to `/v1/chat/completions` with valid workspace ID.

**Expected**: 
- 200 OK response with valid completion
- Usage/quota information in response or headers

**Failure Scenarios**:
- Authentication token invalid
- Workspace quota exhausted (429)
- API server unreachable or erroring

### 4. RAG Query with Citation Validation

**Purpose**: Validate RAG endpoint and citation mechanism.

**Test**: Send authenticated POST request to `/v1/rag/query` with `include_citations=True`.

**Expected**:
- 200 OK response
- Citations present and properly structured

**Failure Scenarios**:
- RAG service unavailable
- Qdrant not accessible
- Collection not found (404)

### 5. MCP Tools RBAC Enforcement

**Purpose**: Verify that MCP tool calls are subject to RBAC enforcement.

**Test**: Send authenticated POST request to `/internal/mcp/tools/call`.

**Expected** (any of the following):
- 200 OK: Tool executed (RBAC allows)
- 403 Forbidden: RBAC denied (correct enforcement)
- 404 Not Found: Tool/server not found (acceptable)

**Failure Scenarios**:
- RBAC not enforced (security risk)
- MCP gateway unreachable

### 6. Prometheus Zero Errors

**Purpose**: Validate that no 5xx errors occurred in the last 5 minutes.

**Test**: Query Prometheus with `sum(rate(http_requests_total{status=~"5.."}[5m]))`.

**Expected**: Error rate is 0.

**Failure Scenarios**:
- Recent deployment caused errors
- Service instability
- Prometheus unreachable (non-critical, test will pass with warning)

### 7. Prometheus Deployment Health

**Purpose**: Validate that all pods are ready according to Prometheus metrics.

**Test**: Query Prometheus with `kube_pod_status_ready{namespace="..."}`.

**Expected**: All pods are ready.

**Failure Scenarios**:
- Pods not fully started
- Pod crashes
- Prometheus unreachable (non-critical, test will pass with warning)

## Troubleshooting

### Authentication Failures

```bash
# Verify auth token is valid
curl -H "Authorization: Bearer $AUTH_TOKEN" \
  https://api.example.com/health

# Generate new JWT if needed
python examples/kong_auth_client.py
```

### Connection Timeouts

```bash
# Increase timeout
python scripts/deploy/prod_smoke_tests.py \
  --base-url https://api.example.com \
  --workspace-id prod-workspace \
  --auth-token $AUTH_TOKEN \
  --timeout 60
```

### Prometheus Connection Issues

```bash
# Test Prometheus connectivity
kubectl port-forward -n monitoring svc/prometheus 9090:9090

# Then use localhost in smoke tests
python scripts/deploy/prod_smoke_tests.py \
  --base-url https://api.example.com \
  --workspace-id prod-workspace \
  --auth-token $AUTH_TOKEN \
  --prometheus-url http://localhost:9090
```

### Manual Rollback

If automatic rollback fails:

```bash
# List releases
helm list -n ai-platform-prod

# View history
helm history ai-platform -n ai-platform-prod

# Rollback manually
helm rollback ai-platform -n ai-platform-prod --wait

# Or rollback to specific revision
helm rollback ai-platform 3 -n ai-platform-prod --wait
```

## Logs

Smoke test logs are saved to:
```
prod_smoke_tests_YYYYMMDD_HHMMSS.log
```

Each test run creates a new log file with timestamp for audit purposes.

## Best Practices

1. **Always run smoke tests after deployment** before declaring deployment complete
2. **Use `--enable-rollback` in automated deployments** to ensure fast recovery
3. **Monitor Prometheus metrics** for 5-10 minutes after smoke tests pass
4. **Keep auth tokens secure** - use environment variables or secret management
5. **Document rollback reasons** when automatic rollback occurs
6. **Test smoke tests in staging** before relying on them in production

## Security Considerations

- Auth tokens are never logged to console or files
- HTTPS/TLS verification is enforced by default
- Rate limiting validation prevents abuse
- RBAC enforcement is verified to prevent privilege escalation
- Workspace isolation is validated through workspace ID headers

## Future Enhancements

Potential additions to smoke test suite:

- [ ] WebSocket/streaming endpoint testing
- [ ] Graph query endpoint validation
- [ ] Memory service endpoint testing
- [ ] Multi-region failover validation
- [ ] Load testing integration
- [ ] Slack/PagerDuty notifications on failure
- [ ] Grafana dashboard integration
- [ ] Custom test plugin system
