#!/bin/bash
#
# Rollback Script for Production Deployment
#
# This script safely rolls back a Helm release to a previous version.
#

set -e

# Configuration
NAMESPACE="${NAMESPACE:-ai-platform-prod}"
RELEASE_NAME="${RELEASE_NAME:-ai-platform}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "======================================================================"
echo "AI PLATFORM PRODUCTION ROLLBACK"
echo "======================================================================"
echo ""

# Check if release exists
if ! helm list -n "$NAMESPACE" | grep -q "$RELEASE_NAME"; then
    echo -e "${RED}Error: Release '$RELEASE_NAME' not found in namespace '$NAMESPACE'${NC}"
    exit 1
fi

# Show current release status
echo "Current release status:"
helm status "$RELEASE_NAME" -n "$NAMESPACE"
echo ""

# Show release history
echo "Release history:"
helm history "$RELEASE_NAME" -n "$NAMESPACE"
echo ""

# Get current revision
CURRENT_REVISION=$(helm list -n "$NAMESPACE" -o json | jq -r ".[] | select(.name==\"$RELEASE_NAME\") | .revision")
echo -e "${BLUE}Current revision: $CURRENT_REVISION${NC}"
echo ""

# Ask which revision to rollback to
if [ -z "$TARGET_REVISION" ]; then
    echo "Which revision do you want to rollback to?"
    echo "(Leave empty to rollback to previous revision)"
    read -p "Target revision: " TARGET_REVISION
fi

if [ -z "$TARGET_REVISION" ]; then
    TARGET_REVISION=$((CURRENT_REVISION - 1))
    echo "Rolling back to previous revision: $TARGET_REVISION"
else
    echo "Rolling back to revision: $TARGET_REVISION"
fi

# Confirmation
echo ""
echo -e "${YELLOW}WARNING: This will rollback the release to revision $TARGET_REVISION${NC}"
echo ""
read -p "Are you sure you want to proceed? (yes/no): " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    echo "Rollback cancelled."
    exit 0
fi

echo ""
echo "Performing rollback..."
echo ""

# Perform rollback
if helm rollback "$RELEASE_NAME" "$TARGET_REVISION" -n "$NAMESPACE" --wait; then
    echo ""
    echo -e "${GREEN}✓ Rollback completed successfully${NC}"
    echo ""
    
    # Show new status
    echo "New release status:"
    helm status "$RELEASE_NAME" -n "$NAMESPACE"
    echo ""
    
    # Verify pods are running
    echo "Verifying pod status..."
    kubectl get pods -n "$NAMESPACE"
    echo ""
    
    # Check for failed pods
    FAILED_PODS=$(kubectl get pods -n "$NAMESPACE" -o json | jq -r '.items[] | select(.status.phase=="Failed") | .metadata.name')
    
    if [ -n "$FAILED_PODS" ]; then
        echo -e "${YELLOW}⚠ Warning: Some pods are in Failed state:${NC}"
        echo "$FAILED_PODS"
        echo ""
    fi
    
    # Check for pending pods
    PENDING_PODS=$(kubectl get pods -n "$NAMESPACE" -o json | jq -r '.items[] | select(.status.phase=="Pending") | .metadata.name')
    
    if [ -n "$PENDING_PODS" ]; then
        echo -e "${YELLOW}⚠ Warning: Some pods are in Pending state:${NC}"
        echo "$PENDING_PODS"
        echo ""
    fi
    
    # Show events
    echo "Recent events:"
    kubectl get events -n "$NAMESPACE" --sort-by='.lastTimestamp' | tail -20
    echo ""
    
    echo "======================================================================"
    echo "ROLLBACK COMPLETED"
    echo "======================================================================"
    echo ""
    echo "Next steps:"
    echo "  1. Monitor pod status:"
    echo "     kubectl get pods -n $NAMESPACE -w"
    echo ""
    echo "  2. Check application logs:"
    echo "     kubectl logs -n $NAMESPACE -l app.kubernetes.io/name=agent-router --tail=100"
    echo ""
    echo "  3. Verify health endpoints:"
    echo "     curl https://api.example.com/health"
    echo ""
    echo "  4. Monitor metrics:"
    echo "     kubectl port-forward -n $NAMESPACE svc/grafana 3000:3000"
    echo ""
    echo "  5. Document rollback reason:"
    echo "     - Why was rollback needed?"
    echo "     - What was the root cause?"
    echo "     - What needs to be fixed before next deployment?"
    echo ""
    
else
    echo ""
    echo -e "${RED}✗ Rollback failed${NC}"
    echo ""
    echo "Troubleshooting:"
    echo "  1. Check Helm status:"
    echo "     helm status $RELEASE_NAME -n $NAMESPACE"
    echo ""
    echo "  2. Check pod status:"
    echo "     kubectl get pods -n $NAMESPACE"
    echo ""
    echo "  3. Check events:"
    echo "     kubectl get events -n $NAMESPACE --sort-by='.lastTimestamp'"
    echo ""
    echo "  4. Check logs:"
    echo "     kubectl logs -n $NAMESPACE <pod-name>"
    echo ""
    exit 1
fi
