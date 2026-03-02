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
PROMETHEUS_PUSHGATEWAY="${PROMETHEUS_PUSHGATEWAY:-http://pushgateway.brainego.io:9091}"

# SLO thresholds (aligned with slo_definitions.yaml)
MAX_ERROR_RATE=0.005  # 0.5%
MAX_P99_LATENCY=2000  # 2000ms (2s)
MIN_AVAILABILITY=99.5 # 99.5%

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
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

info() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')] INFO:${NC} $1"
}

# Create results directory
mkdir -p "$RESULTS_DIR"

# Check if k6 is installed
if ! command -v k6 &> /dev/null; then
    error "k6 is not installed. Please install k6: https://k6.io/docs/getting-started/installation/"
    exit 1
fi

# Check if jq is installed
if ! command -v jq &> /dev/null; then
    error "jq is not installed. Required for JSON parsing."
    exit 1
fi

# Check if bc is installed
if ! command -v bc &> /dev/null; then
    error "bc is not installed. Required for calculations."
    exit 1
fi

# Check if k6 script exists
if [ ! -f "$K6_SCRIPT" ]; then
    error "k6 script not found: $K6_SCRIPT"
    exit 1
fi

# Display configuration
log "${CYAN}════════════════════════════════════════════${NC}"
log "${CYAN}  K6 Load Test Suite Runner${NC}"
log "${CYAN}════════════════════════════════════════════${NC}"
log "Target Environment: ${BLUE}Staging${NC}"
log "Base URL:           ${BLUE}$STAGING_BASE_URL${NC}"
log "Gateway URL:        ${BLUE}$STAGING_GATEWAY_URL${NC}"
log "MCP URL:            ${BLUE}$STAGING_MCP_URL${NC}"
log "Prometheus Gateway: ${BLUE}$PROMETHEUS_PUSHGATEWAY${NC}"
log "Results Directory:  ${BLUE}$RESULTS_DIR${NC}"
log "Timestamp:          ${BLUE}$TIMESTAMP${NC}"
log "${CYAN}════════════════════════════════════════════${NC}"
log ""

# Health check before running tests
log "🏥 Performing health checks..."
health_check_failed=0

check_endpoint() {
    local url=$1
    local name=$2
    
    info "Checking $name..."
    
    # Try health endpoint first, then root endpoint
    if curl -sf -o /dev/null -m 10 "$url/health" 2>/dev/null; then
        log "  ✓ $name is healthy ($url/health)"
    elif curl -sf -o /dev/null -m 10 "$url" 2>/dev/null; then
        log "  ✓ $name is accessible ($url)"
    else
        warn "  ✗ $name health check failed"
        warn "    URL: $url"
        health_check_failed=1
    fi
}

check_endpoint "$STAGING_BASE_URL" "API Server"
check_endpoint "$STAGING_GATEWAY_URL" "Gateway"
check_endpoint "$STAGING_MCP_URL" "MCP Server"

if [ $health_check_failed -eq 1 ]; then
    warn "⚠️  Some health checks failed, but proceeding with tests..."
    warn "    Tests may fail if services are not accessible."
    log ""
else
    log "✅ All health checks passed!"
    log ""
fi

# Run k6 load tests
log "🚀 Starting k6 load tests..."
log "⏱️  Estimated duration: ~21 minutes"
log "   - Standard scenarios: Run in parallel (~15 minutes)"
log "   - Adaptive load: 18 minutes (ramp to 100 users)"
log "   - Quota burst: 3 minutes (10x rate)"
log ""

k6_exit_code=0

# Run k6 with proper output handling
k6 run \
    --out json="$RESULTS_FILE" \
    --summary-export="$RESULTS_FILE" \
    -e BASE_URL="$STAGING_BASE_URL" \
    -e GATEWAY_URL="$STAGING_GATEWAY_URL" \
    -e MCP_URL="$STAGING_MCP_URL" \
    "$K6_SCRIPT" 2>&1 | tee "$SUMMARY_FILE" || k6_exit_code=$?

