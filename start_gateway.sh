#!/bin/bash
# Quick start script for API Gateway Service

set -e

echo "======================================"
echo "AI Platform API Gateway - Quick Start"
echo "======================================"
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}Error: Docker is not running${NC}"
    exit 1
fi

echo "Step 1: Building gateway service..."
docker compose build gateway

echo ""
echo "Step 2: Starting services..."
docker compose up -d gateway

echo ""
echo "Step 3: Waiting for services to be healthy..."
sleep 5

# Wait for gateway to be healthy
MAX_RETRIES=30
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if curl -s http://localhost:9000/health > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Gateway is healthy!${NC}"
        break
    fi
    
    RETRY_COUNT=$((RETRY_COUNT + 1))
    if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
        echo -e "${RED}✗ Gateway failed to start${NC}"
        echo "Check logs with: docker compose logs gateway"
        exit 1
    fi
    
    echo "Waiting for gateway... ($RETRY_COUNT/$MAX_RETRIES)"
    sleep 2
done

echo ""
echo -e "${GREEN}======================================"
echo "Gateway Service Started Successfully!"
echo "======================================${NC}"
echo ""
echo "Gateway URL: http://localhost:9000"
echo "Health check: http://localhost:9000/health"
echo "API docs: http://localhost:9000/docs"
echo ""
echo "Default API Keys:"
echo "  - sk-test-key-123"
echo "  - sk-admin-key-456"
echo "  - sk-dev-key-789"
echo ""
echo "Test the gateway:"
echo '  curl -X POST http://localhost:9000/v1/chat \'
echo '    -H "Authorization: Bearer sk-test-key-123" \'
echo '    -H "Content-Type: application/json" \'
echo '    -d '\''{"messages": [{"role": "user", "content": "Hello!"}]}'\'''
echo ""
echo "Run end-to-end tests:"
echo "  python test_gateway.py"
echo ""
echo -e "${YELLOW}View logs:${NC}"
echo "  docker compose logs -f gateway"
echo ""
echo -e "${YELLOW}Stop gateway:${NC}"
echo "  docker compose stop gateway"
echo ""
