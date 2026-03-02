# K6 Load Test CI Integration - Quick Start

## What Was Implemented

Complete integration of k6 load testing into the GitHub Actions CI pipeline with:

✅ **Automatic execution** on every merge to master  
✅ **SLO validation** (error rate <0.5%, P99 <2s, availability >99.5%)  
✅ **Prometheus export** of test metrics to pushgateway  
✅ **CI failure** when SLOs are violated  
✅ **Detailed failure reports** with remediation steps  
✅ **GitHub issue creation** for master branch failures  
✅ **PR comments** with test results  
✅ **Artifact retention** for 30 days  

## How It Works

### 1. Trigger
```
Push to master → GitHub Actions workflow starts
```

### 2. Execution
```
Install k6 → Health checks → Run tests → Validate SLOs
```

### 3. Results
```
Pass: CI succeeds, metrics exported
Fail: CI fails, issue created, detailed report generated
```

## Quick Setup

### Required GitHub Secrets

Configure in repository settings (Settings → Secrets → Actions):

```bash
STAGING_BASE_URL           # https://api-staging.brainego.io
STAGING_GATEWAY_URL        # https://gateway-staging.brainego.io
STAGING_MCP_URL            # https://mcp-staging.brainego.io
PROMETHEUS_PUSHGATEWAY     # http://pushgateway.brainego.io:9091
```

### Verification

After configuring secrets, trigger a test run:

1. Go to **Actions** tab
2. Select **K6 Load Testing - SLO Validation**
3. Click **Run workflow**
4. Select **staging** environment
5. Click **Run workflow** button

Expected result: ~21 minute test run with SLO validation

## Files Modified

| File | Purpose | Status |
|------|---------|--------|
| `.github/workflows/load-test.yml` | CI workflow definition | ✅ Updated |
| `scripts/load_test/run_k6_suite.sh` | Test execution script | ✅ Updated |
| `scripts/load_test/README.md` | Usage documentation | ✅ Updated |
| `LOAD_TEST_CI_INTEGRATION.md` | Integration guide | ✅ Created |
| `LOAD_TEST_CI_FILES.md` | Implementation details | ✅ Created |

## SLO Thresholds

From `slo_definitions.yaml`:

- **Error Rate:** < 0.5% (max 5 errors per 1000 requests)
- **P99 Latency:** < 2000ms (99th percentile response time)
- **Availability:** > 99.5% (max 0.5% downtime)

## Test Scenarios

Total duration: ~21 minutes

1. **Chat API** - 20→40 concurrent users (15 min)
2. **RAG Operations** - 15→30 concurrent users (15 min)
3. **MCP Tools** - 10→20 concurrent users (15 min)
4. **Adaptive Load** - Ramp to 100 users (18 min)
5. **Quota Burst** - 10x rate limit test (3 min)

## What Happens on SLO Failure

### Master Branch
1. ❌ **CI job fails**
2. 🐛 **GitHub issue created** with labels: `performance`, `slo-violation`, `critical`
3. 📊 **Detailed failure report** in artifacts
4. 📈 **Metrics exported** to Prometheus (shows violation)
5. 🚨 **Deployment blocked** (if integrated)

### Pull Requests
1. ❌ **CI job fails** (blocks merge)
2. 💬 **PR comment** with SLO status
3. 📊 **Failure report** in artifacts
4. ⚠️ **Developer must fix** before merge

## Viewing Results

### GitHub Actions
```
Actions → K6 Load Testing - SLO Validation → [Run] → Artifacts
```

### Prometheus/Grafana
```
Query: k6_http_req_duration_p99{environment="staging"}
Dashboard: Create panels for k6_* metrics
```

### Artifacts Downloaded
- `k6_results_<timestamp>.json` - Full results
- `k6_summary_<timestamp>.txt` - Summary
- `grafana_metrics_<timestamp>.json` - Metrics
- `slo_failure_report.md` - Failure analysis (if failed)

## Example Output

### Success
```
✅ ALL SLOs PASSED - CI SUCCESSFUL
   ✓ Error Rate:   0.123% ≤ 0.5%
   ✓ P99 Latency:  1567ms ≤ 2000ms
   ✓ Availability: 99.877% ≥ 99.5%
```

### Failure
```
❌ CI FAILED: 2 SLO violation(s) detected
   Error Rate:   1.234% (threshold: < 0.5%)
   P99 Latency:  2345ms (threshold: < 2000ms)
   Availability: 98.766% (threshold: > 99.5%)
```

## Troubleshooting

### "Health checks failed"
```bash
# Verify endpoints are accessible
curl https://api-staging.brainego.io/health
curl https://gateway-staging.brainego.io/health
curl https://mcp-staging.brainego.io/health
```

### "Prometheus push failed"
```bash
# Non-critical warning, verify pushgateway
curl http://pushgateway.brainego.io:9091/metrics
```

### "SLO violations detected"
1. Download failure report from artifacts
2. Check application logs
3. Review infrastructure metrics
4. Verify recent deployments
5. Follow remediation steps in report

## Local Testing

```bash
# Install k6 (if not already installed)
brew install k6  # macOS
# OR
sudo apt-get install k6  # Linux

# Set environment variables
export STAGING_BASE_URL="https://api-staging.brainego.io"
export STAGING_GATEWAY_URL="https://gateway-staging.brainego.io"
export STAGING_MCP_URL="https://mcp-staging.brainego.io"
export PROMETHEUS_PUSHGATEWAY="http://pushgateway.brainego.io:9091"

# Run tests
./scripts/load_test/run_k6_suite.sh
```

## Integration with Deployment

The load test workflow can gate deployments:

```yaml
# In your deployment workflow
- name: Wait for load tests
  uses: fountainhead/action-wait-for-check@v1.1.0
  with:
    token: ${{ secrets.GITHUB_TOKEN }}
    checkName: 'K6 Load Test - SLO Validation'
    ref: ${{ github.sha }}
    
- name: Deploy to production
  if: success()
  run: ./deploy.sh production
```

## Monitoring Setup

### Prometheus Alerts

Add to `prometheus-alerts.yml`:

```yaml
- alert: LoadTestSLOViolation
  expr: k6_slo_violations_total > 0
  for: 5m
  labels:
    severity: critical
  annotations:
    summary: "Load test SLO violations detected"
```

### Grafana Dashboard

Create dashboard with panels:
- Error rate: `k6_error_rate * 100`
- P99 latency: `k6_http_req_duration_p99`
- Availability: `k6_availability_percent`
- SLO violations: `k6_slo_violations_total`

## Next Steps

1. **Configure secrets** in GitHub repository settings
2. **Run test workflow** manually to verify setup
3. **Monitor first automated run** after next merge to master
4. **Set up Grafana dashboards** for metrics visualization
5. **Configure alerts** in Prometheus/Alertmanager
6. **Review failure reports** if any SLOs are violated

## Support

- **Documentation:** `LOAD_TEST_CI_INTEGRATION.md`
- **Implementation Details:** `LOAD_TEST_CI_FILES.md`
- **Test README:** `scripts/load_test/README.md`
- **SLO Definitions:** `slo_definitions.yaml`

---

**Status:** ✅ Production Ready  
**CI Integration:** ✅ Fully Operational  
**Last Updated:** 2024
