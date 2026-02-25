#!/bin/bash
# Test Observability Stack
# This script tests metrics, logs, and traces

set -e

echo "=== Testing AI Platform Observability Stack ==="

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test function
test_endpoint() {
    local name=$1
    local url=$2
    local expected=$3
    
    echo -n "Testing $name... "
    
    if response=$(curl -s -f "$url" 2>&1); then
        if [ -z "$expected" ] || echo "$response" | grep -q "$expected"; then
            echo -e "${GREEN}✓${NC}"
            return 0
        else
            echo -e "${RED}✗ (unexpected response)${NC}"
            return 1
        fi
    else
        echo -e "${RED}✗ (connection failed)${NC}"
        return 1
    fi
}

# Test Prometheus
echo ""
echo "=== Testing Prometheus ==="
test_endpoint "Prometheus health" "http://localhost:9090/-/healthy" ""
test_endpoint "Prometheus targets" "http://localhost:9090/api/v1/targets" "activeTargets"
test_endpoint "Prometheus metrics" "http://localhost:9090/api/v1/label/__name__/values" "up"

# Test Grafana
echo ""
echo "=== Testing Grafana ==="
test_endpoint "Grafana health" "http://localhost:3000/api/health" "ok"

# Test Loki
echo ""
echo "=== Testing Loki ==="
test_endpoint "Loki health" "http://localhost:3100/ready" "ready"
test_endpoint "Loki metrics" "http://localhost:3100/metrics" "loki_"

# Test AlertManager
echo ""
echo "=== Testing AlertManager ==="
test_endpoint "AlertManager health" "http://localhost:9093/-/healthy" ""
test_endpoint "AlertManager status" "http://localhost:9093/api/v2/status" "uptime"

# Test OpenTelemetry Collector
echo ""
echo "=== Testing OpenTelemetry Collector ==="
test_endpoint "OTel Collector health" "http://localhost:13133" ""
test_endpoint "OTel Collector metrics" "http://localhost:8888/metrics" "otelcol_"

# Test Exporters
echo ""
echo "=== Testing Exporters ==="
test_endpoint "Redis Exporter" "http://localhost:9121/metrics" "redis_"
test_endpoint "PostgreSQL Exporter" "http://localhost:9187/metrics" "pg_"
test_endpoint "GPU Exporter" "http://localhost:9835/metrics" "nvidia_" || echo -e "${YELLOW}Note: GPU exporter requires NVIDIA GPU${NC}"

# Test Prometheus Targets
echo ""
echo "=== Checking Prometheus Targets ==="
if targets=$(curl -s http://localhost:9090/api/v1/targets); then
    active=$(echo "$targets" | jq -r '.data.activeTargets | length')
    healthy=$(echo "$targets" | jq -r '[.data.activeTargets[] | select(.health == "up")] | length')
    
    echo "Total targets: $active"
    echo "Healthy targets: $healthy"
    
    if [ "$healthy" -eq "$active" ]; then
        echo -e "${GREEN}All targets are healthy ✓${NC}"
    else
        echo -e "${YELLOW}Warning: Some targets are unhealthy${NC}"
        echo "$targets" | jq -r '.data.activeTargets[] | select(.health != "up") | "\(.labels.job): \(.health)"'
    fi
else
    echo -e "${RED}Failed to get Prometheus targets${NC}"
fi

# Test Alert Rules
echo ""
echo "=== Checking Alert Rules ==="
if rules=$(curl -s http://localhost:9090/api/v1/rules); then
    total_rules=$(echo "$rules" | jq -r '[.data.groups[].rules[]] | length')
    alerting_rules=$(echo "$rules" | jq -r '[.data.groups[].rules[] | select(.type == "alerting")] | length')
    
    echo "Total alert rules: $alerting_rules"
    
    if [ "$alerting_rules" -gt 0 ]; then
        echo -e "${GREEN}Alert rules loaded ✓${NC}"
    else
        echo -e "${YELLOW}Warning: No alert rules loaded${NC}"
    fi
else
    echo -e "${RED}Failed to get alert rules${NC}"
fi

# Test Loki Ingestion
echo ""
echo "=== Testing Loki Log Ingestion ==="
if logs=$(curl -s -G "http://localhost:3100/loki/api/v1/query" \
    --data-urlencode 'query={job=~".+"}' \
    --data-urlencode 'limit=1'); then
    
    streams=$(echo "$logs" | jq -r '.data.result | length')
    
    if [ "$streams" -gt 0 ]; then
        echo -e "${GREEN}Logs are being ingested ✓${NC}"
        echo "Active log streams: $streams"
    else
        echo -e "${YELLOW}Warning: No logs found yet (may take a few minutes)${NC}"
    fi
else
    echo -e "${RED}Failed to query Loki${NC}"
fi

# Test Jaeger
echo ""
echo "=== Testing Jaeger ==="
test_endpoint "Jaeger health" "http://localhost:16686" "Jaeger"

# Summary
echo ""
echo "=== Test Summary ==="
echo ""
echo "Access dashboards:"
echo "  Prometheus:   http://localhost:9090"
echo "  Grafana:      http://localhost:3000 (admin/admin)"
echo "  Jaeger:       http://localhost:16686"
echo "  AlertManager: http://localhost:9093"
echo ""
echo "Test queries:"
echo ""
echo "Prometheus (HTTP request rate):"
echo "  rate(http_requests_total[5m])"
echo ""
echo "Loki (error logs):"
echo '  {job="gateway"} |= "ERROR"'
echo ""
echo "Check service logs:"
echo "  docker compose logs -f prometheus"
echo "  docker compose logs -f loki"
echo "  docker compose logs -f otel-collector"
echo ""

# Provide sample queries
echo "=== Sample Metrics Queries ==="
echo ""
echo "1. Request rate by service:"
echo "   sum(rate(http_requests_total[5m])) by (job)"
echo ""
echo "2. P95 latency:"
echo "   histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))"
echo ""
echo "3. Error rate:"
echo '   rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m]) * 100'
echo ""
echo "4. GPU utilization:"
echo "   nvidia_gpu_duty_cycle"
echo ""
echo "5. Drift score:"
echo "   drift_score"
echo ""

echo "=== Testing Complete ==="