log ""
log "📊 K6 tests completed with exit code: $k6_exit_code"
log ""

# Check if results file was created
if [ ! -f "$RESULTS_FILE" ]; then
    error "❌ Results file not found: $RESULTS_FILE"
    error "   k6 may have failed to run or produce output"
    exit 1
fi

# Validate results file is valid JSON
if ! jq empty "$RESULTS_FILE" 2>/dev/null; then
    error "❌ Results file is not valid JSON: $RESULTS_FILE"
    exit 1
fi

# Parse results and validate SLOs
log "📈 Validating SLO compliance..."
log ""

# Extract metrics from JSON results
error_rate=$(jq -r '.metrics.http_req_failed.values.rate // 0' "$RESULTS_FILE")
p99_latency=$(jq -r '.metrics.http_req_duration.values["p(99)"] // 0' "$RESULTS_FILE")
p95_latency=$(jq -r '.metrics.http_req_duration.values["p(95)"] // 0' "$RESULTS_FILE")
p50_latency=$(jq -r '.metrics.http_req_duration.values["p(50)"] // 0' "$RESULTS_FILE")
total_requests=$(jq -r '.metrics.http_reqs.values.count // 0' "$RESULTS_FILE")
failed_requests=$(jq -r '.metrics.http_req_failed.values.passes // 0' "$RESULTS_FILE")

# Validate metrics are numeric
if ! [[ "$error_rate" =~ ^[0-9.]+$ ]] || ! [[ "$p99_latency" =~ ^[0-9.]+$ ]]; then
    error "❌ Failed to extract valid metrics from results"
    error "   error_rate: $error_rate"
    error "   p99_latency: $p99_latency"
    exit 1
fi

# Calculate availability
availability=$(echo "scale=2; (1 - $error_rate) * 100" | bc)
error_rate_pct=$(echo "scale=3; $error_rate * 100" | bc)

# Display metrics
log "${CYAN}════════════════════════════════════════════${NC}"
log "${CYAN}  Test Results${NC}"
log "${CYAN}════════════════════════════════════════════${NC}"
log "Total Requests:     ${BLUE}$total_requests${NC}"
log "Failed Requests:    ${BLUE}$failed_requests${NC}"
log "Error Rate:         ${BLUE}${error_rate_pct}%${NC}"
log "P50 Latency:        ${BLUE}${p50_latency}ms${NC}"
log "P95 Latency:        ${BLUE}${p95_latency}ms${NC}"
log "P99 Latency:        ${BLUE}${p99_latency}ms${NC}"
log "Availability:       ${BLUE}${availability}%${NC}"
log "${CYAN}════════════════════════════════════════════${NC}"
log ""

# Validate SLOs
slo_violations=0

log "${CYAN}════════════════════════════════════════════${NC}"
log "${CYAN}  SLO Validation${NC}"
log "${CYAN}════════════════════════════════════════════${NC}"

# Check error rate SLO (< 0.5%)
if (( $(echo "$error_rate > $MAX_ERROR_RATE" | bc -l) )); then
    error "❌ Error Rate SLO VIOLATED"
    error "   Actual:    ${error_rate_pct}%"
    error "   Threshold: ≤ 0.5%"
    error "   Impact:    System reliability below acceptable threshold"
    slo_violations=$((slo_violations + 1))
else
    log "✅ Error Rate SLO PASSED: ${error_rate_pct}% ≤ 0.5%"
fi

# Check P99 latency SLO (< 2000ms)
if (( $(echo "$p99_latency > $MAX_P99_LATENCY" | bc -l) )); then
    error "❌ P99 Latency SLO VIOLATED"
    error "   Actual:    ${p99_latency}ms"
    error "   Threshold: ≤ 2000ms"
    error "   Impact:    Poor user experience for tail latency"
    slo_violations=$((slo_violations + 1))
