# Production Smoke Tests - Quick Reference Card

## 🚀 Quick Start (30 seconds)

```bash
# 1. Generate token
export AUTH_TOKEN=$(python scripts/deploy/generate_smoke_test_token.py \
  --method rs256 \
  --private-key kong-jwt-keys/kong-jwt-private.pem \
  --key-id admin-key \
  --subject smoke-test-user \
  --workspace-id prod-workspace)

# 2. Run tests
python scripts/deploy/prod_smoke_tests.py \
  --base-url https://api.your-domain.com \
  --workspace-id prod-workspace \
  --auth-token $AUTH_TOKEN
```

## 📋 What Gets Tested

| Test | Validates | Critical? |
|------|-----------|-----------|
| Kong Auth | 401 without token | ✅ Critical |
| Kong Rate Limit | Rate limit headers/config | ✅ Critical |
| Chat Completion | `/v1/chat/completions` + quota | ✅ Critical |
| RAG Query | `/v1/rag/query` + citations | ✅ Critical |
| MCP Tools | `/internal/mcp/tools/call` + RBAC | ✅ Critical |
| Prometheus Errors | Zero 5xx in 5min | ⚠️ Important |
| Prometheus Health | All pods ready | ⚠️ Important |

## 🔄 Automatic Rollback

```bash
# Enable rollback on failure
python scripts/deploy/prod_smoke_tests.py \
  --base-url https://api.your-domain.com \
  --workspace-id prod-workspace \
  --auth-token $AUTH_TOKEN \
  --enable-rollback \
  --namespace ai-platform-prod \
  --release-name ai-platform
```

**Exit Codes:**
- `0` = ✅ Tests passed
- `1` = ❌ Tests failed (no rollback)
- `2` = ⚠️ Tests failed, rollback OK
- `3` = 🚨 Tests failed, rollback FAILED

## 🔑 Token Generation

```bash
# RS256 (Kong JWT)
python scripts/deploy/generate_smoke_test_token.py \
  --method rs256 \
  --private-key kong-jwt-keys/kong-jwt-private.pem \
  --key-id admin-key \
  --subject USER \
  --workspace-id WORKSPACE

# HS256 (Simple)
python scripts/deploy/generate_smoke_test_token.py \
  --method hs256 \
  --secret YOUR_SECRET \
  --subject USER \
  --workspace-id WORKSPACE

# Inspect token
python scripts/deploy/generate_smoke_test_token.py \
  --method rs256 \
  --private-key kong-jwt-keys/kong-jwt-private.pem \
  --key-id admin-key \
  --subject USER \
  --workspace-id WORKSPACE \
  --inspect
```

## 🎯 Common Use Cases

### 1. Post-Deployment Validation
```bash
# After helm upgrade
python scripts/deploy/prod_smoke_tests.py \
  --base-url https://api.your-domain.com \
  --workspace-id prod-workspace \
  --auth-token $AUTH_TOKEN
```

### 2. Full CI/CD Pipeline
```bash
# One-liner deployment with tests
bash scripts/deploy/deploy_with_smoke_tests.sh
```

### 3. With Prometheus
```bash
python scripts/deploy/prod_smoke_tests.py \
  --base-url https://api.your-domain.com \
  --workspace-id prod-workspace \
  --auth-token $AUTH_TOKEN \
  --prometheus-url http://prometheus:9090
```

### 4. With Kong Admin
```bash
python scripts/deploy/prod_smoke_tests.py \
  --base-url https://api.your-domain.com \
  --workspace-id prod-workspace \
  --auth-token $AUTH_TOKEN \
  --kong-admin-url http://kong-admin:8001
```

### 5. Local Testing (Port-Forward)
```bash
kubectl port-forward -n ai-platform-prod svc/agent-router 8000:8000 &
python scripts/deploy/prod_smoke_tests.py \
  --base-url http://localhost:8000 \
  --workspace-id test-workspace \
  --auth-token $AUTH_TOKEN
```

## 🔧 Troubleshooting

### Problem: Authentication Failed (401)

```bash
# Verify token
python scripts/deploy/generate_smoke_test_token.py \
  --method rs256 \
  --private-key kong-jwt-keys/kong-jwt-private.pem \
  --key-id admin-key \
  --subject USER \
  --workspace-id WORKSPACE \
  --inspect

# Test manually
curl -H "Authorization: Bearer $AUTH_TOKEN" \
  -H "X-Workspace-Id: prod-workspace" \
  https://api.your-domain.com/health
```

### Problem: Timeout

