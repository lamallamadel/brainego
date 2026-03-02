#!/bin/bash
set -euo pipefail

# K6 Load Test Suite Runner for Staging Environment
# Executes k6 tests with SLO validation and Prometheus integration
# Fails CI if SLOs are violated: error_rate >0.5%, P99 >2s, availability <99.5%

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
K6_SCRIPT="${REPO_ROOT}/k6_load_test.js"
RESULTS_DIR="${REPO_ROOT}/load_test_results"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RESULTS_FILE="${RESULTS_DIR}/k6_results_${TIMESTAMP}.json"
SUMMARY_FILE="${RESULTS_DIR}/k6_summary_${TIMESTAMP}.txt"

# Environment configuration
STAGING_BASE_URL="${STAGING_BASE_URL:-https://api-staging.brainego.io}"
STAGING_GATEWAY_URL="${STAGING_GATEWAY_URL:-https://gateway-staging.brainego.io}"
STAGING_MCP_URL="${STAGING_MCP_URL:-https://mcp-staging.brainego.io}"
PROMETHEUS_PUSHGATEWAY="${PROMETHEUS_PUSHGATEWAY:-http://pushgateway:9091}"

# SLO thresholds
MAX_ERROR_RATE=0.005  # 0.5%
MAX_P99_LATENCY=2000  # 2000ms (2s)
MIN_AVAILABILITY=99.5 # 99.5%

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to log messages
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1" >&2
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1"
}

# Create results directory
mkdir -p "$RESULTS_DIR"

# Check if k6 is installed
if ! command -v k6 &> /dev/null; then
    error "k6 is not installed. Please install k6: https://k6.io/docs/getting-started/installation/"
    exit 1
fi

# Check if k6 script exists
if [ ! -f "$K6_SCRIPT" ]; then
    error "k6 script not found: $K6_SCRIPT"
    exit 1
fi

# Display configuration
log "K6 Load Test Suite Runner"
log "=========================="
log "Target Environment: Staging"
log "Base URL: $STAGING_BASE_URL"
log "Gateway URL: $STAGING_GATEWAY_URL"
log "MCP URL: $STAGING_MCP_URL"
log "Prometheus Pushgateway: $PROMETHEUS_PUSHGATEWAY"
log "Results Directory: $RESULTS_DIR"
log ""

# Health check before running tests
log "Performing health checks..."
health_check_failed=0

check_endpoint() {
    local url=$1
    local name=$2
    
    if curl -sf -o /dev/null -m 10 "$url/health" || curl -sf -o /dev/null -m 10 "$url"; then
        log "✓ $name is healthy"
    else
        warn "✗ $name health check failed"
        health_check_failed=1
    fi
}

check_endpoint "$STAGING_BASE_URL" "API Server"
check_endpoint "$STAGING_GATEWAY_URL" "Gateway"
check_endpoint "$STAGING_MCP_URL" "MCP Server"

if [ $health_check_failed -eq 1 ]; then
    warn "Some health checks failed, but proceeding with tests..."
    log ""
fi

# Run k6 load tests
log "Starting k6 load tests..."
log "This will take approximately 21 minutes (18m adaptive + 3m burst)"
log ""

k6_exit_code=0
k6 run \
    --out json="$RESULTS_FILE" \
    --summary-export="$RESULTS_FILE" \
    -e BASE_URL="$STAGING_BASE_URL" \
    -e GATEWAY_URL="$STAGING_GATEWAY_URL" \
    -e MCP_URL="$STAGING_MCP_URL" \
    "$K6_SCRIPT" | tee "$SUMMARY_FILE" || k6_exit_code=$?

log "K6 tests completed with exit code: $k6_exit_code"
log ""

# Parse results and validate SLOs
log "Validating SLO compliance..."

if [ ! -f "$RESULTS_FILE" ]; then
    error "Results file not found: $RESULTS_FILE"
    exit 1
fi

# Extract metrics from JSON results
error_rate=$(jq -r '.metrics.http_req_failed.values.rate // 0' "$RESULTS_FILE")
p99_latency=$(jq -r '.metrics.http_req_duration.values["p(99)"] // 0' "$RESULTS_FILE")
total_requests=$(jq -r '.metrics.http_reqs.values.count // 0' "$RESULTS_FILE")
failed_requests=$(jq -r '.metrics.http_req_failed.values.passes // 0' "$RESULTS_FILE")

# Calculate availability
availability=$(echo "scale=2; (1 - $error_rate) * 100" | bc)

# Display metrics
log "Test Results:"
log "  Total Requests: $total_requests"
log "  Failed Requests: $failed_requests"
log "  Error Rate: $(echo "scale=3; $error_rate * 100" | bc)%"
log "  P99 Latency: ${p99_latency}ms"
log "  Availability: ${availability}%"
log ""

# Validate SLOs
slo_violations=0

log "SLO Validation:"

