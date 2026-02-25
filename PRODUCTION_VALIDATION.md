# Production Validation Guide

Complete guide for production validation including load testing, chaos engineering, security auditing, backup/restore testing, and SLO monitoring.

## Table of Contents

1. [Overview](#overview)
2. [Service Level Objectives (SLOs)](#service-level-objectives-slos)
3. [Load Testing](#load-testing)
4. [Chaos Engineering](#chaos-engineering)
5. [Security Audit](#security-audit)
6. [Backup & Restore Testing](#backup--restore-testing)
7. [Running Full Validation](#running-full-validation)
8. [Monitoring & Alerts](#monitoring--alerts)

## Overview

Production validation ensures the system meets all SLO requirements:
- **99.5% Availability**
- **P99 Latency < 2s**
- **Zero Data Loss**

### Validation Components

1. **Load Testing** - k6 and Locust with 50 concurrent users
2. **Chaos Engineering** - Pod kills, CPU saturation, network partitions
3. **Security Audit** - Trivy scanning and penetration testing
4. **Backup/Restore** - Automated testing with data integrity checks

## Service Level Objectives (SLOs)

### Primary SLOs

| Metric | Target | Measurement Window | Alert Threshold |
|--------|--------|-------------------|-----------------|
| Availability | ≥ 99.5% | 30 days | < 99.0% (warning), < 98.0% (critical) |
| P99 Latency | < 2000ms | 1 hour | > 2000ms (warning), > 2500ms (critical) |
| Data Loss | 0 records | Continuous | > 0 (critical) |
| Error Rate | < 0.5% | 5 minutes | > 1.0% (warning), > 2.0% (critical) |

### Service-Specific SLOs

**Chat API:**
- Availability: 99.5%
- P99 Latency: < 2000ms
- Throughput: ≥ 20 req/s

**RAG Service:**
- Query Latency (P99): < 1800ms
- Ingest Latency (P99): < 2000ms
- Availability: 99.5%

**MCP Gateway:**
- Operation Timeout: < 30s
- P99 Latency: < 2000ms
- Availability: 99.5%

### Error Budget

**Monthly (30 days):**
- Allowed downtime: 3.6 hours (0.5%)
- Allowed failed requests: 0.5%

**Weekly (7 days):**
- Allowed downtime: 50.4 minutes
- Allowed failed requests: 0.5%

See `slo_definitions.yaml` for complete configuration.

## Load Testing

### k6 Load Testing

**Setup:**
```bash
# Install k6
curl https://github.com/grafana/k6/releases/download/v0.47.0/k6-v0.47.0-linux-amd64.tar.gz -L | tar xvz
sudo cp k6-v0.47.0-linux-amd64/k6 /usr/local/bin

# Verify installation
k6 version
```

**Run k6 test:**
```bash
# Basic run
k6 run k6_load_test.js

# Custom configuration
k6 run --vus 50 --duration 10m k6_load_test.js

# With environment variables
BASE_URL=http://localhost:8000 \
GATEWAY_URL=http://localhost:9002 \
MCP_URL=http://localhost:9100 \
k6 run --vus 50 --duration 15m k6_load_test.js
```

**Test Scenarios:**
- **Chat Load** (40% of traffic): 20-40 concurrent users
- **RAG Load** (30% of traffic): 15-30 concurrent users  
- **MCP Load** (20% of traffic): 10-20 concurrent users

**Success Criteria:**
- P99 latency < 2000ms for all endpoints
- Error rate < 0.5%
- No service crashes or restarts

**Results:**
- JSON report: `k6_results.json`
- Console output with metrics and SLO compliance

### Locust Load Testing

**Setup:**
```bash
# Install Locust
pip install locust

# Verify installation
locust --version
```

**Run Locust test:**
```bash
# Headless mode (automated)
locust -f locust_load_test.py \
    --host=http://localhost:8000 \
    --users=50 \
    --spawn-rate=5 \
    --run-time=10m \
    --headless \
    --html=locust_report.html

# Web UI mode (interactive)
locust -f locust_load_test.py --host=http://localhost:8000
# Open http://localhost:8089 in browser
```

**Task Distribution:**
- Chat: 50% (ChatTasks with weight 5)
- RAG: 30% (RAGTasks with weight 3)
- MCP: 20% (MCPTasks with weight 2)

**Results:**
- JSON report: `locust_results.json`
- HTML report: `locust_report.html`
- Real-time metrics in web UI
- SLO compliance summary

### Load Test Metrics

Both tools track:
- **Latency**: P50, P95, P99 percentiles
- **Throughput**: Requests per second
- **Error Rate**: Failed requests percentage
- **Availability**: Success rate percentage

## Chaos Engineering

### Overview

Tests system resilience through controlled failure injection:
1. **Random Pod Kills** - Container restart resilience
2. **CPU Saturation** - Performance under CPU stress
3. **Memory Pressure** - OOM handling
4. **Network Partitions** - Network failure recovery

### Prerequisites

```bash
# Install Docker SDK
pip install docker

# Verify Docker access
docker ps
```

### Running Chaos Tests

```bash
# Run all chaos experiments
python chaos_engineering.py

# Results saved to chaos_report.json
```

### Experiments

**1. Random Pod Kill**
- Kills 3 random non-critical containers
- Verifies automatic restart via Docker restart policy
- Recovery timeout: 60 seconds

**2. CPU Saturation**
- Runs CPU-intensive processes in containers
- Duration: 60 seconds
- Verifies service remains responsive

**3. Memory Pressure**
- Allocates 512MB memory in containers
- Duration: 45 seconds
- Tests OOM killer and recovery

**4. Network Partition**
- Blocks traffic between service pairs using iptables
- Duration: 30 seconds
- Verifies circuit breaker and retry logic

### Success Criteria

- **Resilience Score ≥ 90%**: Excellent
- **Resilience Score ≥ 75%**: Good
- **Resilience Score < 75%**: Needs improvement

Services should:
- Auto-recover within defined timeouts
- Maintain availability during experiments
- Prevent cascading failures

### Chaos Report

```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "experiments_run": 4,
  "failures_detected": 0,
  "resilience_score": 100.0,
  "failures": []
}
```

## Security Audit

### Overview

Comprehensive security validation:
1. **Trivy Image Scanning** - Container vulnerability scanning
2. **Penetration Testing** - SQL injection, XSS, auth bypass
3. **Security Headers** - HTTP security header validation
4. **API Security** - Rate limiting, CORS, input validation

### Setup

**Install Trivy:**
```bash
# Linux
curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh -s -- -b /usr/local/bin

# macOS
brew install aquasecurity/trivy/trivy

# Verify
trivy --version
```

**Install Python dependencies:**
```bash
pip install requests
```

### Running Security Audit

```bash
# Run complete audit
python security_audit.py

# Results saved to:
# - security_audit_report.json
# - trivy_scan_results.json
```

### Trivy Image Scanning

Scans Docker images for vulnerabilities:
- `modular/max-serve:latest`
- `api-server:latest`
- `gateway:latest`
- `mcpjungle-gateway:latest`

Reports HIGH and CRITICAL vulnerabilities.

### Penetration Tests

**1. SQL Injection**
- Tests common SQL injection patterns
- Validates input sanitization

**2. Cross-Site Scripting (XSS)**
- Tests script injection in inputs
- Validates output encoding

**3. Authentication Bypass**
- Tests unprotected endpoints
- Validates auth middleware

**4. Rate Limiting**
- Sends 100 rapid requests
- Verifies rate limiter activates

**5. CORS Policy**
- Tests cross-origin requests
- Validates CORS headers

**6. Security Headers**
- Checks X-Content-Type-Options
- Checks X-Frame-Options
- Checks Strict-Transport-Security
- Checks Content-Security-Policy

**7. File Upload Security**
- Tests malicious file uploads
- Validates file type restrictions

**8. API Key Exposure**
- Scans responses for sensitive data
- Validates secret management

### Success Criteria

- **Security Score ≥ 95%**: Excellent
- **Security Score ≥ 80%**: Good
- **Security Score < 80%**: Needs attention

No CRITICAL vulnerabilities should be found.

### Security Report

```json
{
  "timestamp": "2024-01-15T10:45:00Z",
  "tests_run": 8,
  "vulnerabilities_found": 0,
  "security_score": 100.0,
  "vulnerabilities": [],
  "test_results": [...]
}
```

## Backup & Restore Testing

### Overview

Validates backup system and ensures zero data loss:
1. **Backup Creation** - Automated backup generation
2. **Data Integrity** - Verification before/after backup
3. **Restore Testing** - Full system restore
4. **Zero Data Loss** - Data count validation

### Prerequisites

```bash
# Install Python dependencies
pip install psycopg2-binary qdrant-client redis

# Verify services are running
docker ps | grep -E 'postgres|qdrant|redis'
```

### Running Backup/Restore Tests

```bash
# Run complete test suite
python test_backup_restore.py

# Results saved to backup_restore_report.json
```

### Test Workflow

1. **Setup**: Connect to all data stores
2. **Inject Test Data**: Add known test records
3. **Verify Initial State**: Confirm data exists
4. **Create Backup**: Trigger backup service
5. **Verify Backup**: Check backup files created
6. **Restore**: Restore from backup
7. **Verify Integrity**: Confirm data matches
8. **Zero Data Loss**: Compare counts before/after

### Data Stores Tested

**PostgreSQL:**
- Conversations table
- User data
- Training history

**Redis:**
- Cache entries
- Session data
- Rate limit counters

**Qdrant:**
- Vector embeddings
- Document metadata
- Search indices

**Neo4j:**
- Knowledge graph
- Entity relationships

**MinIO:**
- Model artifacts
- LoRA adapters
- Backup archives

### Success Criteria

- All backups created successfully
- Restore completes without errors
- Data integrity verified
- **Zero data loss confirmed** (SLO requirement)

### Backup Report

```json
{
  "timestamp": "2024-01-15T11:00:00Z",
  "tests_run": 3,
  "passed": 3,
  "failed": 0,
  "success_rate": 100.0,
  "test_results": [
    {"test": "backup_creation", "status": "passed"},
    {"test": "restore", "status": "passed"},
    {"test": "data_loss", "status": "passed"}
  ]
}
```

## Running Full Validation

### Quick Start

```bash
# Install all dependencies
pip install -r requirements.txt
pip install locust docker

# Run complete validation suite
python run_production_validation.py --full
```

### Validation Options

**Full validation:**
```bash
python run_production_validation.py --full
```

**Quick validation (skip chaos and k6):**
```bash
python run_production_validation.py --quick
```

**Skip specific tests:**
```bash
python run_production_validation.py --skip chaos security
```

**Available skip options:**
- `locust` - Skip Locust load test
- `k6` - Skip k6 load test
- `chaos` - Skip chaos engineering
- `security` - Skip security audit
- `backup` - Skip backup/restore test

### Validation Timeline

| Test | Duration | Notes |
|------|----------|-------|
| Locust Load Test | 10 minutes | 50 concurrent users |
| k6 Load Test | 10 minutes | Optional if k6 installed |
| Chaos Engineering | 15 minutes | 4 experiments |
| Security Audit | 10 minutes | With Trivy scanning |
| Backup/Restore | 5 minutes | Full cycle test |
| **Total** | **50-60 minutes** | Full validation |

### Validation Report

After completion, check:
- `production_validation_report.json` - Main report
- `locust_results.json` - Load test results
- `k6_results.json` - k6 results (if run)
- `chaos_report.json` - Resilience report
- `security_audit_report.json` - Security findings
- `backup_restore_report.json` - Backup test results

**Example report structure:**
```json
{
  "timestamp": "2024-01-15T10:00:00Z",
  "duration_seconds": 3000,
  "tests": {
    "locust_load_test": {"status": "passed", "slo_pass": true},
    "k6_load_test": {"status": "passed"},
    "chaos_engineering": {"status": "passed", "resilience_score": 100},
    "security_audit": {"status": "passed", "security_score": 95},
    "backup_restore": {"status": "passed", "success_rate": 100}
  },
  "slo_compliance": {
    "availability": {"target": 99.5, "met": true, "actual": 99.8},
    "p99_latency": {"target": 2000, "met": true, "actual": 1450},
    "data_loss": {"target": 0, "met": true, "actual": 0}
  },
  "overall_status": "PASSED"
}
```

## Monitoring & Alerts

### Prometheus Queries

**Availability:**
```promql
(sum(rate(http_requests_total{status="200"}[5m])) / 
 sum(rate(http_requests_total[5m]))) * 100
```

**P99 Latency:**
```promql
histogram_quantile(0.99, 
  sum(rate(http_request_duration_seconds_bucket[5m])) by (le)
)
```

**Error Rate:**
```promql
(sum(rate(http_requests_total{status=~"5.."}[5m])) / 
 sum(rate(http_requests_total[5m]))) * 100
```

### Grafana Dashboards

Import dashboards from `configs/grafana/dashboards/`:
- `slo_dashboard.json` - SLO tracking
- `api_performance.json` - API metrics
- `infrastructure.json` - Resource utilization

### Alert Rules

See `configs/prometheus/alert_rules.yml`:

**Critical Alerts:**
- Availability < 98%
- P99 latency > 2500ms
- Data loss detected
- Error rate > 2%

**Warning Alerts:**
- Availability < 99%
- P99 latency > 2000ms
- Error rate > 1%
- High memory usage

### Slack Integration

Configure in `configs/alertmanager/alertmanager.yml`:
```yaml
receivers:
  - name: 'slack'
    slack_configs:
      - api_url: 'YOUR_SLACK_WEBHOOK_URL'
        channel: '#alerts'
        title: 'Production Alert'
```

## Troubleshooting

### Load Test Issues

**Problem:** High error rates during load test
- Check service logs: `docker compose logs -f api-server`
- Verify resource limits: `docker stats`
- Check database connections
- Review rate limiting configuration

**Problem:** Timeout errors
- Increase timeout in test configuration
- Check network connectivity
- Verify service health endpoints
- Scale up resources if needed

### Chaos Engineering Issues

**Problem:** Containers don't recover
- Check Docker restart policy: `unless-stopped`
- Verify health check configuration
- Check resource availability
- Review container logs

**Problem:** Network partition fails
- Ensure containers have NET_ADMIN capability
- Verify iptables available in containers
- Check container network mode

### Security Audit Issues

**Problem:** Trivy not found
- Install Trivy (see installation instructions)
- Verify PATH includes `/usr/local/bin`
- Check Trivy executable permissions

**Problem:** False positives
- Review vulnerability details
- Check if patches available
- Update base images
- Document accepted risks

### Backup/Restore Issues

**Problem:** Connection errors
- Verify all services running
- Check credentials in environment
- Test individual connections
- Review firewall rules

**Problem:** Data loss detected
- Check backup service logs
- Verify backup completeness
- Test restore procedure manually
- Review retention policies

## Best Practices

1. **Run validation regularly** - Weekly minimum
2. **Monitor SLO trends** - Track over time
3. **Review all reports** - Don't just check pass/fail
4. **Update baselines** - As system evolves
5. **Document incidents** - Learn from failures
6. **Automate everything** - Integrate into CI/CD
7. **Test disaster recovery** - Quarterly full DR tests
8. **Keep dependencies updated** - Security patches
9. **Maintain runbooks** - For incident response
10. **Celebrate successes** - When SLOs are met!

## CI/CD Integration

### GitHub Actions

```yaml
name: Production Validation
on:
  schedule:
    - cron: '0 2 * * 0'  # Weekly on Sunday at 2 AM
  workflow_dispatch:

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install locust docker
      - name: Start services
        run: docker compose up -d
      - name: Wait for services
        run: sleep 60
      - name: Run validation
        run: python run_production_validation.py --full
      - name: Upload reports
        uses: actions/upload-artifact@v3
        with:
          name: validation-reports
          path: |
            production_validation_report.json
            locust_results.json
            chaos_report.json
            security_audit_report.json
            backup_restore_report.json
```

## Additional Resources

- [SLO Definitions](slo_definitions.yaml)
- [Prometheus Configuration](configs/prometheus/)
- [Grafana Dashboards](configs/grafana/dashboards/)
- [Alert Rules](configs/prometheus/alert_rules.yml)
- [Backup Documentation](BACKUP_README.md)
- [Security Guide](SECURITY_FEATURES.md)

## Support

For issues or questions:
1. Check service logs: `docker compose logs`
2. Review validation reports
3. Consult runbooks in `/docs`
4. Contact on-call engineer (see escalation policy)

---

**Remember:** Production validation is not just about passing tests - it's about building confidence in system reliability and ensuring we meet our commitments to users.
