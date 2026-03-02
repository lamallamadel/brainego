# K6 Load Test CI Integration - Complete Implementation

## Overview

This document describes the complete integration of k6 load testing into the CI/CD pipeline for brainego. The implementation validates Service Level Objectives (SLOs) on every merge to master and fails the build if performance requirements are not met.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   GitHub Actions Workflow                    │
│               (.github/workflows/load-test.yml)              │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              Run K6 Suite Script                             │
│        (scripts/load_test/run_k6_suite.sh)                   │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                   K6 Load Tests                              │
│              (k6_load_test.js)                               │
│  • Chat API load (20-40 users)                               │
│  • RAG operations load (15-30 users)                         │
│  • MCP operations load (10-20 users)                         │
│  • Adaptive load (ramp to 100 users)                         │
│  • Quota burst (10x rate)                                    │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│               SLO Validation                                 │
│  ✓ Error Rate < 0.5%                                         │
│  ✓ P99 Latency < 2000ms                                      │
│  ✓ Availability > 99.5%                                      │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ├──────────────┬─────────────────────┐
                         ▼              ▼                     ▼
              ┌──────────────┐  ┌────────────┐    ┌──────────────┐
              │  Prometheus  │  │  GitHub    │    │   Artifact   │
              │  Pushgateway │  │  Issues    │    │   Upload     │
              └──────────────┘  └────────────┘    └──────────────┘
```

## Components

### 1. GitHub Actions Workflow (`.github/workflows/load-test.yml`)

**Triggers:**
- Every push to `master` or `main` branch
- Daily at 2 AM UTC (scheduled)
- Manual dispatch via GitHub Actions UI

**Features:**
- ✅ Automated k6 installation and setup
- ✅ Health checks before test execution
- ✅ SLO validation with detailed reporting
- ✅ Prometheus metrics export
- ✅ Automatic GitHub issue creation on failure
- ✅ PR comments with test results
- ✅ Artifact upload (30-day retention)
- ✅ CI failure on SLO violations

**Environment Variables:**
```bash
STAGING_BASE_URL          # API server URL
STAGING_GATEWAY_URL       # Gateway URL
STAGING_MCP_URL           # MCP server URL
PROMETHEUS_PUSHGATEWAY    # Pushgateway URL
```

### 2. Test Execution Script (`scripts/load_test/run_k6_suite.sh`)

**Responsibilities:**
- Environment validation
- Health checks for target endpoints
- K6 test execution
- Results parsing and SLO validation
- Prometheus metrics export
- Artifact generation and archiving

**Exit Codes:**
- `0` - All SLOs passed
- `1` - SLO violations detected
- `>1` - Test execution failure

### 3. K6 Test Script (`k6_load_test.js`)

**Test Scenarios:**

1. **Chat Load Scenario**
   - Ramps 20 → 40 concurrent users
   - Tests chat completion endpoint
   - Duration: ~15 minutes

2. **RAG Load Scenario**
   - Ramps 15 → 30 concurrent users
   - Tests document ingestion and query
   - Duration: ~15 minutes

3. **MCP Load Scenario**
   - Ramps 10 → 20 concurrent users
   - Tests MCP tool execution
   - Duration: ~15 minutes

4. **Adaptive Load Scenario**
   - Ramps to 100 concurrent users
   - Mixed traffic across all endpoints
   - Duration: 18 minutes

5. **Workspace Quota Burst Scenario**
   - 10x normal request rate (100 req/s)
   - Tests rate limiting and quotas
   - Duration: 3 minutes

**Total Test Duration:** ~21 minutes

## SLO Definitions

Based on `slo_definitions.yaml`:

| Metric | Target | Measurement | Impact |
|--------|--------|-------------|--------|
| Error Rate | < 0.5% | Failed requests / Total requests | System reliability |
| P99 Latency | < 2000ms | 99th percentile response time | User experience |
| Availability | > 99.5% | (1 - Error Rate) × 100 | Service uptime |

## Prometheus Integration

### Metrics Exported

The following metrics are pushed to Prometheus Pushgateway after each test run:

```prometheus
# Request counts
k6_http_reqs_total{environment="staging",job="load_test"}
k6_http_req_failed_total{environment="staging",job="load_test"}

