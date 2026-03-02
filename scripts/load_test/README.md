# K6 Load Test Suite

This directory contains the k6 load test execution pipeline for brainego, designed to validate performance SLOs in staging and production environments with full CI/CD integration.

## Overview

The load test suite validates the following SLOs (defined in `slo_definitions.yaml`):
- **Error Rate**: < 0.5%
- **P99 Latency**: < 2000ms (2 seconds)
- **Availability**: > 99.5%

## CI/CD Integration

The load test suite is fully integrated into the GitHub Actions CI/CD pipeline via `.github/workflows/load-test.yml`.

### Automatic Triggers

The load tests run automatically on:
1. **Every merge to master/main branch** - Validates production readiness
2. **Daily at 2 AM UTC** - Continuous monitoring of staging environment
3. **Manual dispatch** - On-demand testing via GitHub Actions UI

### CI Pipeline Features

- ✅ **Automated SLO validation** - Tests fail if any SLO is violated
- ✅ **Prometheus integration** - Metrics exported to pushgateway for monitoring
- ✅ **Detailed failure reports** - Comprehensive analysis of SLO violations
- ✅ **GitHub issue creation** - Automatic incident tracking for master branch failures
- ✅ **PR comments** - Test results posted to pull requests
- ✅ **Artifact upload** - Full test results archived for 30 days
- ✅ **Health checks** - Pre-flight validation of target environment

## Test Scenarios

### 1. Standard Load Scenarios
- **chat_load**: Chat completion endpoint with ramping load (20 → 40 users)
- **rag_load**: RAG operations (ingest & query) with ramping load (15 → 30 users)
- **mcp_load**: MCP tool execution with ramping load (10 → 20 users)

### 2. Adaptive Load Scenario
- Ramps up to **100 concurrent users** testing all endpoints
- Mixed traffic across chat, RAG, and MCP endpoints
- Duration: 18 minutes
- Validates system behavior under increasing load
- Targets P99 latency < 2s SLO across all endpoints

### 3. Workspace Quota Burst Scenario
- Sends **10x normal request rate** (100 req/s)
- Tests metering enforcement and rate limiting
- Duration: 3 minutes
- Validates quota enforcement and graceful degradation
- Expects >50% rate limiting during burst

## Usage

### Prerequisites

Install k6:
```bash
# macOS
brew install k6

# Linux
sudo gpg -k
sudo gpg --no-default-keyring --keyring /usr/share/keyrings/k6-archive-keyring.gpg --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69
echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" | sudo tee /etc/apt/sources.list.d/k6.list
sudo apt-get update
sudo apt-get install k6

# Windows
choco install k6

# Docker
docker pull grafana/k6
```

Also required:
- `jq` for JSON parsing
- `bc` for calculations
- `curl` for Prometheus pushgateway integration

### Running the Test Suite

#### Against Staging Environment (Default)

```bash
./scripts/load_test/run_k6_suite.sh
```

#### With Custom Environment URLs

```bash
STAGING_BASE_URL=https://api-staging.example.com \
STAGING_GATEWAY_URL=https://gateway-staging.example.com \
STAGING_MCP_URL=https://mcp-staging.example.com \
PROMETHEUS_PUSHGATEWAY=http://pushgateway.example.com:9091 \
./scripts/load_test/run_k6_suite.sh
```

#### Running k6 Script Directly (for development)

```bash
# Run all scenarios
k6 run k6_load_test.js

# Run specific scenario only
k6 run --env SCENARIO=adaptive_load_scenario k6_load_test.js

# Run against custom endpoints
k6 run \
  -e BASE_URL=http://localhost:8000 \
  -e GATEWAY_URL=http://localhost:9002 \
  -e MCP_URL=http://localhost:9100 \
  k6_load_test.js
```

## Test Duration

Total test duration: ~21 minutes
- Standard scenarios: Run in parallel for ~15 minutes
- Adaptive load scenario: 18 minutes
- Workspace quota burst: 3 minutes (starts at 18m mark)

## Output

The test suite produces:

### 1. Console Output
- Real-time test progress
- Health check results
- SLO validation results
- Color-coded pass/fail indicators

### 2. Results Files
All results are saved to `load_test_results/` directory:
- `k6_results_<timestamp>.json`: Complete k6 test results in JSON format
- `k6_summary_<timestamp>.txt`: Text summary of test execution
- `grafana_metrics_<timestamp>.json`: Detailed metrics for Grafana visualization
- `k6_test_archive_<timestamp>.tar.gz`: Compressed archive of all results

### 3. Prometheus Metrics
Metrics pushed to Prometheus Pushgateway:
- `k6_http_reqs_total`: Total HTTP requests
- `k6_http_req_failed_total`: Failed HTTP requests
- `k6_http_req_duration_p99`: P99 latency in milliseconds
- `k6_error_rate`: Overall error rate
- `k6_availability_percent`: Availability percentage
- `k6_slo_violations_total`: Number of SLO violations
- `k6_test_timestamp`: Test execution timestamp

### 4. Exit Codes
- `0`: All tests passed and SLOs met
- `1`: SLO violations detected
- `>1`: k6 test execution failure

### Workflow Configuration

The GitHub Actions workflow (`.github/workflows/load-test.yml`) requires the following secrets:

```bash
# GitHub Secrets (configure in repository settings)
STAGING_BASE_URL           # API server URL (e.g., https://api-staging.brainego.io)
STAGING_GATEWAY_URL        # Gateway URL (e.g., https://gateway-staging.brainego.io)
STAGING_MCP_URL            # MCP server URL (e.g., https://mcp-staging.brainego.io)
PROMETHEUS_PUSHGATEWAY     # Pushgateway URL (e.g., http://pushgateway.brainego.io:9091)
```