else
    log "✅ P99 Latency SLO PASSED: ${p99_latency}ms ≤ 2000ms"
fi

# Check availability SLO (> 99.5%)
if (( $(echo "$availability < $MIN_AVAILABILITY" | bc -l) )); then
    error "❌ Availability SLO VIOLATED"
    error "   Actual:    ${availability}%"
    error "   Threshold: ≥ 99.5%"
    error "   Impact:    Unacceptable downtime affecting users"
    slo_violations=$((slo_violations + 1))
else
    log "✅ Availability SLO PASSED: ${availability}% ≥ 99.5%"
fi

log "${CYAN}════════════════════════════════════════════${NC}"
log ""

# Export results to Prometheus Pushgateway
log "📤 Exporting metrics to Prometheus Pushgateway..."

push_metrics_to_prometheus() {
    local job_name="k6_load_test"
    local instance="staging"
    local timestamp=$(date +%s)
    
    # Create metrics in Prometheus format
    metrics=$(cat <<EOF
# TYPE k6_http_reqs_total counter
k6_http_reqs_total{environment="staging",job="load_test"} $total_requests $timestamp

# TYPE k6_http_req_failed_total counter
k6_http_req_failed_total{environment="staging",job="load_test"} $failed_requests $timestamp

# TYPE k6_http_req_duration_p50 gauge
k6_http_req_duration_p50{environment="staging",job="load_test"} $p50_latency $timestamp

# TYPE k6_http_req_duration_p95 gauge
k6_http_req_duration_p95{environment="staging",job="load_test"} $p95_latency $timestamp

# TYPE k6_http_req_duration_p99 gauge
k6_http_req_duration_p99{environment="staging",job="load_test"} $p99_latency $timestamp

# TYPE k6_error_rate gauge
k6_error_rate{environment="staging",job="load_test"} $error_rate $timestamp

# TYPE k6_availability_percent gauge
k6_availability_percent{environment="staging",job="load_test"} $availability $timestamp

# TYPE k6_slo_violations_total counter
k6_slo_violations_total{environment="staging",job="load_test"} $slo_violations $timestamp

# TYPE k6_test_timestamp gauge
k6_test_timestamp{environment="staging",job="load_test"} $timestamp $timestamp
EOF
)
    
    # Push to Prometheus Pushgateway
    if echo "$metrics" | curl -sf --data-binary @- "$PROMETHEUS_PUSHGATEWAY/metrics/job/$job_name/instance/$instance" &> /dev/null; then
        log "✅ Metrics successfully exported to Prometheus Pushgateway"
        info "   Job:      $job_name"
        info "   Instance: $instance"
        info "   Gateway:  $PROMETHEUS_PUSHGATEWAY"
    else
        warn "⚠️  Failed to export metrics to Prometheus Pushgateway"
        warn "   Gateway URL: $PROMETHEUS_PUSHGATEWAY"
        warn "   This is not a critical failure, continuing..."
        
        # Try to diagnose the issue
        if command -v nc &> /dev/null; then
            local host=$(echo "$PROMETHEUS_PUSHGATEWAY" | sed -e 's|http[s]*://||' -e 's|:.*||')
            local port=$(echo "$PROMETHEUS_PUSHGATEWAY" | sed -e 's|.*:||' -e 's|/.*||')
            if ! nc -z -w5 "$host" "$port" 2>/dev/null; then
                warn "   Pushgateway is not accessible at $host:$port"
            fi
        fi
    fi
}

push_metrics_to_prometheus
log ""

# Export detailed metrics for Grafana
log "📊 Exporting detailed metrics for Grafana visualization..."

