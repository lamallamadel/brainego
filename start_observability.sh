#!/bin/bash
# Start Observability Stack
# This script starts all observability services

set -e

echo "=== Starting AI Platform Observability Stack ==="

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "Error: Docker is not running"
    exit 1
fi

# Create required directories
echo "Creating directories..."
mkdir -p configs/prometheus/rules
mkdir -p configs/alertmanager
mkdir -p configs/otel-collector
mkdir -p configs/loki
mkdir -p configs/promtail

# Check for .env.observability
if [ ! -f .env.observability ]; then
    echo "Warning: .env.observability not found. Creating from example..."
    cp .env.observability.example .env.observability
    echo "Please edit .env.observability with your Slack webhook URL"
fi

# Load environment variables
if [ -f .env.observability ]; then
    export $(cat .env.observability | grep -v '^#' | xargs)
fi

# Start observability services
echo "Starting observability services..."
docker compose up -d \
    prometheus \
    grafana \
    loki \
    promtail \
    alertmanager \
    otel-collector \
    redis-exporter \
    postgres-exporter \
    nvidia-gpu-exporter

# Wait for services to be healthy
echo "Waiting for services to be healthy..."
sleep 10

# Check service health
echo "Checking service health..."

check_service() {
    local service=$1
    local url=$2
    
    if curl -f -s "$url" > /dev/null 2>&1; then
        echo "✓ $service is healthy"
        return 0
    else
        echo "✗ $service is not healthy"
        return 1
    fi
}

check_service "Prometheus" "http://localhost:9090/-/healthy"
check_service "Grafana" "http://localhost:3000/api/health"
check_service "Loki" "http://localhost:3100/ready"
check_service "AlertManager" "http://localhost:9093/-/healthy"
check_service "OpenTelemetry Collector" "http://localhost:13133"

echo ""
echo "=== Observability Stack Started ==="
echo ""
echo "Access dashboards at:"
echo "  Prometheus:   http://localhost:9090"
echo "  Grafana:      http://localhost:3000 (admin/admin)"
echo "  Jaeger:       http://localhost:16686"
echo "  AlertManager: http://localhost:9093"
echo ""
echo "Check logs with: docker compose logs -f <service>"
echo "Stop with: docker compose stop prometheus grafana loki promtail alertmanager otel-collector"
echo ""

# Show Prometheus targets
echo "Prometheus targets status:"
curl -s http://localhost:9090/api/v1/targets | \
    jq -r '.data.activeTargets[] | "\(.labels.job): \(.health)"' 2>/dev/null || \
    echo "Prometheus API not ready yet. Check http://localhost:9090/targets"

echo ""
echo "=== Setup Complete ==="