```bash
# Increase timeout
python scripts/deploy/prod_smoke_tests.py \
  --base-url https://api.your-domain.com \
  --workspace-id prod-workspace \
  --auth-token $AUTH_TOKEN \
  --timeout 60
```

### Problem: Prometheus Unreachable

```bash
# Port-forward Prometheus
kubectl port-forward -n monitoring svc/prometheus 9090:9090 &

# Use localhost
python scripts/deploy/prod_smoke_tests.py \
  --base-url https://api.your-domain.com \
  --workspace-id prod-workspace \
  --auth-token $AUTH_TOKEN \
  --prometheus-url http://localhost:9090
```

### Problem: Tests Failed, Need Manual Rollback

```bash
# Check current revision
helm list -n ai-platform-prod

# View history
helm history ai-platform -n ai-platform-prod

# Rollback
helm rollback ai-platform -n ai-platform-prod --wait

# Or to specific revision
helm rollback ai-platform 3 -n ai-platform-prod --wait
```

## 📁 File Locations

```
scripts/deploy/
├── prod_smoke_tests.py              # Main test suite
├── generate_smoke_test_token.py     # Token generator
├── deploy_with_smoke_tests.sh       # Full deployment
├── PROD_SMOKE_TESTS_README.md       # Full docs
├── SMOKE_TEST_EXAMPLES.md           # Examples
└── PROD_SMOKE_TESTS_QUICK_REFERENCE.md  # This file
```

## 📝 Environment Variables

```bash
# Required
export BASE_URL="https://api.your-domain.com"
export WORKSPACE_ID="prod-workspace"
export AUTH_TOKEN="eyJhbGc..."

# Optional
export PROMETHEUS_URL="http://prometheus:9090"
export KONG_ADMIN_URL="http://kong-admin:8001"
export NAMESPACE="ai-platform-prod"
export RELEASE_NAME="ai-platform"
export ENABLE_ROLLBACK="true"
```

## 🔐 Security Checklist

- ✅ Never commit auth tokens to git
- ✅ Use environment variables for secrets
- ✅ Use short-lived tokens (1-24 hours)
- ✅ Rotate tokens regularly
- ✅ Use different tokens for staging/prod
- ✅ Mask tokens in CI/CD logs
- ✅ Validate HTTPS/TLS is enforced

## 📊 CI/CD Integration

### GitHub Actions
```yaml
- name: Smoke Tests
  run: |
    export AUTH_TOKEN=$(python scripts/deploy/generate_smoke_test_token.py \
      --method hs256 --secret ${{ secrets.JWT_SECRET }} \
      --subject ci-user --workspace-id prod-workspace)
    python scripts/deploy/prod_smoke_tests.py \
      --base-url ${{ secrets.PROD_URL }} \
      --workspace-id prod-workspace \
      --auth-token $AUTH_TOKEN \
      --enable-rollback
```

### GitLab CI
```yaml
smoke_tests:
  script:
    - export AUTH_TOKEN=$(python scripts/deploy/generate_smoke_test_token.py
        --method hs256 --secret $JWT_SECRET
        --subject ci-user --workspace-id prod-workspace)
    - python scripts/deploy/prod_smoke_tests.py
        --base-url $PROD_URL
        --workspace-id prod-workspace
        --auth-token $AUTH_TOKEN
        --enable-rollback
```

## 🆘 Support

- **Full Documentation**: `PROD_SMOKE_TESTS_README.md`
- **Examples**: `SMOKE_TEST_EXAMPLES.md`
- **Implementation Details**: `PROD_SMOKE_TESTS_IMPLEMENTATION.md`
- **Logs**: `prod_smoke_tests_YYYYMMDD_HHMMSS.log`

## ⚡ Advanced Features

```bash
# Verbose logging
--verbose

# Custom timeout per request
--timeout 60

# Specific rollback revision
--rollback-revision 3

# Output formats for token
--output token    # Just the token
--output json     # Token + decoded payload
--output env      # Export statement

# Token expiration
--expiration-hours 1

# Custom scopes
--scopes api.read api.write mcp.call
```

## 🎨 Pro Tips

1. **Generate tokens just before use** to minimize exposure
2. **Enable verbose logging** when debugging failures
3. **Run smoke tests in staging** before production
4. **Monitor smoke test logs** for patterns
5. **Use --enable-rollback in automated pipelines** for safety
6. **Set up scheduled smoke tests** for continuous monitoring
7. **Keep tokens under 24 hours** expiration
8. **Document rollback reasons** when they occur

---

**Quick Help**: `python scripts/deploy/prod_smoke_tests.py --help`
