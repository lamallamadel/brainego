# K6 Load Test Implementation Summary

This document summarizes the k6 load test execution pipeline implementation for brainego.

## Implementation Overview

Created a comprehensive k6 load test execution pipeline with:

1. **Two new test scenarios** in k6_load_test.js
2. **Execution script** with SLO validation and Prometheus integration
3. **Documentation** for usage and scenario details

## Files Created/Modified

### 1. k6_load_test.js (Modified)

**Added Scenarios:**

#### adaptive_load_scenario
- Ramps up to 100 concurrent users over 18 minutes
- Tests all endpoints (chat, RAG, MCP) with mixed traffic
- Distributes requests across 10 workspaces
- Validates P99 latency < 2s SLO under adaptive load
- Strict error rate threshold: < 0.5%

**Configuration:**
```javascript
stages: [
    { duration: '1m', target: 10 },   // Warm up
    { duration: '2m', target: 25 },   // Gradual increase
    { duration: '2m', target: 50 },   // Mid-range load
    { duration: '2m', target: 75 },   // Higher load
    { duration: '3m', target: 100 },  // Peak load
    { duration: '5m', target: 100 },  // Sustain peak
    { duration: '2m', target: 50 },   // Ramp down
    { duration: '1m', target: 0 },    // Cool down
]
```

#### workspace_quota_burst_scenario
- Sends 10x normal request rate (100 req/s)
- Tests metering enforcement and rate limiting
- Runs for 3 minutes after adaptive scenario completes
- Expects >50% rate limiting
- Tracks quota exceeded and rate limited requests

**Configuration:**
```javascript
executor: 'constant-arrival-rate'
duration: '3m'
rate: 100  // 100 req/s
preAllocatedVUs: 50
maxVUs: 200
```

**New Metrics:**
- `adaptive_errors`: Error rate for adaptive scenario
- `quota_burst_rate_limited`: Rate limiting percentage
- `adaptive_latency_ms`: Latency trend for adaptive load
- `quota_burst_latency_ms`: Latency during burst
- `rate_limited_requests`: Count of 429 responses
- `quota_exceeded_requests`: Count of quota exhaustion

**Updated Thresholds:**
- Overall error rate: < 0.5%
- P99 latency: < 2s
- Availability: > 99.5%
- Adaptive error rate: < 0.5% (strict)
- Quota burst rate limited: > 50% (expects limiting)

### 2. scripts/load_test/run_k6_suite.sh (Created)

**Features:**

#### SLO Validation
- Error rate < 0.5%
- P99 latency < 2000ms
- Availability > 99.5%
- Fails CI if any SLO is violated

#### Health Checks
- Pre-test health checks for all endpoints
- Validates API server, Gateway, and MCP server
- Non-blocking (warns but continues)

#### Prometheus Integration
- Exports metrics to Prometheus Pushgateway
- Pushes test results for Grafana visualization
- Metrics include:
  - `k6_http_reqs_total`
  - `k6_http_req_failed_total`
  - `k6_http_req_duration_p99`
  - `k6_error_rate`
  - `k6_availability_percent`
  - `k6_slo_violations_total`
  - `k6_test_timestamp`

#### Results Management
- Creates timestamped results files
- JSON results for programmatic analysis
- Text summary for human reading
- Grafana-compatible metrics export
- Compressed archives of all results

#### Environment Configuration
- Defaults to staging environment
- Configurable via environment variables:
  - `STAGING_BASE_URL`
  - `STAGING_GATEWAY_URL`
  - `STAGING_MCP_URL`
  - `PROMETHEUS_PUSHGATEWAY`

#### Exit Codes
- `0`: Success (all SLOs met)
- `1`: SLO violations detected
- `>1`: k6 test execution failure

**Usage:**
```bash
# Default (staging)
./scripts/load_test/run_k6_suite.sh

# Custom environment
STAGING_BASE_URL=https://api.example.com \
./scripts/load_test/run_k6_suite.sh
```

### 3. scripts/load_test/README.md (Created)

Comprehensive documentation including:
- Overview of test scenarios
- Installation prerequisites (k6, jq, bc, curl)
- Usage instructions
- Test duration breakdown
- Output file descriptions
- CI/CD integration examples (GitHub Actions, GitLab CI)
- Grafana visualization queries
- Troubleshooting guide
- Customization instructions

### 4. scripts/load_test/scenarios.md (Created)

Detailed scenario documentation:
- Scenario comparison table
- Per-scenario details:
  - Purpose and use cases
  - Configuration
  - Request patterns
  - Thresholds
  - Expected behavior
  - Key metrics