# Latency percentiles
k6_http_req_duration_p50{environment="staging",job="load_test"}
k6_http_req_duration_p95{environment="staging",job="load_test"}
k6_http_req_duration_p99{environment="staging",job="load_test"}

# SLO metrics
k6_error_rate{environment="staging",job="load_test"}
k6_availability_percent{environment="staging",job="load_test"}
k6_slo_violations_total{environment="staging",job="load_test"}

# Test metadata
k6_test_timestamp{environment="staging",job="load_test"}
```

### Grafana Visualization

Example queries for Grafana dashboards:

```promql
# Error rate over time
k6_error_rate{environment="staging"} * 100

# P99 latency trend
k6_http_req_duration_p99{environment="staging"}

# Availability percentage
k6_availability_percent{environment="staging"}

# SLO violations count
k6_slo_violations_total{environment="staging"}
```

## CI Failure Behavior

### On SLO Violation

When any SLO is violated, the CI pipeline will:

1. **Fail the build** with exit code 1
2. **Generate detailed failure report** (`slo_failure_report.md`)
3. **Upload all test artifacts** to GitHub Actions
4. **Create GitHub issue** (master branch only) with:
   - Issue title: `🚨 Load Test SLO Failure - YYYY-MM-DD`
   - Labels: `performance`, `slo-violation`, `critical`, `load-test`
   - Detailed failure analysis
   - Recommended remediation steps
5. **Post PR comment** (pull requests only) with:
   - SLO compliance matrix
   - Test metrics summary
   - Warning about merge blocking

### Failure Report Contents

The generated `slo_failure_report.md` includes:

- **Executive Summary** - Status, environment, commit info
- **SLO Compliance Table** - Pass/fail status for each SLO
- **Test Metrics** - Detailed performance data
- **Violation Details** - Specific analysis for each failed SLO
- **Recommended Actions** - Immediate, short-term, and long-term steps
- **Investigation Checklist** - Systematic troubleshooting guide
- **Additional Context** - Test configuration and scenario details

## Test Artifacts

All test runs generate the following artifacts (retained for 30 days):

### Always Generated

1. **k6_results_<timestamp>.json**
   - Complete k6 metrics in JSON format
   - All HTTP request details
   - Custom metric values
   - Threshold pass/fail status

2. **k6_summary_<timestamp>.txt**
   - Human-readable test summary
   - Console output from k6 execution

3. **grafana_metrics_<timestamp>.json**
   - Structured metrics for Grafana
   - SLO compliance flags
   - Test run metadata

4. **k6_test_archive_<timestamp>.tar.gz**
   - Compressed archive of all results

### Generated on Failure

5. **slo_failure_report.md**
   - Comprehensive failure analysis
   - Remediation recommendations
   - Investigation checklist

## Usage

### Local Execution

```bash
# Set environment variables
export STAGING_BASE_URL="https://api-staging.brainego.io"
export STAGING_GATEWAY_URL="https://gateway-staging.brainego.io"
export STAGING_MCP_URL="https://mcp-staging.brainego.io"
export PROMETHEUS_PUSHGATEWAY="http://pushgateway.brainego.io:9091"

# Run the test suite
./scripts/load_test/run_k6_suite.sh
```

### Manual Trigger in GitHub Actions

1. Go to **Actions** tab in GitHub repository
2. Select **K6 Load Testing - SLO Validation** workflow
3. Click **Run workflow**
4. Select environment (staging/production)
5. Click **Run workflow** button

### Viewing Results

**In GitHub Actions:**
1. Navigate to the workflow run
2. Check the job summary for SLO compliance
3. Download artifacts for detailed analysis

**In Prometheus/Grafana:**
1. Query Prometheus for `k6_*` metrics
2. View pre-configured dashboards in Grafana
3. Set up alerts based on SLO violations

## Configuration

### GitHub Secrets

Required secrets in repository settings:

```bash
STAGING_BASE_URL           # Staging API URL
STAGING_GATEWAY_URL        # Staging Gateway URL
STAGING_MCP_URL            # Staging MCP URL
PROMETHEUS_PUSHGATEWAY     # Pushgateway URL
```

### SLO Thresholds

Defined in `scripts/load_test/run_k6_suite.sh`:

```bash
MAX_ERROR_RATE=0.005      # 0.5%
MAX_P99_LATENCY=2000      # 2000ms
MIN_AVAILABILITY=99.5     # 99.5%
```

These values are aligned with `slo_definitions.yaml`.

## Troubleshooting

### Test Fails with "k6 not found"

The CI workflow automatically installs k6. For local execution:

```bash
# macOS
brew install k6

