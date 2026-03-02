# Production Smoke Test Examples

This document provides practical examples for running production smoke tests in various scenarios.

## Quick Start

### 1. Generate Authentication Token

```bash
# Generate Kong JWT token (RS256)
python scripts/deploy/generate_smoke_test_token.py \
  --method rs256 \
  --private-key kong-jwt-keys/kong-jwt-private.pem \
  --key-id admin-key \
  --subject smoke-test-user \
  --workspace-id prod-workspace \
  --expiration-hours 1

# Export token to environment variable
export AUTH_TOKEN=$(python scripts/deploy/generate_smoke_test_token.py \
  --method rs256 \
  --private-key kong-jwt-keys/kong-jwt-private.pem \
  --key-id admin-key \
  --subject smoke-test-user \
  --workspace-id prod-workspace)
```

### 2. Run Basic Smoke Tests

```bash
python scripts/deploy/prod_smoke_tests.py \
  --base-url https://api.your-domain.com \
  --workspace-id prod-workspace \
  --auth-token $AUTH_TOKEN
```

## Common Scenarios

### Scenario 1: Post-Deployment Validation (Manual)

After manually deploying with Helm:

```bash
# Deploy
helm upgrade --install ai-platform helm/ai-platform \
  --namespace ai-platform-prod \
  --values helm/ai-platform/values-production-secure.yaml \
  --wait

# Wait for pods
kubectl wait --for=condition=ready pod \
  -l app.kubernetes.io/instance=ai-platform \
  -n ai-platform-prod \
  --timeout=300s

# Generate token
export AUTH_TOKEN=$(python scripts/deploy/generate_smoke_test_token.py \
  --method rs256 \
  --private-key kong-jwt-keys/kong-jwt-private.pem \
  --key-id admin-key \
  --subject smoke-test-user \
  --workspace-id prod-workspace)

# Run smoke tests
python scripts/deploy/prod_smoke_tests.py \
  --base-url https://api.your-domain.com \
  --workspace-id prod-workspace \
  --auth-token $AUTH_TOKEN \
  --prometheus-url http://prometheus.monitoring:9090 \
  --kong-admin-url http://kong-admin:8001 \
  --verbose
```

### Scenario 2: Automated Deployment with Rollback

Use the integrated deployment script:

```bash
# Set environment variables
export NAMESPACE="ai-platform-prod"
export RELEASE_NAME="ai-platform"
export BASE_URL="https://api.your-domain.com"
export WORKSPACE_ID="prod-workspace"
export ENABLE_ROLLBACK="true"
export PROMETHEUS_URL="http://prometheus.monitoring:9090"
export KONG_ADMIN_URL="http://kong-admin:8001"

# Generate token
export AUTH_TOKEN=$(python scripts/deploy/generate_smoke_test_token.py \
  --method rs256 \
  --private-key kong-jwt-keys/kong-jwt-private.pem \
  --key-id admin-key \
  --subject smoke-test-user \
  --workspace-id $WORKSPACE_ID)

# Deploy with automatic smoke tests and rollback
bash scripts/deploy/deploy_with_smoke_tests.sh
```

### Scenario 3: CI/CD Pipeline Integration (GitHub Actions)

```yaml
name: Production Deployment

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Configure kubectl
        uses: azure/k8s-set-context@v3
        with:
          kubeconfig: ${{ secrets.KUBECONFIG }}
      
      - name: Install dependencies
        run: pip install -r scripts/deploy/requirements-deploy.txt
      
      - name: Deploy Helm chart
        run: |
          helm upgrade --install ai-platform helm/ai-platform \
            --namespace ai-platform-prod \
            --values helm/ai-platform/values-production-secure.yaml \
            --wait --timeout 10m
      
      - name: Generate smoke test token
        id: token
        run: |
          TOKEN=$(python scripts/deploy/generate_smoke_test_token.py \
            --method hs256 \
            --secret ${{ secrets.JWT_SECRET }} \
            --subject smoke-test-user \
            --workspace-id prod-workspace)
          echo "::add-mask::$TOKEN"
          echo "token=$TOKEN" >> $GITHUB_OUTPUT
      
      - name: Run smoke tests with automatic rollback
        run: |
          python scripts/deploy/prod_smoke_tests.py \
            --base-url ${{ secrets.PROD_BASE_URL }} \
            --workspace-id prod-workspace \
            --auth-token ${{ steps.token.outputs.token }} \
            --prometheus-url ${{ secrets.PROMETHEUS_URL }} \
            --enable-rollback \
            --namespace ai-platform-prod \
            --release-name ai-platform
      
      - name: Upload smoke test logs
        if: always()
        uses: actions/upload-artifact@v3
        with:
          name: smoke-test-logs
          path: prod_smoke_tests_*.log
```

