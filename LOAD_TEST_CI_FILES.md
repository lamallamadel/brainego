# K6 Load Test CI Integration - Files Created/Updated

## Summary

Complete implementation of k6 load testing integration into the CI/CD pipeline with SLO validation, Prometheus integration, and automated failure reporting.

## Files Created/Updated

### 1. GitHub Actions Workflow
**File:** `.github/workflows/load-test.yml`
- **Status:** ✅ Updated
- **Purpose:** CI/CD workflow for automated load testing
- **Features:**
  - Triggers on every merge to master/main
  - Daily scheduled runs at 2 AM UTC
  - Manual dispatch capability
  - Health checks before test execution
  - SLO validation (error rate, P99 latency, availability)
  - Prometheus metrics export
  - GitHub issue creation on failure (master branch)
  - PR comments with test results
  - Detailed failure reports
  - Artifact upload (30-day retention)
  - CI failure on SLO violations

### 2. Test Execution Script
**File:** `scripts/load_test/run_k6_suite.sh`
- **Status:** ✅ Updated
- **Purpose:** Bash script to execute k6 tests with SLO validation
- **Features:**
  - Environment validation (k6, jq, bc)
  - Health checks for target endpoints
  - K6 test execution with configurable endpoints
  - Results parsing and metric extraction
  - SLO compliance validation
  - Prometheus pushgateway integration
  - Detailed console output with colors
  - Grafana metrics export
  - Test artifact archiving
  - Exit codes for CI integration

### 3. Documentation
**File:** `scripts/load_test/README.md`
- **Status:** ✅ Updated
- **Purpose:** Complete documentation for load test suite
- **Additions:**
  - CI/CD integration details
  - Workflow configuration instructions
  - SLO validation behavior
  - Artifact descriptions
  - Troubleshooting guides
  - CI failure examples
  - Environment variable configuration

**File:** `LOAD_TEST_CI_INTEGRATION.md`
- **Status:** ✅ Created
- **Purpose:** Comprehensive integration documentation
- **Contents:**
  - Architecture overview
  - Component descriptions
  - SLO definitions and thresholds
  - Prometheus metrics catalog
  - CI failure behavior
  - Test artifact details
  - Usage instructions
  - Configuration guide
  - Troubleshooting
  - Best practices
  - Monitoring and alerting examples

## Implementation Details

### SLO Thresholds

Aligned with `slo_definitions.yaml`:

| Metric | Threshold | Source |
|--------|-----------|--------|
| Error Rate | < 0.5% | `slo_definitions.yaml` line 71 |
| P99 Latency | < 2000ms | `slo_definitions.yaml` line 40 |
| Availability | > 99.5% | `slo_definitions.yaml` line 7 |

### Prometheus Metrics

Exported to pushgateway:
- `k6_http_reqs_total` - Total HTTP requests
- `k6_http_req_failed_total` - Failed HTTP requests
- `k6_http_req_duration_p50` - P50 latency
- `k6_http_req_duration_p95` - P95 latency
- `k6_http_req_duration_p99` - P99 latency
- `k6_error_rate` - Overall error rate
- `k6_availability_percent` - Availability percentage
- `k6_slo_violations_total` - Number of SLO violations
- `k6_test_timestamp` - Test execution timestamp

### CI Workflow Triggers

1. **Push to master/main** - Validates production readiness
2. **Daily schedule** - Continuous monitoring (2 AM UTC)
3. **Manual dispatch** - On-demand testing

### Test Scenarios (from k6_load_test.js)

1. **chat_load** - Chat API (20→40 users, 15 min)
2. **rag_load** - RAG operations (15→30 users, 15 min)
3. **mcp_load** - MCP tools (10→20 users, 15 min)
4. **adaptive_load_scenario** - All endpoints (ramp to 100 users, 18 min)
5. **workspace_quota_burst_scenario** - Rate limiting (10x rate, 3 min)

**Total Duration:** ~21 minutes

### Artifacts Generated

**Always:**
- `k6_results_<timestamp>.json` - Complete test results
- `k6_summary_<timestamp>.txt` - Text summary
- `grafana_metrics_<timestamp>.json` - Grafana-ready metrics
- `k6_test_archive_<timestamp>.tar.gz` - Compressed archive

