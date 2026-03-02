#!/bin/bash
# One-Click Blue-Green Rollback Script
#
# Immediately rolls back traffic to blue environment in case of emergency
#
# Usage:
#   ./rollback_blue_green.sh <namespace> <service-name>
#
# Example:
#   ./rollback_blue_green.sh ai-platform-prod agent-router

set -euo pipefail

NAMESPACE="${1:-}"
SERVICE_NAME="${2:-}"

if [ -z "$NAMESPACE" ] || [ -z "$SERVICE_NAME" ]; then
    echo "ERROR: Missing required arguments"
    echo ""
    echo "Usage: $0 <namespace> <service-name>"
    echo ""
    echo "Example:"
    echo "  $0 ai-platform-prod agent-router"
    exit 1
fi

INGRESS_NAME="${SERVICE_NAME}-green-canary"

echo "============================================"
echo "BLUE-GREEN ROLLBACK"
echo "============================================"
echo "Namespace: $NAMESPACE"
echo "Service: $SERVICE_NAME"
echo "Ingress: $INGRESS_NAME"
echo "============================================"
echo ""

read -p "Are you sure you want to rollback to blue environment? (yes/no): " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    echo "Rollback cancelled"
    exit 0
fi

echo ""
echo "Step 1/4: Setting green traffic weight to 0%..."
kubectl annotate ingress "$INGRESS_NAME" \
  nginx.ingress.kubernetes.io/canary-weight=0 \
  -n "$NAMESPACE" \
  --overwrite

if [ $? -ne 0 ]; then
    echo "ERROR: Failed to update ingress annotation"
    exit 1
fi

echo "✓ Traffic weight updated"
echo ""

echo "Step 2/4: Verifying traffic split..."
WEIGHT=$(kubectl get ingress "$INGRESS_NAME" -n "$NAMESPACE" -o jsonpath='{.metadata.annotations.nginx\.ingress\.kubernetes\.io/canary-weight}')
echo "Current green traffic weight: $WEIGHT%"

if [ "$WEIGHT" = "0" ]; then
    echo "✓ Rollback successful - 100% traffic on blue"
else
    echo "⚠ WARNING: Traffic weight is not 0%, got $WEIGHT%"
fi

echo ""
echo "Step 3/4: Checking blue environment health..."
BLUE_READY=$(kubectl get pods -n "$NAMESPACE" -l "app.kubernetes.io/name=$SERVICE_NAME,app.kubernetes.io/environment=blue" -o jsonpath='{.items[?(@.status.phase=="Running")].metadata.name}' | wc -w)
BLUE_TOTAL=$(kubectl get pods -n "$NAMESPACE" -l "app.kubernetes.io/name=$SERVICE_NAME,app.kubernetes.io/environment=blue" -o jsonpath='{.items[*].metadata.name}' | wc -w)

echo "Blue pods: $BLUE_READY/$BLUE_TOTAL ready"

if [ "$BLUE_READY" -eq "$BLUE_TOTAL" ] && [ "$BLUE_TOTAL" -gt 0 ]; then
    echo "✓ Blue environment is healthy"
else
    echo "⚠ WARNING: Blue environment may have issues"
    kubectl get pods -n "$NAMESPACE" -l "app.kubernetes.io/name=$SERVICE_NAME,app.kubernetes.io/environment=blue"
fi

echo ""
echo "Step 4/4: Checking green environment status..."
GREEN_READY=$(kubectl get pods -n "$NAMESPACE" -l "app.kubernetes.io/name=$SERVICE_NAME,app.kubernetes.io/environment=green" -o jsonpath='{.items[?(@.status.phase=="Running")].metadata.name}' | wc -w)
GREEN_TOTAL=$(kubectl get pods -n "$NAMESPACE" -l "app.kubernetes.io/name=$SERVICE_NAME,app.kubernetes.io/environment=green" -o jsonpath='{.items[*].metadata.name}' | wc -w)

echo "Green pods: $GREEN_READY/$GREEN_TOTAL ready"
echo ""

echo "============================================"
echo "ROLLBACK COMPLETE"
echo "============================================"
echo ""
echo "Next steps:"
echo "1. Monitor blue environment metrics"
echo "2. Investigate green environment issues"
echo "3. Fix issues in green environment"
echo "4. Re-deploy when ready"
echo ""
echo "To monitor traffic:"
echo "  watch 'kubectl get ingress $INGRESS_NAME -n $NAMESPACE -o yaml | grep canary-weight'"
echo ""
echo "To view blue pod logs:"
echo "  kubectl logs -n $NAMESPACE -l app.kubernetes.io/name=$SERVICE_NAME,app.kubernetes.io/environment=blue --tail=100"
echo ""
echo "To view green pod logs:"
echo "  kubectl logs -n $NAMESPACE -l app.kubernetes.io/name=$SERVICE_NAME,app.kubernetes.io/environment=green --tail=100"
echo ""
