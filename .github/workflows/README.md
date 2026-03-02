# GitHub Actions Workflows

This directory contains CI/CD workflows for the brainego platform.

## Workflows

### 1. Load Testing (`load-test.yml`)

**Purpose:** Validates system performance against SLO thresholds on every merge to master.

**Triggers:**
- Push to `master` or `main` branch (automatic)
- Manual workflow dispatch (optional)
- Daily schedule at 2 AM UTC

**What it does:**
1. Installs k6 and dependencies
2. Runs comprehensive load tests (~21 minutes)
3. Validates SLO compliance:
   - Error rate < 0.5%
   - P99 latency < 2000ms
   - Availability > 99.5%
4. Exports metrics to Prometheus Pushgateway
5. Generates detailed failure reports on SLO violations
6. Creates GitHub issues for failures on master branch
7. **Fails CI if any SLO is violated**

**Environment Variables:**
```yaml
STAGING_BASE_URL: API server URL
STAGING_GATEWAY_URL: Gateway URL
STAGING_MCP_URL: MCP URL
PROMETHEUS_PUSHGATEWAY: Pushgateway URL
```

**Artifacts:**
- `load-test-results-<sha>/k6_results_*.json`: Full test results
- `load-test-results-<sha>/k6_summary_*.txt`: Text summary
- `load-test-results-<sha>/grafana_metrics_*.json`: Grafana metrics
- `load-test-results-<sha>/slo_failure_report.md`: Failure report (on violations)
- `load-test-results-<sha>/k6_test_archive_*.tar.gz`: Compressed archive

**Documentation:**
- [Load Test CI Integration Guide](../../LOAD_TEST_CI_INTEGRATION.md)
- [Load Test Suite README](../../scripts/load_test/README.md)

**Manual Trigger:**
```bash
# Via GitHub UI:
# 1. Go to Actions tab
# 2. Select "Load Testing on Staging"
# 3. Click "Run workflow"
# 4. Select environment (staging/production)
# 5. Click "Run workflow"
```

---

### 2. Codex Build & Test (`codex-build.yml`)

**Purpose:** Builds Docker images and runs tests for Codex feature branches.

**Triggers:**
- Push to `feature/codex/**` branches
- Pull requests to `feature/codex/**` branches

**What it does:**
1. Builds and pushes Docker images for:
   - API server
   - Gateway
   - MCPJungle
2. Runs unit tests (offline)
3. Runs integration tests (Testcontainers Cloud)
4. Runs LoRA non-regression tests
5. Runs adversarial safety suite
6. Performs security scanning with Trivy

**Artifacts:**
- `test-results/`: Test output logs
- `adversarial-safety-report/`: Safety validation results

---

## Setup for CI/CD

### Required GitHub Secrets

For load testing:
```
STAGING_BASE_URL
STAGING_GATEWAY_URL
STAGING_MCP_URL
PROMETHEUS_PUSHGATEWAY
```

For image registry:
```
GITHUB_TOKEN (automatically provided)
```

For external integrations (optional):
```
SLACK_WEBHOOK_URL
PAGERDUTY_INTEGRATION_KEY
DD_API_KEY (Datadog)
```

### Adding a New Workflow

1. Create new YAML file in `.github/workflows/`
2. Define workflow name, triggers, and jobs
3. Use appropriate runners (`ubuntu-latest`, etc.)
4. Set timeout for long-running jobs
5. Add artifact upload for results
6. Document in this README

### Best Practices

1. **Use continue-on-error judiciously**: Only for non-critical steps
2. **Always upload artifacts**: Even on failure (`if: always()`)
3. **Set timeouts**: Prevent hanging jobs
4. **Use caching**: Speed up builds and tests
5. **Fail fast**: Exit early on critical failures
6. **Generate reports**: Make results actionable
7. **Notify on failure**: Use PR comments or external integrations

---

## Workflow Monitoring

### View Workflow Runs

```
https://github.com/<org>/<repo>/actions
```

### Check Workflow Status Badge

Add to README.md:
```markdown
[![Load Tests](https://github.com/<org>/<repo>/actions/workflows/load-test.yml/badge.svg)](https://github.com/<org>/<repo>/actions/workflows/load-test.yml)
```

### Grafana Dashboard

View load test metrics in Grafana:
- Dashboard: "K6 Load Test - SLO Monitoring"
- URL: `http://grafana:3000/d/k6-load-test`

---

## Troubleshooting

### Workflow Fails to Start

- Check workflow syntax with [actionlint](https://github.com/rhysd/actionlint)
- Verify branch name matches trigger pattern
- Check repository permissions

### Workflow Times Out

- Increase `timeout-minutes` in job definition
- Check for blocking operations (network, database)
- Review logs for stuck processes

### Artifacts Not Uploaded

- Ensure `upload-artifact` step runs with `if: always()`
- Check artifact path exists
- Verify artifact size is under limit (5GB)

### SLO Violations

- Review detailed failure report in artifacts
- Check Grafana dashboard for trends
- Investigate recent code changes
- Review infrastructure metrics

---

## Additional Resources

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Workflow Syntax](https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions)
- [Secrets Management](https://docs.github.com/en/actions/security-guides/encrypted-secrets)
- [Artifact Upload](https://github.com/actions/upload-artifact)
- [K6 Documentation](https://k6.io/docs/)