# Linux (Debian/Ubuntu)
sudo gpg --no-default-keyring --keyring /usr/share/keyrings/k6-archive-keyring.gpg \
  --keyserver hkp://keyserver.ubuntu.com:80 \
  --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69
echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" | \
  sudo tee /etc/apt/sources.list.d/k6.list
sudo apt-get update
sudo apt-get install k6
```

### Health Checks Fail

Verify target environment is accessible:

```bash
curl -v https://api-staging.brainego.io/health
curl -v https://gateway-staging.brainego.io/health
curl -v https://mcp-staging.brainego.io/health
```

### Prometheus Push Fails

Non-critical warning. Verify pushgateway is accessible:

```bash
curl http://pushgateway.brainego.io:9091/metrics
```

### SLO Violations

Review the failure report and check:
- Application logs for errors
- Infrastructure metrics (CPU, memory, network)
- Database query performance
- Recent deployments or configuration changes
- Cache hit rates
- External dependency health

## Integration with Deployment Pipeline

The load test CI can be integrated with deployment pipelines:

```yaml
# Example: deployment-pipeline.yml
jobs:
  deploy-staging:
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to staging
        run: ./deploy.sh staging
      
      - name: Wait for deployment
        run: sleep 60
      
      - name: Trigger load tests
        uses: actions/github-script@v7
        with:
          script: |
            await github.rest.actions.createWorkflowDispatch({
              owner: context.repo.owner,
              repo: context.repo.repo,
              workflow_id: 'load-test.yml',
              ref: 'main',
              inputs: { environment: 'staging' }
            });
      
      - name: Wait for load tests
        run: sleep 1500  # 25 minutes
      
      - name: Check load test status
        run: |
          # Check if load tests passed
          # Fail deployment if SLOs violated
```

## Monitoring and Alerting

### Recommended Alerts

Configure alerts in Prometheus/Alertmanager:

```yaml
# Load test SLO violation alert
- alert: LoadTestSLOViolation
  expr: k6_slo_violations_total > 0
  for: 5m
  labels:
    severity: critical
  annotations:
    summary: "Load test SLO violations detected"
    description: "{{ $value }} SLO violations in recent load test"

# Load test error rate alert
- alert: LoadTestHighErrorRate
  expr: k6_error_rate > 0.005
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Load test error rate above threshold"
    description: "Error rate: {{ $value | humanizePercentage }}"

# Load test high latency alert
- alert: LoadTestHighLatency
  expr: k6_http_req_duration_p99 > 2000
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Load test P99 latency above threshold"
    description: "P99 latency: {{ $value }}ms"
```

## Best Practices

### When to Run

- **On every merge to master** - Catch performance regressions early
- **Daily scheduled runs** - Continuous monitoring of staging
- **Before major releases** - Validate performance before production
- **After infrastructure changes** - Verify impact on performance

### When SLOs Fail

1. **Immediate Actions** (within 1 hour)
   - Review failure report
   - Check application and infrastructure logs
   - Verify recent changes
   - Assess impact on production

2. **Short-term Actions** (within 24 hours)
   - Identify root cause
   - Implement fix
   - Re-run load tests to validate
   - Update monitoring if needed

3. **Long-term Actions** (within 1 week)
   - Conduct post-mortem
   - Update documentation
   - Enhance monitoring
   - Review capacity planning

### Customization

To adjust SLO thresholds or test scenarios:

1. Update `slo_definitions.yaml` for documentation
2. Update `scripts/load_test/run_k6_suite.sh` for validation thresholds
3. Update `k6_load_test.js` for test scenarios and k6 thresholds
4. Test changes locally before committing

## References

- **K6 Documentation**: https://k6.io/docs/
- **SLO Definitions**: `slo_definitions.yaml`
- **Test Scenarios**: `scripts/load_test/scenarios.md`
- **Workflow Configuration**: `.github/workflows/load-test.yml`
- **Test Script**: `k6_load_test.js`
- **Execution Script**: `scripts/load_test/run_k6_suite.sh`

---

**Last Updated:** 2024
**Owner:** Platform Engineering Team
**Status:** Production Ready