### SLO Validation and CI Behavior

The CI pipeline enforces SLO compliance and will **fail the build** if any SLO is violated:

**CI Failure Conditions:**
1. **Error Rate > 0.5%** - Too many failed requests
2. **P99 Latency > 2000ms** - Unacceptable tail latency
3. **Availability < 99.5%** - System reliability too low

**When SLOs are violated on master branch:**
- ❌ CI job fails with detailed error message
- 📊 Comprehensive failure report generated (`slo_failure_report.md`)
- 📁 All test artifacts uploaded (retained 30 days)
- 🐛 GitHub issue automatically created with `slo-violation` label
- 🚨 Deployment pipeline blocked

**When SLOs are violated on pull requests:**
- ❌ CI job fails, blocking merge
- 💬 PR comment posted with test results
- 📊 Failure details available in artifacts
- ⚠️ Developer must fix issues before merge

**Workflow Outputs:**

Success:
```
✅ ALL SLOs PASSED - CI SUCCESSFUL
   ✓ Error Rate:   0.123% ≤ 0.5%
   ✓ P99 Latency:  1567ms ≤ 2000ms
   ✓ Availability: 99.877% ≥ 99.5%
```

Failure:
```
❌ CI FAILED: 2 SLO violation(s) detected
   Error Rate:   1.234% (threshold: < 0.5%)
   P99 Latency:  2345ms (threshold: < 2000ms)
   Availability: 98.766% (threshold: > 99.5%)
```

### Test Artifacts

All test runs produce artifacts uploaded to GitHub Actions:

**Always Generated:**
- `k6_results_<timestamp>.json` - Complete k6 metrics and results
- `k6_summary_<timestamp>.txt` - Human-readable summary
- `grafana_metrics_<timestamp>.json` - Metrics for Grafana dashboards
- `k6_test_archive_<timestamp>.tar.gz` - Compressed archive

**Generated on Failure:**
- `slo_failure_report.md` - Detailed failure analysis with remediation steps

**Retention:** 30 days

### Alternative CI Systems

#### GitLab CI Example

```yaml
load-test:
  stage: test
  image: grafana/k6:latest
  before_script:
    - apk add --no-cache jq bc bash curl
  script:
    - chmod +x ./scripts/load_test/run_k6_suite.sh
    - ./scripts/load_test/run_k6_suite.sh
  artifacts:
    when: always
    paths:
      - load_test_results/
    expire_in: 30 days
  only:
    - schedules
    - web
```

#### Jenkins Pipeline Example

```groovy
pipeline {
    agent any
    stages {
        stage('Load Test') {
            steps {
                sh '''
                    chmod +x ./scripts/load_test/run_k6_suite.sh
                    ./scripts/load_test/run_k6_suite.sh
                '''
            }
        }
    }
    post {
        always {
            archiveArtifacts artifacts: 'load_test_results/**/*', fingerprint: true
        }
    }
}
```

## Grafana Visualization

The test suite exports metrics to Prometheus Pushgateway, which can be visualized in Grafana.

### Example Grafana Dashboard Panels

1. **Request Rate**: `rate(k6_http_reqs_total[5m])`
2. **Error Rate**: `k6_error_rate * 100`
3. **P99 Latency**: `k6_http_req_duration_p99`
4. **Availability**: `k6_availability_percent`
5. **SLO Compliance**: `k6_slo_violations_total`

## Troubleshooting

### Test Fails with "k6 not found"
Install k6 following the prerequisites section above.

### Health Checks Fail
Verify that the target environment is accessible:
```bash
curl https://api-staging.brainego.io/health
curl https://gateway-staging.brainego.io/health
curl https://mcp-staging.brainego.io/health
```

### Prometheus Push Fails
This is a non-critical warning. Verify Pushgateway is accessible:
```bash
curl http://pushgateway:9091/metrics
```

### SLO Violations
Review the detailed metrics in `k6_results_<timestamp>.json`:
- Check which endpoints are failing
- Review latency distribution (P50, P95, P99)
- Identify error patterns
- Examine rate limiting behavior

## Customization

### Adjusting SLO Thresholds

Edit `scripts/load_test/run_k6_suite.sh`:
```bash
MAX_ERROR_RATE=0.005  # 0.5%
MAX_P99_LATENCY=2000  # 2000ms
MIN_AVAILABILITY=99.5 # 99.5%
```

### Modifying Load Scenarios

Edit `k6_load_test.js` scenarios section:
```javascript
adaptive_load_scenario: {
    executor: 'ramping-vus',
    exec: 'adaptiveLoadScenario',
    startVUs: 0,
    stages: [
        { duration: '1m', target: 10 },
        { duration: '2m', target: 50 },
        // Add more stages...
    ],
}
```

### Adding Custom Metrics

Add to `k6_load_test.js`:
```javascript
import { Trend } from 'k6/metrics';
const customMetric = new Trend('custom_metric');

export function customScenario() {
    const startTime = Date.now();
    // Your test logic
    customMetric.add(Date.now() - startTime);
}
```

## References

- [k6 Documentation](https://k6.io/docs/)
- [k6 Thresholds](https://k6.io/docs/using-k6/thresholds/)
- [k6 Scenarios](https://k6.io/docs/using-k6/scenarios/)
- [Prometheus Pushgateway](https://github.com/prometheus/pushgateway)