### Scenario 4: CI/CD Pipeline Integration (GitLab CI)

```yaml
stages:
  - deploy
  - verify

deploy_production:
  stage: deploy
  script:
    - helm upgrade --install ai-platform helm/ai-platform
        --namespace ai-platform-prod
        --values helm/ai-platform/values-production-secure.yaml
        --wait --timeout 10m
  only:
    - main

smoke_tests:
  stage: verify
  script:
    - pip install -r scripts/deploy/requirements-deploy.txt
    - |
      export AUTH_TOKEN=$(python scripts/deploy/generate_smoke_test_token.py \
        --method hs256 \
        --secret $JWT_SECRET \
        --subject smoke-test-user \
        --workspace-id prod-workspace)
    - |
      python scripts/deploy/prod_smoke_tests.py \
        --base-url $PROD_BASE_URL \
        --workspace-id prod-workspace \
        --auth-token $AUTH_TOKEN \
        --prometheus-url $PROMETHEUS_URL \
        --enable-rollback \
        --namespace ai-platform-prod \
        --release-name ai-platform
  artifacts:
    when: always
    paths:
      - prod_smoke_tests_*.log
  only:
    - main
```

### Scenario 5: Multi-Region Deployment

Deploy and test multiple regions sequentially:

```bash
#!/bin/bash

REGIONS=("us-east-1" "eu-west-1" "ap-southeast-1")
FAILED_REGIONS=()

for REGION in "${REGIONS[@]}"; do
  echo "=========================================="
  echo "Deploying to region: $REGION"
  echo "=========================================="
  
  # Set region-specific configuration
  KUBECONFIG="~/.kube/config-$REGION"
  BASE_URL="https://api-$REGION.your-domain.com"
  NAMESPACE="ai-platform-prod"
  
  # Deploy
  helm upgrade --install ai-platform helm/ai-platform \
    --kubeconfig $KUBECONFIG \
    --namespace $NAMESPACE \
    --values helm/ai-platform/values-production-$REGION.yaml \
    --wait --timeout 10m
  
  if [ $? -ne 0 ]; then
    echo "Deployment failed in $REGION"
    FAILED_REGIONS+=($REGION)
    continue
  fi
  
  # Generate token
  export AUTH_TOKEN=$(python scripts/deploy/generate_smoke_test_token.py \
    --method rs256 \
    --private-key kong-jwt-keys/kong-jwt-private.pem \
    --key-id admin-key \
    --subject smoke-test-user \
    --workspace-id prod-workspace)
  
  # Run smoke tests with rollback
  python scripts/deploy/prod_smoke_tests.py \
    --base-url $BASE_URL \
    --workspace-id prod-workspace \
    --auth-token $AUTH_TOKEN \
    --enable-rollback \
    --namespace $NAMESPACE \
    --release-name ai-platform
  
  if [ $? -ne 0 ]; then
    echo "Smoke tests failed in $REGION"
    FAILED_REGIONS+=($REGION)
    continue
  fi
  
  echo "✓ $REGION deployment successful"
done

# Summary
if [ ${#FAILED_REGIONS[@]} -eq 0 ]; then
  echo "✓ All regions deployed successfully"
  exit 0
else
  echo "✗ Failed regions: ${FAILED_REGIONS[@]}"
  exit 1
fi
```

### Scenario 6: Blue-Green Deployment Validation