# Check error rate
error_rate_pct=$(echo "scale=3; $error_rate * 100" | bc)
if (( $(echo "$error_rate > $MAX_ERROR_RATE" | bc -l) )); then
    error "✗ Error rate SLO violated: ${error_rate_pct}% > 0.5%"
    slo_violations=$((slo_violations + 1))
else
    log "✓ Error rate SLO passed: ${error_rate_pct}% ≤ 0.5%"
fi

# Check P99 latency
if (( $(echo "$p99_latency > $MAX_P99_LATENCY" | bc -l) )); then
    error "✗ P99 latency SLO violated: ${p99_latency}ms > 2000ms"
    slo_violations=$((slo_violations + 1))
else
    log "✓ P99 latency SLO passed: ${p99_latency}ms ≤ 2000ms"
fi

# Check availability
if (( $(echo "$availability < $MIN_AVAILABILITY" | bc -l) )); then
    error "✗ Availability SLO violated: ${availability}% < 99.5%"
    slo_violations=$((slo_violations + 1))
else
    log "✓ Availability SLO passed: ${availability}% ≥ 99.5%"
fi

log ""

# Export results to Prometheus Pushgateway
log "Exporting metrics to Prometheus Pushgateway..."

push_metrics_to_prometheus() {
    local job_name="k6_load_test"
    local instance="staging"
    
    # Create metrics in Prometheus format
    metrics=$(cat <<EOF
# TYPE k6_http_reqs_total counter
k6_http_reqs_total{environment="staging",job="load_test"} $total_requests

# TYPE k6_http_req_failed_total counter
k6_http_req_failed_total{environment="staging",job="load_test"} $failed_requests

# TYPE k6_http_req_duration_p99 gauge
k6_http_req_duration_p99{environment="staging",job="load_test"} $p99_latency

# TYPE k6_error_rate gauge
k6_error_rate{environment="staging",job="load_test"} $error_rate

# TYPE k6_availability_percent gauge
k6_availability_percent{environment="staging",job="load_test"} $availability

# TYPE k6_slo_violations_total counter
k6_slo_violations_total{environment="staging",job="load_test"} $slo_violations

# TYPE k6_test_timestamp gauge
k6_test_timestamp{environment="staging",job="load_test"} $(date +%s)
EOF
)
    
    # Push to Prometheus Pushgateway
    if curl -sf --data-binary "$metrics" "$PROMETHEUS_PUSHGATEWAY/metrics/job/$job_name/instance/$instance" &> /dev/null; then
        log "✓ Metrics exported to Prometheus Pushgateway"
    else
        warn "✗ Failed to export metrics to Prometheus Pushgateway"
        warn "  Pushgateway URL: $PROMETHEUS_PUSHGATEWAY"
        warn "  This is not a critical failure, continuing..."
    fi
}

push_metrics_to_prometheus
log ""

# Export detailed metrics for Grafana
log "Exporting detailed metrics for Grafana visualization..."

detailed_metrics=$(cat <<EOF
{
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "environment": "staging",
  "summary": {
    "total_requests": $total_requests,
    "failed_requests": $failed_requests,
    "error_rate": $error_rate,
    "p99_latency_ms": $p99_latency,
    "availability_percent": $availability,
    "slo_violations": $slo_violations
  },
  "slo_compliance": {
    "error_rate_ok": $([ "$(echo "$error_rate <= $MAX_ERROR_RATE" | bc)" -eq 1 ] && echo "true" || echo "false"),
    "p99_latency_ok": $([ "$(echo "$p99_latency <= $MAX_P99_LATENCY" | bc)" -eq 1 ] && echo "true" || echo "false"),
    "availability_ok": $([ "$(echo "$availability >= $MIN_AVAILABILITY" | bc)" -eq 1 ] && echo "true" || echo "false")
  }
}
EOF
)

echo "$detailed_metrics" > "${RESULTS_DIR}/grafana_metrics_${TIMESTAMP}.json"
log "✓ Detailed metrics saved to grafana_metrics_${TIMESTAMP}.json"
log ""

# Archive results
log "Archiving test results..."
tar -czf "${RESULTS_DIR}/k6_test_archive_${TIMESTAMP}.tar.gz" \
    -C "$RESULTS_DIR" \
    "k6_results_${TIMESTAMP}.json" \
    "k6_summary_${TIMESTAMP}.txt" \
    "grafana_metrics_${TIMESTAMP}.json" 2>/dev/null || true

log "✓ Results archived to k6_test_archive_${TIMESTAMP}.tar.gz"
log ""

# Final verdict
log "=========================="
if [ $k6_exit_code -ne 0 ]; then
    error "K6 tests failed with exit code $k6_exit_code"
    exit $k6_exit_code
elif [ $slo_violations -gt 0 ]; then
    error "SLO violations detected: $slo_violations"
    error "Load test FAILED - SLOs not met"
    exit 1
else
    log "${GREEN}✓ All SLOs passed - Load test SUCCESSFUL${NC}"
    exit 0
fi
