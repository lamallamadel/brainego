#!/bin/bash
# Health check for MAX Serve endpoint
# Tests the /health endpoint directly (offline, no web search)
# Usage: bash scripts/max-health-check.sh [timeout_seconds]

set -e

TIMEOUT=${1:-30}
HOST=${MAX_HOST:-localhost}
PORT=${MAX_PORT:-8080}
ENDPOINT="http://$HOST:$PORT/health"

echo "🔍 Checking MAX Serve /health endpoint..."
echo "   Endpoint: $ENDPOINT"
echo "   Timeout: ${TIMEOUT}s"
echo ""

elapsed=0
interval=2

while [ $elapsed -lt $TIMEOUT ]; do
    if curl -s -f "$ENDPOINT" >/dev/null 2>&1; then
        echo "✅ MAX Serve /health endpoint is responding (status: 200)"
        echo ""
        curl -s "$ENDPOINT" | python -m json.tool 2>/dev/null || curl -s "$ENDPOINT"
        exit 0
    fi
    
    echo "⏳ Waiting for MAX Serve... ($elapsed/$TIMEOUT s)"
    sleep $interval
    elapsed=$((elapsed + interval))
done

echo ""
echo "❌ MAX Serve /health endpoint not responding after $TIMEOUT seconds"
echo ""
echo "Debugging:"
echo "  - Check if MAX Serve container is running: docker compose ps"
echo "  - View logs: docker compose logs max-serve-llama"
echo "  - Test connectivity: curl -v http://localhost:8080/health"
exit 1