Validate both blue and green environments before switching traffic:

```bash
# Deploy to green environment
helm upgrade --install ai-platform-green helm/ai-platform \
  --namespace ai-platform-prod \
  --values helm/ai-platform/values-production-green.yaml \
  --wait

# Generate token
export AUTH_TOKEN=$(python scripts/deploy/generate_smoke_test_token.py \
  --method rs256 \
  --private-key kong-jwt-keys/kong-jwt-private.pem \
  --key-id admin-key \
  --subject smoke-test-user \
  --workspace-id prod-workspace)

# Test green environment (internal URL, before traffic switch)
python scripts/deploy/prod_smoke_tests.py \
  --base-url https://api-green.internal.your-domain.com \
  --workspace-id prod-workspace \
  --auth-token $AUTH_TOKEN \
  --prometheus-url http://prometheus.monitoring:9090 \
  --verbose

if [ $? -eq 0 ]; then
  echo "✓ Green environment validated"
  
  # Switch traffic to green
  kubectl patch service ai-platform-gateway \
    -n ai-platform-prod \
    -p '{"spec":{"selector":{"version":"green"}}}'
  
  # Test production URL (now pointing to green)
  sleep 10
  python scripts/deploy/prod_smoke_tests.py \
    --base-url https://api.your-domain.com \
    --workspace-id prod-workspace \
    --auth-token $AUTH_TOKEN \
    --prometheus-url http://prometheus.monitoring:9090
  
  if [ $? -eq 0 ]; then
    echo "✓ Production traffic successfully switched to green"
  else
    echo "✗ Production validation failed, rolling back traffic"
    kubectl patch service ai-platform-gateway \
      -n ai-platform-prod \
      -p '{"spec":{"selector":{"version":"blue"}}}'
  fi
else
  echo "✗ Green environment validation failed"
  exit 1
fi
```

### Scenario 7: Scheduled Smoke Tests (Monitoring)

Run smoke tests periodically to detect issues:

```bash
# Cron job (every 5 minutes)
*/5 * * * * /path/to/run-smoke-tests.sh >> /var/log/smoke-tests.log 2>&1
```

```bash
#!/bin/bash
# run-smoke-tests.sh

# Generate token
export AUTH_TOKEN=$(python scripts/deploy/generate_smoke_test_token.py \
  --method rs256 \
  --private-key kong-jwt-keys/kong-jwt-private.pem \
  --key-id admin-key \
  --subject monitoring-user \
  --workspace-id prod-workspace \
  --expiration-hours 1)

# Run smoke tests (no rollback for monitoring)
python scripts/deploy/prod_smoke_tests.py \
  --base-url https://api.your-domain.com \
  --workspace-id prod-workspace \
  --auth-token $AUTH_TOKEN \
  --prometheus-url http://prometheus.monitoring:9090 \
  --timeout 15

if [ $? -ne 0 ]; then
  # Send alert
  curl -X POST https://hooks.slack.com/services/YOUR/WEBHOOK/URL \
    -H 'Content-Type: application/json' \
    -d '{"text":"🚨 Production smoke tests failed!"}'
fi
```

### Scenario 8: Testing Without Authentication (Public Endpoints)

Test public endpoints without authentication:

```bash
python scripts/deploy/prod_smoke_tests.py \
  --base-url https://api.your-domain.com \
  --workspace-id prod-workspace \
  # No --auth-token provided
```

Note: Only authentication enforcement test will pass. Other tests will fail with 401.

### Scenario 9: Testing with Kong Admin Access

Full validation including Kong configuration:

```bash
# Port-forward Kong Admin API
kubectl port-forward -n kong svc/kong-admin 8001:8001 &
KONG_PF_PID=$!

# Wait for port-forward
sleep 2

# Generate token
export AUTH_TOKEN=$(python scripts/deploy/generate_smoke_test_token.py \
  --method rs256 \
  --private-key kong-jwt-keys/kong-jwt-private.pem \
  --key-id admin-key \
  --subject smoke-test-user \
  --workspace-id prod-workspace)

# Run smoke tests with Kong admin validation
python scripts/deploy/prod_smoke_tests.py \
  --base-url https://api.your-domain.com \
  --workspace-id prod-workspace \
  --auth-token $AUTH_TOKEN \
  --kong-admin-url http://localhost:8001 \
  --prometheus-url http://prometheus.monitoring:9090 \
  --verbose

# Cleanup
kill $KONG_PF_PID
```