**On Failure:**
- `slo_failure_report.md` - Detailed failure analysis

**Retention:** 30 days in GitHub Actions

### CI Failure Behavior

**When SLOs are violated:**

1. **Build fails** with exit code 1
2. **Failure report generated** with:
   - Executive summary
   - SLO compliance table
   - Violation details
   - Recommended actions
   - Investigation checklist
3. **GitHub issue created** (master branch only) with labels:
   - `performance`
   - `slo-violation`
   - `critical`
   - `load-test`
4. **PR comment posted** (pull requests) with SLO status
5. **All artifacts uploaded** for analysis

### Environment Variables Required

Must be configured in GitHub repository secrets:

```bash
STAGING_BASE_URL           # e.g., https://api-staging.brainego.io
STAGING_GATEWAY_URL        # e.g., https://gateway-staging.brainego.io
STAGING_MCP_URL            # e.g., https://mcp-staging.brainego.io
PROMETHEUS_PUSHGATEWAY     # e.g., http://pushgateway.brainego.io:9091
```

## Integration Points

### 1. Existing Infrastructure

- **k6 test script:** `k6_load_test.js` (already exists)
- **SLO definitions:** `slo_definitions.yaml` (already exists)
- **Prometheus:** Uses existing pushgateway
- **Grafana:** Metrics compatible with existing dashboards

### 2. CI/CD Pipeline

- **GitHub Actions:** Native integration
- **Merge blocking:** PR checks prevent merge on SLO failure
- **Master protection:** Issues created for master branch failures
- **Deployment gate:** Can block deployments on failure

### 3. Monitoring Stack

- **Prometheus:** Metrics pushed to pushgateway
- **Grafana:** Dashboard-ready metrics exported
- **Alerting:** Can trigger alerts on SLO violations

## Usage

### Local Testing

```bash
# Set environment variables
export STAGING_BASE_URL="https://api-staging.brainego.io"
export STAGING_GATEWAY_URL="https://gateway-staging.brainego.io"
export STAGING_MCP_URL="https://mcp-staging.brainego.io"
export PROMETHEUS_PUSHGATEWAY="http://pushgateway.brainego.io:9091"

# Run tests
./scripts/load_test/run_k6_suite.sh
```

### Manual GitHub Actions Trigger

1. Go to **Actions** → **K6 Load Testing - SLO Validation**
2. Click **Run workflow**
3. Select environment (staging/production)
4. Click **Run workflow**

### Viewing Results

**GitHub Actions:**
- Workflow run summary shows SLO compliance
- Download artifacts for detailed analysis

**Prometheus/Grafana:**
- Query `k6_*` metrics
- Create dashboards for trend analysis
- Set up alerts for SLO violations

## Validation Checklist

- ✅ Workflow triggers on merge to master
- ✅ Daily scheduled runs configured
- ✅ Manual dispatch available
- ✅ Health checks performed before tests
- ✅ SLO thresholds validated (error rate, P99, availability)
- ✅ Prometheus metrics exported
- ✅ GitHub issues created on master failures
- ✅ PR comments posted with results
- ✅ Detailed failure reports generated
- ✅ Artifacts uploaded and retained (30 days)
- ✅ CI fails on SLO violations
- ✅ Exit codes properly set
- ✅ Documentation complete

## Future Enhancements

Potential improvements:

1. **Multi-environment support** - Test against staging and production
2. **Trend analysis** - Compare results over time
3. **Performance budgets** - Set limits per endpoint
4. **Slack notifications** - Real-time alerts on failure
5. **Grafana annotations** - Mark test runs on dashboards
6. **Cost tracking** - Estimate infrastructure costs during load
7. **A/B testing** - Compare different configurations
8. **Canary validation** - Test during canary deployments

## References

- **Workflow:** `.github/workflows/load-test.yml`
- **Script:** `scripts/load_test/run_k6_suite.sh`
- **Tests:** `k6_load_test.js`
- **SLOs:** `slo_definitions.yaml`
- **README:** `scripts/load_test/README.md`
- **Integration Guide:** `LOAD_TEST_CI_INTEGRATION.md`

---

**Implementation Date:** 2024
**Status:** ✅ Complete
**CI Integration:** ✅ Fully Operational