- Scenario timing timeline
- Result interpretation examples
- Evolution recommendations

### 5. .gitignore (Modified)

Added load test results to gitignore:
```
# K6 Load Test Results
load_test_results/
k6_results_*.json
k6_summary_*.txt
grafana_metrics_*.json
k6_test_archive_*.tar.gz
```

## Test Execution Flow

```
1. Health checks → All endpoints
2. Run k6 load tests → 21 minutes
   ├─ 0:00-15:00  Standard scenarios (chat, RAG, MCP)
   ├─ 0:00-18:00  Adaptive load (100 users)
   └─ 18:00-21:00 Quota burst (100 req/s)
3. Parse results → Extract metrics
4. Validate SLOs → Error rate, P99, Availability
5. Export to Prometheus → Pushgateway
6. Archive results → Timestamped files
7. Exit with status → 0 (success) or 1 (failure)
```

## SLO Validation

The pipeline validates three critical SLOs:

| SLO | Threshold | Impact |
|-----|-----------|--------|
| Error Rate | < 0.5% | Fails CI if violated |
| P99 Latency | < 2000ms | Fails CI if violated |
| Availability | > 99.5% | Fails CI if violated |

All three SLOs must pass for the test suite to succeed.

## Prometheus Metrics

Metrics are exported in Prometheus format to Pushgateway:

```prometheus
# TYPE k6_http_reqs_total counter
k6_http_reqs_total{environment="staging",job="load_test"} 18523

# TYPE k6_http_req_failed_total counter
k6_http_req_failed_total{environment="staging",job="load_test"} 23

# TYPE k6_http_req_duration_p99 gauge
k6_http_req_duration_p99{environment="staging",job="load_test"} 1856

# TYPE k6_error_rate gauge
k6_error_rate{environment="staging",job="load_test"} 0.00124

# TYPE k6_availability_percent gauge
k6_availability_percent{environment="staging",job="load_test"} 99.88

# TYPE k6_slo_violations_total counter
k6_slo_violations_total{environment="staging",job="load_test"} 0
```

## Grafana Visualization

Example Grafana queries:

```promql
# Request rate (5m average)
rate(k6_http_reqs_total[5m])

# Error rate percentage
k6_error_rate * 100

# P99 latency
k6_http_req_duration_p99

# Availability percentage
k6_availability_percent

# SLO violations over time
increase(k6_slo_violations_total[1h])
```

## CI/CD Integration

The test suite is designed for automated execution in CI/CD pipelines:

**GitHub Actions:**
- Scheduled daily runs
- Manual trigger support
- Artifact upload for results
- Secrets for environment URLs

**GitLab CI:**
- Scheduled pipeline runs
- Docker-based execution
- 30-day artifact retention
- Environment-based configuration

## Key Features

1. **Adaptive Load Testing**: Validates system behavior from 10 to 100 concurrent users
2. **Quota Enforcement**: Tests rate limiting and metering with 10x burst traffic
3. **SLO Validation**: Automated pass/fail based on strict performance criteria
4. **Prometheus Integration**: Metrics export for monitoring and alerting
5. **CI-Friendly**: Exit codes, artifact generation, configurable environments
6. **Comprehensive Logging**: Color-coded output with timestamps
7. **Health Checks**: Pre-test validation of target environment
8. **Result Archiving**: Timestamped, compressed results for historical analysis

## Dependencies

- **k6**: Load testing tool
- **jq**: JSON parsing
- **bc**: Mathematical calculations
- **curl**: HTTP client for health checks and Prometheus push
- **bash**: Shell script execution

## Total Test Duration

- **Standard scenarios**: 15 minutes (parallel)
- **Adaptive scenario**: 18 minutes
- **Quota burst**: 3 minutes
- **Total**: ~21 minutes

## Success Criteria

Test suite succeeds when:
- All k6 scenarios complete without errors
- Error rate < 0.5%
- P99 latency < 2000ms
- Availability > 99.5%
- Rate limiting engages during burst (>50%)
- System remains stable (no 500 errors)

## Files Summary

| File | Purpose | Lines |
|------|---------|-------|
| k6_load_test.js | Load test script with scenarios | ~511 |
| scripts/load_test/run_k6_suite.sh | Execution script with SLO validation | ~270 |
| scripts/load_test/README.md | Usage documentation | ~284 |
| scripts/load_test/scenarios.md | Scenario details | ~294 |
| .gitignore | Exclude load test results | +5 |

**Total**: 4 new files, 2 modified files, ~1,364 lines of code and documentation