### Scenario 10: Local Testing (Port-Forward)

Test local Kubernetes deployment:

```bash
# Port-forward services
kubectl port-forward -n ai-platform-prod svc/agent-router 8000:8000 &
AGENT_PF_PID=$!

kubectl port-forward -n monitoring svc/prometheus 9090:9090 &
PROM_PF_PID=$!

# Wait for port-forwards
sleep 5

# Generate token
export AUTH_TOKEN=$(python scripts/deploy/generate_smoke_test_token.py \
  --method rs256 \
  --private-key kong-jwt-keys/kong-jwt-private.pem \
  --key-id admin-key \
  --subject smoke-test-user \
  --workspace-id test-workspace)

# Run smoke tests
python scripts/deploy/prod_smoke_tests.py \
  --base-url http://localhost:8000 \
  --workspace-id test-workspace \
  --auth-token $AUTH_TOKEN \
  --prometheus-url http://localhost:9090 \
  --verbose

# Cleanup
kill $AGENT_PF_PID $PROM_PF_PID
```

## Troubleshooting Examples

### Debug Failed Test

```bash
# Run with verbose logging
python scripts/deploy/prod_smoke_tests.py \
  --base-url https://api.your-domain.com \
  --workspace-id prod-workspace \
  --auth-token $AUTH_TOKEN \
  --verbose

# Check recent logs
tail -100 prod_smoke_tests_*.log | grep -A 5 "FAIL"
```

### Verify Token

```bash
# Generate and inspect token
python scripts/deploy/generate_smoke_test_token.py \
  --method rs256 \
  --private-key kong-jwt-keys/kong-jwt-private.pem \
  --key-id admin-key \
  --subject smoke-test-user \
  --workspace-id prod-workspace \
  --inspect

# Test token manually
export AUTH_TOKEN=$(python scripts/deploy/generate_smoke_test_token.py \
  --method rs256 \
  --private-key kong-jwt-keys/kong-jwt-private.pem \
  --key-id admin-key \
  --subject smoke-test-user \
  --workspace-id prod-workspace)

curl -H "Authorization: Bearer $AUTH_TOKEN" \
  -H "X-Workspace-Id: prod-workspace" \
  https://api.your-domain.com/health
```

### Test Individual Endpoints

```bash
# Test chat completion
curl -X POST https://api.your-domain.com/v1/chat/completions \
  -H "Authorization: Bearer $AUTH_TOKEN" \
  -H "X-Workspace-Id: prod-workspace" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama-3.3-8b",
    "messages": [{"role": "user", "content": "Hello"}],
    "max_tokens": 50
  }'

# Test RAG query
curl -X POST https://api.your-domain.com/v1/rag/query \
  -H "Authorization: Bearer $AUTH_TOKEN" \
  -H "X-Workspace-Id: prod-workspace" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is the deployment process?",
    "collection": "documentation",
    "top_k": 3,
    "include_citations": true
  }'

# Test MCP tools
curl -X POST https://api.your-domain.com/internal/mcp/tools/call \
  -H "Authorization: Bearer $AUTH_TOKEN" \
  -H "X-Workspace-Id: prod-workspace" \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "list_files",
    "arguments": {"path": "/tmp"},
    "server_name": "filesystem"
  }'
```

## Best Practices

1. **Always use short-lived tokens** for smoke tests (1-24 hours)
2. **Store sensitive values in environment variables or secrets manager**
3. **Run smoke tests after every deployment**
4. **Enable automatic rollback in CI/CD pipelines**
5. **Monitor smoke test logs for patterns**
6. **Test smoke tests in staging first**
7. **Keep smoke tests fast** (< 2 minutes total)
8. **Document rollback reasons** when they occur