detailed_metrics=$(cat <<EOF
{
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "environment": "staging",
  "test_run": {
    "id": "$TIMESTAMP",
    "duration_seconds": $(jq -r '.state.testRunDurationMs // 0' "$RESULTS_FILE" | awk '{print $1/1000}'),
    "k6_version": "$(k6 version 2>/dev/null | head -n1 || echo 'unknown')"
  },
  "summary": {
    "total_requests": $total_requests,
    "failed_requests": $failed_requests,
    "error_rate": $error_rate,
    "error_rate_percent": $error_rate_pct,
    "p50_latency_ms": $p50_latency,
    "p95_latency_ms": $p95_latency,
    "p99_latency_ms": $p99_latency,
    "availability_percent": $availability,
    "slo_violations": $slo_violations
  },
  "slo_compliance": {
    "error_rate_ok": $([ "$(echo "$error_rate <= $MAX_ERROR_RATE" | bc -l)" -eq 1 ] && echo "true" || echo "false"),
    "p99_latency_ok": $([ "$(echo "$p99_latency <= $MAX_P99_LATENCY" | bc -l)" -eq 1 ] && echo "true" || echo "false"),
    "availability_ok": $([ "$(echo "$availability >= $MIN_AVAILABILITY" | bc -l)" -eq 1 ] && echo "true" || echo "false")
  },
  "thresholds": {
    "max_error_rate": $MAX_ERROR_RATE,
    "max_error_rate_percent": 0.5,
    "max_p99_latency_ms": $MAX_P99_LATENCY,
    "min_availability_percent": $MIN_AVAILABILITY
  },
  "endpoints": {
    "base_url": "$STAGING_BASE_URL",
    "gateway_url": "$STAGING_GATEWAY_URL",
    "mcp_url": "$STAGING_MCP_URL"
  }
}
EOF
)

echo "$detailed_metrics" > "${RESULTS_DIR}/grafana_metrics_${TIMESTAMP}.json"
log "✅ Detailed metrics saved to grafana_metrics_${TIMESTAMP}.json"
log ""

# Archive results
log "📦 Archiving test results..."

archive_file="${RESULTS_DIR}/k6_test_archive_${TIMESTAMP}.tar.gz"

if tar -czf "$archive_file" \
    -C "$RESULTS_DIR" \
    "k6_results_${TIMESTAMP}.json" \
    "k6_summary_${TIMESTAMP}.txt" \
    "grafana_metrics_${TIMESTAMP}.json" 2>/dev/null; then
    log "✅ Results archived to k6_test_archive_${TIMESTAMP}.tar.gz"
    info "   Archive size: $(du -h "$archive_file" | cut -f1)"
else
    warn "⚠️  Failed to create archive (non-critical)"
fi

log ""

# Final verdict
log "${CYAN}════════════════════════════════════════════${NC}"

if [ $k6_exit_code -ne 0 ]; then
    error "${RED}❌ K6 TESTS FAILED${NC}"
    error "   Exit code: $k6_exit_code"
    error "   Check logs above for details"
    log "${CYAN}════════════════════════════════════════════${NC}"
    exit $k6_exit_code
elif [ $slo_violations -gt 0 ]; then
    error "${RED}❌ LOAD TEST FAILED - SLO VIOLATIONS DETECTED${NC}"
    error "   Violations: $slo_violations"
    error ""
    error "   Review the following:"
    error "   • Application logs for errors"
    error "   • Infrastructure metrics (CPU, memory, network)"
    error "   • Database and cache performance"
    error "   • Recent deployments or config changes"
    log "${CYAN}════════════════════════════════════════════${NC}"
    exit 1
else
    log "${GREEN}✅ ALL SLOS PASSED - LOAD TEST SUCCESSFUL${NC}"
    log ""
    log "   Summary:"
    log "   • Error Rate:   ${error_rate_pct}% ≤ 0.5% ✓"
    log "   • P99 Latency:  ${p99_latency}ms ≤ 2000ms ✓"
    log "   • Availability: ${availability}% ≥ 99.5% ✓"
    log ""
    log "   System is performing within acceptable limits."
    log "${CYAN}════════════════════════════════════════════${NC}"
    exit 0
fi
