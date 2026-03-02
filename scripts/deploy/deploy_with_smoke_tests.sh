#!/bin/bash
#
# Production Deployment with Smoke Tests and Automatic Rollback
#
# This script orchestrates:
# 1. Helm deployment
# 2. Production smoke tests
# 3. Automatic rollback on failure
#

set -e

# Configuration
NAMESPACE="${NAMESPACE:-ai-platform-prod}"
RELEASE_NAME="${RELEASE_NAME:-ai-platform}"
CHART_PATH="${CHART_PATH:-helm/ai-platform}"
VALUES_FILE="${VALUES_FILE:-helm/ai-platform/values-production-secure.yaml}"
BASE_URL="${BASE_URL:-https://api.example.com}"
WORKSPACE_ID="${WORKSPACE_ID:-prod-workspace}"
PROMETHEUS_URL="${PROMETHEUS_URL:-}"
KONG_ADMIN_URL="${KONG_ADMIN_URL:-}"
ENABLE_ROLLBACK="${ENABLE_ROLLBACK:-true}"
TIMEOUT="${TIMEOUT:-600}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "======================================================================"
echo "PRODUCTION DEPLOYMENT WITH SMOKE TESTS"
echo "======================================================================"
echo ""
echo "Configuration:"
echo "  Namespace: $NAMESPACE"
echo "  Release: $RELEASE_NAME"
echo "  Chart: $CHART_PATH"
echo "  Values: $VALUES_FILE"
echo "  Base URL: $BASE_URL"
echo "  Workspace ID: $WORKSPACE_ID"
echo "  Enable Rollback: $ENABLE_ROLLBACK"
echo ""
echo "======================================================================"
echo ""

# Check prerequisites
echo "Checking prerequisites..."
if ! command -v helm &> /dev/null; then
    echo -e "${RED}Error: helm not found${NC}"
    exit 1
fi

if ! command -v kubectl &> /dev/null; then
    echo -e "${RED}Error: kubectl not found${NC}"
    exit 1
fi

