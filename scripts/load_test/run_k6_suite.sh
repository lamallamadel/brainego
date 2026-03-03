#!/bin/bash
set -euo pipefail

# K6 Load Test Suite Runner for Staging Environment
# Executes k6 tests with endpoint-specific SLO validation and Prometheus integration
# Validates: success_ratio >= 99.5%, error_rate < 0.5%, P99 < 2s (non-LLM), P99 < 8s (chat)

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
K6_ABORT_ON_HEALTHCHECK_FAILURE="${K6_ABORT_ON_HEALTHCHECK_FAILURE:-true}"
K6_FORCE_RUN="${K6_FORCE_RUN:-false}"

# SLO thresholds (aligned with slo_definitions.yaml)
MAX_ERROR_RATE=0.005  # 0.5%
MIN_SUCCESS_RATIO=99.5 # 99.5%
MAX_P99_NON_LLM=2000  # 2000ms (2s) for health, rag, mcp/tools
MAX_P99_CHAT=8000     # 8000ms (8s) for chat endpoints

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

extract_host() {
    local url=$1
    local without_scheme="${url#*://}"
    echo "${without_scheme%%/*}" | cut -d: -f1
}

dns_resolves() {
    local host=$1
    if command -v getent &>/dev/null; then
        getent hosts "$host" >/dev/null 2>&1
        return $?
    fi
    if command -v nslookup &>/dev/null; then
        nslookup "$host" >/dev/null 2>&1
        return $?
    fi
    return 0
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

# DNS preflight (fail-fast to avoid long k6 loops on NXDOMAIN)
dns_failed=0
for endpoint in "$STAGING_BASE_URL" "$STAGING_GATEWAY_URL" "$STAGING_MCP_URL"; do
    host=$(extract_host "$endpoint")
    if dns_resolves "$host"; then
        info "DNS resolved: $host"
    else
        warn "DNS lookup failed for host: $host"
        dns_failed=1
    fi
done

if [ $dns_failed -eq 1 ] && [ "$K6_FORCE_RUN" != "true" ]; then
    error "❌ DNS preflight failed (no such host). Aborting load test early."
    error "   Set K6_FORCE_RUN=true to override."
    exit 2
fi

if [ $health_check_failed -eq 1 ]; then
    if [ "$K6_ABORT_ON_HEALTHCHECK_FAILURE" = "true" ] && [ "$K6_FORCE_RUN" != "true" ]; then
        error "❌ Health checks failed and fail-fast is enabled. Aborting load test early."
        error "   Set K6_ABORT_ON_HEALTHCHECK_FAILURE=false or K6_FORCE_RUN=true to override."
        exit 3
    fi
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
log ""

k6_exit_code=0

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

# Extract overall metrics
total_requests=$(jq -r '.metrics.http_reqs.values.count // 0' "$RESULTS_FILE")
failed_requests=$(jq -r '.metrics.http_req_failed.values.passes // 0' "$RESULTS_FILE")
error_rate=$(jq -r '.metrics.http_req_failed.values.rate // 0' "$RESULTS_FILE")

# Calculate success ratio
if [ "$total_requests" -gt 0 ]; then
    success_ratio=$(echo "scale=2; (($total_requests - $failed_requests) / $total_requests) * 100" | bc)
else
    success_ratio="0"
fi

error_rate_pct=$(echo "scale=3; $error_rate * 100" | bc)

# Extract endpoint-specific metrics
chat_p99=$(jq -r '.metrics["http_req_duration{scenario:chat}"].values["p(99)"] // 0' "$RESULTS_FILE")
chat_p95=$(jq -r '.metrics["http_req_duration{scenario:chat}"].values["p(95)"] // 0' "$RESULTS_FILE")
chat_p50=$(jq -r '.metrics["http_req_duration{scenario:chat}"].values["p(50)"] // 0' "$RESULTS_FILE")
chat_error_rate=$(jq -r '.metrics.chat_errors.values.rate // 0' "$RESULTS_FILE")

rag_p99=$(jq -r '.metrics["http_req_duration{scenario:rag}"].values["p(99)"] // 0' "$RESULTS_FILE")
rag_p95=$(jq -r '.metrics["http_req_duration{scenario:rag}"].values["p(95)"] // 0' "$RESULTS_FILE")
rag_p50=$(jq -r '.metrics["http_req_duration{scenario:rag}"].values["p(50)"] // 0' "$RESULTS_FILE")
rag_error_rate=$(jq -r '.metrics.rag_errors.values.rate // 0' "$RESULTS_FILE")

mcp_p99=$(jq -r '.metrics["http_req_duration{scenario:mcp}"].values["p(99)"] // 0' "$RESULTS_FILE")
mcp_p95=$(jq -r '.metrics["http_req_duration{scenario:mcp}"].values["p(95)"] // 0' "$RESULTS_FILE")
mcp_p50=$(jq -r '.metrics["http_req_duration{scenario:mcp}"].values["p(50)"] // 0' "$RESULTS_FILE")
mcp_error_rate=$(jq -r '.metrics.mcp_errors.values.rate // 0' "$RESULTS_FILE")

# Get overall latencies
overall_p99=$(jq -r '.metrics.http_req_duration.values["p(99)"] // 0' "$RESULTS_FILE")
overall_p95=$(jq -r '.metrics.http_req_duration.values["p(95)"] // 0' "$RESULTS_FILE")
overall_p50=$(jq -r '.metrics.http_req_duration.values["p(50)"] // 0' "$RESULTS_FILE")

# Display metrics
log "${CYAN}════════════════════════════════════════════${NC}"
log "${CYAN}  Test Results${NC}"
log "${CYAN}════════════════════════════════════════════${NC}"
log "Total Requests:     ${BLUE}$total_requests${NC}"
log "Failed Requests:    ${BLUE}$failed_requests${NC}"
log "Error Rate:         ${BLUE}${error_rate_pct}%${NC}"
log "Success Ratio:      ${BLUE}${success_ratio}%${NC}"
log ""
log "Overall Latencies:"
log "  P50: ${BLUE}${overall_p50}ms${NC}"
log "  P95: ${BLUE}${overall_p95}ms${NC}"
log "  P99: ${BLUE}${overall_p99}ms${NC}"
log ""
log "Chat Endpoint (/v1/chat):"
log "  P50: ${BLUE}${chat_p50}ms${NC}"
log "  P95: ${BLUE}${chat_p95}ms${NC}"
log "  P99: ${BLUE}${chat_p99}ms${NC}"
log "  Error Rate: ${BLUE}$(echo "scale=3; $chat_error_rate * 100" | bc)%${NC}"
log ""
log "RAG Endpoints (/v1/rag/*):"
log "  P50: ${BLUE}${rag_p50}ms${NC}"
log "  P95: ${BLUE}${rag_p95}ms${NC}"
log "  P99: ${BLUE}${rag_p99}ms${NC}"
log "  Error Rate: ${BLUE}$(echo "scale=3; $rag_error_rate * 100" | bc)%${NC}"
log ""
log "MCP/Tools Endpoints (/internal/mcp/tools/*):"
log "  P50: ${BLUE}${mcp_p50}ms${NC}"
log "  P95: ${BLUE}${mcp_p95}ms${NC}"
log "  P99: ${BLUE}${mcp_p99}ms${NC}"
log "  Error Rate: ${BLUE}$(echo "scale=3; $mcp_error_rate * 100" | bc)%${NC}"
log "${CYAN}════════════════════════════════════════════${NC}"
log ""

# Validate SLOs
slo_violations=0
violation_details=""

log "${CYAN}════════════════════════════════════════════${NC}"
log "${CYAN}  SLO Validation${NC}"
log "${CYAN}════════════════════════════════════════════${NC}"

# Check success ratio SLO (>= 99.5%)
if (( $(echo "$success_ratio < $MIN_SUCCESS_RATIO" | bc -l) )); then
    error "❌ Success Ratio SLO VIOLATED"
    error "   Actual:    ${success_ratio}%"
    error "   Threshold: ≥ 99.5%"
    error "   Impact:    System reliability below acceptable threshold"
    slo_violations=$((slo_violations + 1))
    violation_details="${violation_details}\n### Success Ratio Violation\n- **Actual:** ${success_ratio}%\n- **Threshold:** ≥ 99.5%\n- **Total Requests:** $total_requests\n- **Failed Requests:** $failed_requests\n"
else
    log "✅ Success Ratio SLO PASSED: ${success_ratio}% ≥ 99.5%"
fi

# Check error rate SLO (< 0.5%)
if (( $(echo "$error_rate > $MAX_ERROR_RATE" | bc -l) )); then
    error "❌ Error Rate SLO VIOLATED"
    error "   Actual:    ${error_rate_pct}%"
    error "   Threshold: < 0.5%"
    error "   Impact:    Too many failed requests"
    slo_violations=$((slo_violations + 1))
    violation_details="${violation_details}\n### Error Rate Violation\n- **Actual:** ${error_rate_pct}%\n- **Threshold:** < 0.5%\n"
else
    log "✅ Error Rate SLO PASSED: ${error_rate_pct}% < 0.5%"
fi

# Check Chat endpoint P99 latency (< 8s)
if (( $(echo "$chat_p99 > 0" | bc -l) )); then
    if (( $(echo "$chat_p99 > $MAX_P99_CHAT" | bc -l) )); then
        error "❌ Chat P99 Latency SLO VIOLATED"
        error "   Actual:    ${chat_p99}ms"
        error "   Threshold: < 8000ms"
        error "   Impact:    Poor user experience for chat interactions"
        slo_violations=$((slo_violations + 1))
        violation_details="${violation_details}\n### Chat Endpoint P99 Latency Violation\n- **Actual:** ${chat_p99}ms\n- **Threshold:** < 8000ms\n- **P95:** ${chat_p95}ms\n- **P50:** ${chat_p50}ms\n"
    else
        log "✅ Chat P99 Latency SLO PASSED: ${chat_p99}ms < 8000ms"
    fi
fi

# Check RAG endpoints P99 latency (< 2s)
if (( $(echo "$rag_p99 > 0" | bc -l) )); then
    if (( $(echo "$rag_p99 > $MAX_P99_NON_LLM" | bc -l) )); then
        error "❌ RAG P99 Latency SLO VIOLATED"
        error "   Actual:    ${rag_p99}ms"
        error "   Threshold: < 2000ms"
        error "   Impact:    RAG operations too slow"
        slo_violations=$((slo_violations + 1))
        violation_details="${violation_details}\n### RAG Endpoints P99 Latency Violation\n- **Actual:** ${rag_p99}ms\n- **Threshold:** < 2000ms\n- **P95:** ${rag_p95}ms\n- **P50:** ${rag_p50}ms\n"
    else
        log "✅ RAG P99 Latency SLO PASSED: ${rag_p99}ms < 2000ms"
    fi
fi

# Check MCP/Tools endpoints P99 latency (< 2s)
if (( $(echo "$mcp_p99 > 0" | bc -l) )); then
    if (( $(echo "$mcp_p99 > $MAX_P99_NON_LLM" | bc -l) )); then
        error "❌ MCP/Tools P99 Latency SLO VIOLATED"
        error "   Actual:    ${mcp_p99}ms"
        error "   Threshold: < 2000ms"
        error "   Impact:    Tool operations too slow"
        slo_violations=$((slo_violations + 1))
        violation_details="${violation_details}\n### MCP/Tools Endpoints P99 Latency Violation\n- **Actual:** ${mcp_p99}ms\n- **Threshold:** < 2000ms\n- **P95:** ${mcp_p95}ms\n- **P50:** ${mcp_p50}ms\n"
    else
        log "✅ MCP/Tools P99 Latency SLO PASSED: ${mcp_p99}ms < 2000ms"
    fi
fi

log "${CYAN}════════════════════════════════════════════${NC}"
log ""

# Generate top errors report
log "🔍 Analyzing error patterns..."
top_errors=""

chat_error_pct=$(echo "scale=2; $chat_error_rate * 100" | bc)
rag_error_pct=$(echo "scale=2; $rag_error_rate * 100" | bc)
mcp_error_pct=$(echo "scale=2; $mcp_error_rate * 100" | bc)

top_errors="${top_errors}\n### Error Breakdown by Endpoint\n\n"
top_errors="${top_errors}| Endpoint Group | Error Rate | Status |\n"
top_errors="${top_errors}|----------------|------------|--------|\n"
top_errors="${top_errors}| Chat (/v1/chat) | ${chat_error_pct}% | $(if (( $(echo "$chat_error_rate > 0.005" | bc -l) )); then echo "❌"; else echo "✅"; fi) |\n"
top_errors="${top_errors}| RAG (/v1/rag/*) | ${rag_error_pct}% | $(if (( $(echo "$rag_error_rate > 0.005" | bc -l) )); then echo "❌"; else echo "✅"; fi) |\n"
top_errors="${top_errors}| MCP/Tools (/internal/mcp/tools/*) | ${mcp_error_pct}% | $(if (( $(echo "$mcp_error_rate > 0.005" | bc -l) )); then echo "❌"; else echo "✅"; fi) |\n"
top_errors="${top_errors}\n"

# Export results to Prometheus Pushgateway
log "📤 Exporting metrics to Prometheus Pushgateway..."

push_metrics_to_prometheus() {
    local job_name="k6_load_test"
    local timestamp=$(date +%s)
    
    # Calculate success ratio for Prometheus
    local success_requests=$(echo "$total_requests - $failed_requests" | bc)
    
    # Create metrics in Prometheus format with limited labels (suite=merge, endpoint_group)
    metrics=$(cat <<EOF
# TYPE k6_http_reqs_total counter
# HELP k6_http_reqs_total Total HTTP requests
k6_http_reqs_total{suite="merge",endpoint_group="all"} $total_requests $timestamp

# TYPE k6_http_req_failed_total counter
# HELP k6_http_req_failed_total Failed HTTP requests
k6_http_req_failed_total{suite="merge",endpoint_group="all"} $failed_requests $timestamp

# TYPE k6_http_req_success_total counter
# HELP k6_http_req_success_total Successful HTTP requests
k6_http_req_success_total{suite="merge",endpoint_group="all"} $success_requests $timestamp

# TYPE k6_success_ratio gauge
# HELP k6_success_ratio Success ratio percentage
k6_success_ratio{suite="merge",endpoint_group="all"} $success_ratio $timestamp

# TYPE k6_error_rate gauge
# HELP k6_error_rate Error rate percentage
k6_error_rate{suite="merge",endpoint_group="all"} $error_rate_pct $timestamp

# TYPE k6_http_req_duration_p99 gauge
# HELP k6_http_req_duration_p99 P99 latency in milliseconds
k6_http_req_duration_p99{suite="merge",endpoint_group="chat"} $chat_p99 $timestamp
k6_http_req_duration_p99{suite="merge",endpoint_group="rag"} $rag_p99 $timestamp
k6_http_req_duration_p99{suite="merge",endpoint_group="tools"} $mcp_p99 $timestamp

# TYPE k6_http_req_duration_p95 gauge
# HELP k6_http_req_duration_p95 P95 latency in milliseconds
k6_http_req_duration_p95{suite="merge",endpoint_group="chat"} $chat_p95 $timestamp
k6_http_req_duration_p95{suite="merge",endpoint_group="rag"} $rag_p95 $timestamp
k6_http_req_duration_p95{suite="merge",endpoint_group="tools"} $mcp_p95 $timestamp

# TYPE k6_http_req_duration_p50 gauge
# HELP k6_http_req_duration_p50 P50 latency in milliseconds
k6_http_req_duration_p50{suite="merge",endpoint_group="chat"} $chat_p50 $timestamp
k6_http_req_duration_p50{suite="merge",endpoint_group="rag"} $rag_p50 $timestamp
k6_http_req_duration_p50{suite="merge",endpoint_group="tools"} $mcp_p50 $timestamp

# TYPE k6_endpoint_error_rate gauge
# HELP k6_endpoint_error_rate Error rate by endpoint group
k6_endpoint_error_rate{suite="merge",endpoint_group="chat"} $chat_error_pct $timestamp
k6_endpoint_error_rate{suite="merge",endpoint_group="rag"} $rag_error_pct $timestamp
k6_endpoint_error_rate{suite="merge",endpoint_group="tools"} $mcp_error_pct $timestamp

# TYPE k6_slo_violations_total counter
# HELP k6_slo_violations_total Number of SLO violations
k6_slo_violations_total{suite="merge",endpoint_group="all"} $slo_violations $timestamp

# TYPE k6_test_timestamp gauge
# HELP k6_test_timestamp Test execution timestamp
k6_test_timestamp{suite="merge",endpoint_group="all"} $timestamp $timestamp
EOF
)
    
    # Push to Prometheus Pushgateway
    if echo "$metrics" | curl -sf --data-binary @- "$PROMETHEUS_PUSHGATEWAY/metrics/job/$job_name" &> /dev/null; then
        log "✅ Metrics successfully exported to Prometheus Pushgateway"
        info "   Job:      $job_name"
        info "   Gateway:  $PROMETHEUS_PUSHGATEWAY"
        info "   Labels:   suite=merge, endpoint_group={chat,rag,tools,health,all}"
    else
        warn "⚠️  Failed to export metrics to Prometheus Pushgateway"
        warn "   Gateway URL: $PROMETHEUS_PUSHGATEWAY"
        warn "   This is not a critical failure, continuing..."
    fi
}

push_metrics_to_prometheus
log ""

# Generate detailed failure report if violations detected
if [ $slo_violations -gt 0 ]; then
    log "📝 Generating detailed failure report..."
    
    REPORT_FILE="${RESULTS_DIR}/slo_failure_report.md"
    
    cat > "$REPORT_FILE" << EOF
# 🚨 Load Test SLO Failure Report

## Executive Summary

**Status:** ❌ FAILED - ${slo_violations} SLO Violation(s) Detected

**Environment:** Staging
**Timestamp:** $(date -u +"%Y-%m-%d %H:%M:%S UTC")
**Test Duration:** ~21 minutes

## SLO Compliance

| SLO Metric | Target | Actual | Status |
|------------|--------|--------|--------|
| Success Ratio | ≥ 99.5% | ${success_ratio}% | $(if (( $(echo "$success_ratio >= $MIN_SUCCESS_RATIO" | bc -l) )); then echo "✅ PASS"; else echo "❌ FAIL"; fi) |
| Error Rate | < 0.5% | ${error_rate_pct}% | $(if (( $(echo "$error_rate < $MAX_ERROR_RATE" | bc -l) )); then echo "✅ PASS"; else echo "❌ FAIL"; fi) |
| Chat P99 Latency | < 8000ms | ${chat_p99}ms | $(if (( $(echo "$chat_p99 <= $MAX_P99_CHAT" | bc -l) )); then echo "✅ PASS"; else echo "❌ FAIL"; fi) |
| RAG P99 Latency | < 2000ms | ${rag_p99}ms | $(if (( $(echo "$rag_p99 <= $MAX_P99_NON_LLM" | bc -l) )); then echo "✅ PASS"; else echo "❌ FAIL"; fi) |
| MCP/Tools P99 Latency | < 2000ms | ${mcp_p99}ms | $(if (( $(echo "$mcp_p99 <= $MAX_P99_NON_LLM" | bc -l) )); then echo "✅ PASS"; else echo "❌ FAIL"; fi) |

## Test Metrics

### Overall
- **Total Requests:** $total_requests
- **Failed Requests:** $failed_requests
- **Success Ratio:** ${success_ratio}%
- **Error Rate:** ${error_rate_pct}%
- **P50 Latency:** ${overall_p50}ms
- **P95 Latency:** ${overall_p95}ms
- **P99 Latency:** ${overall_p99}ms

### Chat Endpoint (/v1/chat)
- **P50:** ${chat_p50}ms
- **P95:** ${chat_p95}ms
- **P99:** ${chat_p99}ms
- **Error Rate:** ${chat_error_pct}%
- **SLO Threshold:** P99 < 8000ms

### RAG Endpoints (/v1/rag/*)
- **P50:** ${rag_p50}ms
- **P95:** ${rag_p95}ms
- **P99:** ${rag_p99}ms
- **Error Rate:** ${rag_error_pct}%
- **SLO Threshold:** P99 < 2000ms

### MCP/Tools Endpoints (/internal/mcp/tools/*)
- **P50:** ${mcp_p50}ms
- **P95:** ${mcp_p95}ms
- **P99:** ${mcp_p99}ms
- **Error Rate:** ${mcp_error_pct}%
- **SLO Threshold:** P99 < 2000ms

## Violation Details

$(echo -e "$violation_details")

$(echo -e "$top_errors")

### Slow Endpoints Analysis

**Endpoints exceeding SLO thresholds:**

EOF

    # Add slow endpoint analysis
    if (( $(echo "$chat_p99 > $MAX_P99_CHAT" | bc -l) )); then
        echo "- **Chat (/v1/chat)**: P99=${chat_p99}ms (threshold: 8000ms)" >> "$REPORT_FILE"
    fi
    if (( $(echo "$rag_p99 > $MAX_P99_NON_LLM" | bc -l) )); then
        echo "- **RAG (/v1/rag/*)**: P99=${rag_p99}ms (threshold: 2000ms)" >> "$REPORT_FILE"
    fi
    if (( $(echo "$mcp_p99 > $MAX_P99_NON_LLM" | bc -l) )); then
        echo "- **MCP/Tools (/internal/mcp/tools/*)**: P99=${mcp_p99}ms (threshold: 2000ms)" >> "$REPORT_FILE"
    fi

    cat >> "$REPORT_FILE" << 'EOF'

## Recommended Actions

### 🚨 Immediate (within 1 hour)
1. Review application logs for errors and exceptions
2. Check infrastructure metrics (CPU, memory, disk I/O, network)
3. Verify database and cache performance
4. Review recent deployments or configuration changes
5. Check for alerts in monitoring systems
6. Verify external dependency health

### ⚡ Short-term (within 24 hours)
1. Scale resources if under capacity
2. Optimize slow endpoints identified in tests
3. Review and tune rate limiting/throttling
4. Validate circuit breaker configurations
5. Implement additional caching where appropriate
6. Fix identified bugs or performance issues

### 📊 Long-term (within 1 week)
1. Conduct thorough performance analysis
2. Review architecture for systemic bottlenecks
3. Enhance monitoring and alerting coverage
4. Schedule capacity planning review
5. Implement performance improvements
6. Conduct load testing against fixes
7. Update runbooks with lessons learned

## Prometheus Metrics

Metrics have been exported to Prometheus Pushgateway with the following labels:
- **suite:** merge
- **endpoint_group:** chat, rag, tools, health, all

Query examples:
```promql
# Success ratio
k6_success_ratio{suite="merge",endpoint_group="all"}

# Error rate by endpoint
k6_endpoint_error_rate{suite="merge"}

# P99 latency by endpoint
k6_http_req_duration_p99{suite="merge"}

# SLO violations count
k6_slo_violations_total{suite="merge"}
```

## Related Artifacts

- **Full k6 results:** k6_results_*.json
- **Test summary:** k6_summary_*.txt
- **Prometheus metrics:** Available at pushgateway

---

*This report was automatically generated by the K6 load testing CI pipeline.*
EOF

    log "✅ Failure report generated: slo_failure_report.md"
    log ""
fi

# Archive results
log "📦 Archiving test results..."

archive_file="${RESULTS_DIR}/k6_test_archive_${TIMESTAMP}.tar.gz"

files_to_archive="k6_results_${TIMESTAMP}.json k6_summary_${TIMESTAMP}.txt"
if [ -f "${RESULTS_DIR}/slo_failure_report.md" ]; then
    files_to_archive="$files_to_archive slo_failure_report.md"
fi

if tar -czf "$archive_file" -C "$RESULTS_DIR" $files_to_archive 2>/dev/null; then
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
    error "   Detailed breakdown:"
    
    if (( $(echo "$success_ratio < $MIN_SUCCESS_RATIO" | bc -l) )); then
        error "   • Success Ratio: ${success_ratio}% < 99.5%"
    fi
    if (( $(echo "$error_rate > $MAX_ERROR_RATE" | bc -l) )); then
        error "   • Error Rate: ${error_rate_pct}% > 0.5%"
    fi
    if (( $(echo "$chat_p99 > $MAX_P99_CHAT" | bc -l) )); then
        error "   • Chat P99: ${chat_p99}ms > 8000ms"
    fi
    if (( $(echo "$rag_p99 > $MAX_P99_NON_LLM" | bc -l) )); then
        error "   • RAG P99: ${rag_p99}ms > 2000ms"
    fi
    if (( $(echo "$mcp_p99 > $MAX_P99_NON_LLM" | bc -l) )); then
        error "   • MCP/Tools P99: ${mcp_p99}ms > 2000ms"
    fi
    
    error ""
    error "   📄 See detailed report: ${RESULTS_DIR}/slo_failure_report.md"
    error ""
    error "   Top errors by endpoint:"
    error "   • Chat: ${chat_error_pct}%"
    error "   • RAG: ${rag_error_pct}%"
    error "   • MCP/Tools: ${mcp_error_pct}%"
    
    log "${CYAN}════════════════════════════════════════════${NC}"
    exit 1
else
    log "${GREEN}✅ ALL SLOS PASSED - LOAD TEST SUCCESSFUL${NC}"
    log ""
    log "   Summary:"
    log "   • Success Ratio:  ${success_ratio}% ≥ 99.5% ✓"
    log "   • Error Rate:     ${error_rate_pct}% < 0.5% ✓"
    log "   • Chat P99:       ${chat_p99}ms < 8000ms ✓"
    log "   • RAG P99:        ${rag_p99}ms < 2000ms ✓"
    log "   • MCP/Tools P99:  ${mcp_p99}ms < 2000ms ✓"
    log ""
    log "   System is performing within acceptable limits."
    log "${CYAN}════════════════════════════════════════════${NC}"
    exit 0
fi
