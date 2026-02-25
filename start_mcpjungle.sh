#!/bin/bash
# Startup script for MCPJungle Gateway

set -e

echo "========================================"
echo "    MCPJungle Gateway Startup"
echo "========================================"

# Check required environment variables
echo "Checking environment variables..."
if [ -z "$QDRANT_HOST" ]; then
    echo "Warning: QDRANT_HOST not set, using default: localhost"
    export QDRANT_HOST=localhost
fi

if [ -z "$REDIS_HOST" ]; then
    echo "Warning: REDIS_HOST not set, using default: localhost"
    export REDIS_HOST=localhost
fi

if [ -z "$MAX_SERVE_URL" ]; then
    echo "Warning: MAX_SERVE_URL not set, using default: http://localhost:8080"
    export MAX_SERVE_URL=http://localhost:8080
fi

# Check if configs exist
if [ ! -f "configs/mcp-servers.yaml" ]; then
    echo "Error: configs/mcp-servers.yaml not found!"
    exit 1
fi

if [ ! -f "configs/mcp-acl.yaml" ]; then
    echo "Error: configs/mcp-acl.yaml not found!"
    exit 1
fi

echo "✓ Configuration files found"

# Create workspace directory if it doesn't exist
mkdir -p workspace
echo "✓ Workspace directory ready"

# Check Node.js availability (required for MCP servers)
if command -v node &> /dev/null; then
    echo "✓ Node.js version: $(node --version)"
    echo "✓ npm version: $(npm --version)"
else
    echo "Warning: Node.js not found. MCP servers may not work properly."
fi

# Display configuration
echo ""
echo "Configuration:"
echo "  MAX Serve URL: $MAX_SERVE_URL"
echo "  Qdrant: $QDRANT_HOST:$QDRANT_PORT"
echo "  Redis: $REDIS_HOST:$REDIS_PORT"
echo "  Telemetry: ${ENABLE_TELEMETRY:-true}"
echo "  OTLP Endpoint: ${OTLP_ENDPOINT:-http://localhost:4317}"
echo "  Jaeger Endpoint: ${JAEGER_ENDPOINT:-localhost:6831}"
echo "  Port: 9100"
echo ""

echo "Starting MCPJungle Gateway..."
echo "========================================"

# Start the gateway service
python gateway_service_mcp.py