if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: python3 not found${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Prerequisites OK${NC}"
echo ""

# Get current revision before deployment
CURRENT_REVISION=$(helm list -n "$NAMESPACE" -o json | jq -r ".[] | select(.name==\"$RELEASE_NAME\") | .revision" || echo "0")
echo "Current revision: $CURRENT_REVISION"
echo ""

# Phase 1: Helm Deployment
echo "======================================================================"
echo "PHASE 1: HELM DEPLOYMENT"
echo "======================================================================"
echo ""

helm upgrade --install \
    "$RELEASE_NAME" \
    "$CHART_PATH" \
    --namespace "$NAMESPACE" \
    --create-namespace \
    --values "$VALUES_FILE" \
    --wait \
    --timeout "${TIMEOUT}s"

if [ $? -ne 0 ]; then
    echo ""
    echo -e "${RED}✗ Helm deployment failed${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}✓ Helm deployment completed${NC}"
echo ""

# Get new revision
NEW_REVISION=$(helm list -n "$NAMESPACE" -o json | jq -r ".[] | select(.name==\"$RELEASE_NAME\") | .revision")
echo "New revision: $NEW_REVISION"
echo ""

# Wait for pods to be ready
echo "Waiting for pods to be ready..."
kubectl wait --for=condition=ready pod \
    -l app.kubernetes.io/instance="$RELEASE_NAME" \
    -n "$NAMESPACE" \
    --timeout=300s || true

echo ""
echo "Pod status:"
kubectl get pods -n "$NAMESPACE"
echo ""

# Phase 2: Smoke Tests
echo "======================================================================"
echo "PHASE 2: PRODUCTION SMOKE TESTS"
echo "======================================================================"
echo ""

# Build smoke test command
SMOKE_TEST_CMD="python3 scripts/deploy/prod_smoke_tests.py"
SMOKE_TEST_CMD="$SMOKE_TEST_CMD --base-url $BASE_URL"
SMOKE_TEST_CMD="$SMOKE_TEST_CMD --workspace-id $WORKSPACE_ID"
SMOKE_TEST_CMD="$SMOKE_TEST_CMD --namespace $NAMESPACE"
SMOKE_TEST_CMD="$SMOKE_TEST_CMD --release-name $RELEASE_NAME"

# Add auth token if provided
if [ -n "$AUTH_TOKEN" ]; then
    SMOKE_TEST_CMD="$SMOKE_TEST_CMD --auth-token $AUTH_TOKEN"
fi

# Add Prometheus URL if provided
if [ -n "$PROMETHEUS_URL" ]; then
    SMOKE_TEST_CMD="$SMOKE_TEST_CMD --prometheus-url $PROMETHEUS_URL"
fi

# Add Kong Admin URL if provided
if [ -n "$KONG_ADMIN_URL" ]; then
    SMOKE_TEST_CMD="$SMOKE_TEST_CMD --kong-admin-url $KONG_ADMIN_URL"
fi

# Enable rollback if configured
if [ "$ENABLE_ROLLBACK" = "true" ]; then
    SMOKE_TEST_CMD="$SMOKE_TEST_CMD --enable-rollback"
fi

# Run smoke tests
echo "Running: $SMOKE_TEST_CMD"
echo ""

eval $SMOKE_TEST_CMD
SMOKE_TEST_EXIT_CODE=$?

# Phase 3: Handle Results
echo ""
echo "======================================================================"
echo "DEPLOYMENT RESULT"
echo "======================================================================"
echo ""

if [ $SMOKE_TEST_EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✓ DEPLOYMENT SUCCESSFUL${NC}"
    echo ""
    echo "Deployment completed and verified!"
    echo "  Namespace: $NAMESPACE"
    echo "  Release: $RELEASE_NAME"
    echo "  Revision: $NEW_REVISION"
    echo ""
    echo "Next steps:"
    echo "  1. Monitor metrics:"
    echo "     kubectl port-forward -n $NAMESPACE svc/grafana 3000:3000"
    echo ""
    echo "  2. View logs:"
    echo "     kubectl logs -n $NAMESPACE -l app.kubernetes.io/name=agent-router --tail=100 -f"
    echo ""
    echo "  3. Check pod status:"
    echo "     kubectl get pods -n $NAMESPACE"
    echo ""
    exit 0

elif [ $SMOKE_TEST_EXIT_CODE -eq 2 ]; then
    echo -e "${YELLOW}⚠ SMOKE TESTS FAILED - ROLLBACK COMPLETED${NC}"
    echo ""
    echo "Deployment was automatically rolled back due to smoke test failures."
    echo "  Rolled back to revision: $CURRENT_REVISION"
    echo ""
    echo "Action required:"
    echo "  1. Review smoke test logs"
    echo "  2. Investigate failures"
    echo "  3. Fix issues before redeploying"
    echo ""
    echo "Logs:"
    echo "  $(ls -t prod_smoke_tests_*.log | head -1)"
    echo ""
    exit 2

elif [ $SMOKE_TEST_EXIT_CODE -eq 3 ]; then
    echo -e "${RED}✗ CRITICAL: SMOKE TESTS FAILED AND ROLLBACK FAILED${NC}"
    echo ""
    echo "Manual intervention required immediately!"
    echo ""
    echo "Current state is unknown. Possible actions:"
    echo ""
    echo "  1. Check cluster status:"
    echo "     kubectl get pods -n $NAMESPACE"
    echo "     kubectl get events -n $NAMESPACE --sort-by='.lastTimestamp'"
    echo ""
    echo "  2. Manual rollback:"
    echo "     helm rollback $RELEASE_NAME $CURRENT_REVISION -n $NAMESPACE --wait"
    echo ""
    echo "  3. View logs:"
    echo "     kubectl logs -n $NAMESPACE -l app.kubernetes.io/name=agent-router --tail=100"
    echo ""
    echo "  4. Contact on-call engineer"
    echo ""
    exit 3

else
    echo -e "${RED}✗ SMOKE TESTS FAILED${NC}"
    echo ""
    echo "Smoke tests failed but rollback was not enabled or completed."
    echo "  Current revision: $NEW_REVISION"
    echo ""
    echo "Action required:"
    echo "  1. Review smoke test logs"
    echo "  2. Decide: keep deployment or rollback"
    echo ""
    echo "To rollback manually:"
    echo "  helm rollback $RELEASE_NAME $CURRENT_REVISION -n $NAMESPACE --wait"
    echo ""
    echo "Logs:"
    echo "  $(ls -t prod_smoke_tests_*.log | head -1)"
    echo ""
    exit 1
fi
