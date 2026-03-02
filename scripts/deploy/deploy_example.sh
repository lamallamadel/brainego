#!/bin/bash
#
# Example Production Deployment Script
#
# This script demonstrates how to use prod_deploy.py for production deployment
# with all recommended settings and validations.
#

set -e

# Configuration
NAMESPACE="${NAMESPACE:-ai-platform-prod}"
RELEASE_NAME="${RELEASE_NAME:-ai-platform}"
CHART_PATH="${CHART_PATH:-helm/ai-platform}"
VALUES_FILE="${VALUES_FILE:-helm/ai-platform/values-production-secure.yaml}"
BASE_URL="${BASE_URL:-https://api.example.com}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "======================================================================"
echo "AI PLATFORM PRODUCTION DEPLOYMENT"
echo "======================================================================"
echo ""
echo "Namespace:    $NAMESPACE"
echo "Release:      $RELEASE_NAME"
echo "Chart:        $CHART_PATH"
echo "Values:       $VALUES_FILE"
echo "Base URL:     $BASE_URL"
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

echo -e "${GREEN}✓ Prerequisites check passed${NC}"
echo ""

# Verify cluster connectivity
echo "Verifying cluster connectivity..."
if ! kubectl cluster-info &> /dev/null; then
    echo -e "${RED}Error: Cannot connect to Kubernetes cluster${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Cluster connectivity verified${NC}"
echo ""

# Define smoke test URLs
SMOKE_TEST_URLS=(
    "$BASE_URL/gateway/health"
    "$BASE_URL/v1/health"
    "$BASE_URL/memory/health"
    "$BASE_URL/learning/health"
    "$BASE_URL/mcp/health"
    "$BASE_URL/metrics"
)

# Convert array to space-separated string
SMOKE_TEST_ARGS=""
for url in "${SMOKE_TEST_URLS[@]}"; do
    SMOKE_TEST_ARGS="$SMOKE_TEST_ARGS $url"
done

# Run deployment
echo "Starting deployment..."
echo ""

python3 scripts/deploy/prod_deploy.py \
    --namespace "$NAMESPACE" \
    --release-name "$RELEASE_NAME" \
    --chart-path "$CHART_PATH" \
    --values-file "$VALUES_FILE" \
    --timeout 600 \
    --helm-extra-args \
        --set kong.enabled=true \
        --set certManager.enabled=true \
        --set networkPolicies.enabled=true \
        --set rbac.enabled=true \
    --smoke-test-urls $SMOKE_TEST_ARGS \
    --verbose

DEPLOY_EXIT_CODE=$?

if [ $DEPLOY_EXIT_CODE -eq 0 ]; then
    echo ""
    echo -e "${GREEN}✓ Deployment completed successfully${NC}"
    echo ""
    
    # Run additional smoke tests
    echo "Running additional smoke tests..."
    python3 scripts/deploy/smoke_tests.py \
        --base-url "$BASE_URL" \
        --retry-count 3 \
        --retry-delay 10
    
    SMOKE_EXIT_CODE=$?
    
    if [ $SMOKE_EXIT_CODE -eq 0 ]; then
        echo ""
        echo -e "${GREEN}✓ All smoke tests passed${NC}"
        echo ""
        echo "======================================================================"
        echo "DEPLOYMENT SUCCESS"
        echo "======================================================================"
        echo ""
        echo "Next steps:"
        echo "  1. Monitor deployment:"
        echo "     kubectl get pods -n $NAMESPACE -w"
        echo ""
        echo "  2. Check logs:"
        echo "     kubectl logs -n $NAMESPACE -l app.kubernetes.io/name=agent-router --tail=100"
        echo ""
        echo "  3. Access Grafana:"
        echo "     kubectl port-forward -n $NAMESPACE svc/grafana 3000:3000"
        echo ""
        echo "  4. View metrics:"
        echo "     curl $BASE_URL/metrics"
        echo ""
        exit 0
    else
        echo ""
        echo -e "${YELLOW}⚠ Deployment succeeded but some smoke tests failed${NC}"
        echo "Please investigate the failures before proceeding."
        exit 1
    fi
else
    echo ""
    echo -e "${RED}✗ Deployment failed${NC}"
    echo ""
    echo "Troubleshooting:"
    echo "  1. Check deployment logs:"
    echo "     cat prod_deploy_*.log"
    echo ""
    echo "  2. Check pod status:"
    echo "     kubectl get pods -n $NAMESPACE"
    echo ""
    echo "  3. Check events:"
    echo "     kubectl get events -n $NAMESPACE --sort-by='.lastTimestamp'"
    echo ""
    echo "  4. Rollback if needed:"
    echo "     helm rollback $RELEASE_NAME -n $NAMESPACE"
    echo ""
    exit 1
fi
