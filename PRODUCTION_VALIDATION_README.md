# Production Validation System

Complete production validation infrastructure for ensuring SLO compliance: 99.5% availability, P99 latency < 2s, and zero data loss.

## 🎯 Quick Start

```bash
# 1. Install dependencies
pip install -r requirements-production-validation.txt

# 2. Make runner executable
chmod +x run_validation.sh

# 3. Run quick validation (10 minutes)
./run_validation.sh quick

# 4. Check results
./run_validation.sh results
```

## 📋 What's Included

### Load Testing
- **k6**: High-performance load testing with 50 concurrent users
- **Locust**: Python-based load testing with mixed workload simulation
- Real-time SLO validation and metrics tracking

### Chaos Engineering
- Random pod kills and auto-recovery testing
- CPU saturation and performance validation
- Memory pressure and OOM handling
- Network partitions and connectivity failures

### Security Audit
- Trivy container vulnerability scanning
- Penetration testing (SQL injection, XSS, etc.)
- Security best practices validation
- Comprehensive security scoring

### Backup & Restore
- Multi-database backup validation
- Data integrity verification
- Zero data loss testing (SLO requirement)
- Automated restore testing

### Orchestration
- Unified test execution
- SLO compliance checking
- Consolidated reporting
- CI/CD integration ready

## 📚 Documentation

| Document | Description |
|----------|-------------|
| [Quick Start Guide](PRODUCTION_VALIDATION_QUICKSTART.md) | Get started in 5 minutes |
| [Complete Guide](PRODUCTION_VALIDATION.md) | Comprehensive documentation |
| [Checklist](PRODUCTION_VALIDATION_CHECKLIST.md) | Validation checklist |
| [Summary](PRODUCTION_VALIDATION_SUMMARY.md) | Implementation overview |
| [Files Created](PRODUCTION_VALIDATION_FILES_CREATED.md) | File listing and structure |
| [SLO Definitions](slo_definitions.yaml) | SLO targets and configuration |

## 🎯 Service Level Objectives (SLOs)

### Primary SLOs

| Metric | Target | Alert Threshold |
|--------|--------|----------------|
| **Availability** | ≥ 99.5% | < 99.0% (warning), < 98.0% (critical) |
| **P99 Latency** | < 2000ms | > 2000ms (warning), > 2500ms (critical) |
| **Data Loss** | 0 records | > 0 (critical) |
| **Error Rate** | < 0.5% | > 1.0% (warning), > 2.0% (critical) |

### Error Budget

**Monthly (30 days):**
- Allowed downtime: 3.6 hours (0.5%)
- Allowed failed requests: 0.5%

**Weekly (7 days):**
- Allowed downtime: 50.4 minutes
- Allowed failed requests: 0.5%

## 🚀 Usage

### Basic Commands

```bash
# Quick validation (skips chaos and k6)
./run_validation.sh quick

# Full validation (all tests)
./run_validation.sh full

# Individual tests
./run_validation.sh locust    # Load testing with Locust
./run_validation.sh k6        # Load testing with k6
./run_validation.sh chaos     # Chaos engineering
./run_validation.sh security  # Security audit
./run_validation.sh backup    # Backup/restore testing

# Utilities
./run_validation.sh check     # Check prerequisites
./run_validation.sh results   # View results
./run_validation.sh clean     # Clean up reports
```

### Python API

```bash
# Full validation
python run_production_validation.py --full

# Quick validation
python run_production_validation.py --quick

# Skip specific tests
python run_production_validation.py --skip chaos security

# Individual tests
locust -f locust_load_test.py --headless --users=50 --run-time=10m
python chaos_engineering.py
python security_audit.py
python test_backup_restore.py
```

## 📊 Results and Reports

After validation, check these files:

**Main Report:**
- `production_validation_report.json` - Consolidated results with SLO compliance

**Individual Reports:**
- `locust_results.json` - Load test metrics (JSON)
- `locust_report.html` - Load test metrics (HTML)
- `k6_results.json` - k6 test results (if run)
- `chaos_report.json` - Chaos engineering results
- `security_audit_report.json` - Security findings
- `trivy_scan_results.json` - Container vulnerabilities
- `backup_restore_report.json` - Backup test results

**Example Report:**
```json
{
  "timestamp": "2024-01-15T10:00:00Z",
  "duration_seconds": 3000,
  "overall_status": "PASSED",
  "slo_compliance": {
    "availability": {"target": 99.5, "met": true, "actual": 99.8},
    "p99_latency": {"target": 2000, "met": true, "actual": 1450},
    "data_loss": {"target": 0, "met": true, "actual": 0}
  }
}
```

## 🔧 Installation

### Prerequisites

- Docker and Docker Compose
- Python 3.11+
- At least 8GB RAM
- At least 50GB disk space

### Install Dependencies

```bash
# Python dependencies
pip install -r requirements-production-validation.txt

# Optional: k6 (recommended)
# Linux
curl https://github.com/grafana/k6/releases/download/v0.47.0/k6-v0.47.0-linux-amd64.tar.gz -L | tar xvz
sudo cp k6-v0.47.0-linux-amd64/k6 /usr/local/bin

# macOS
brew install k6

# Optional: Trivy (recommended)
# Linux
curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh -s -- -b /usr/local/bin

# macOS
brew install aquasecurity/trivy/trivy
```

### Verify Installation

```bash
# Check services
docker compose ps

# Check health endpoints
curl http://localhost:8000/health
curl http://localhost:9002/health
curl http://localhost:9100/health

# Check tools
python3 --version
locust --version
k6 version  # if installed
trivy --version  # if installed
```

## 🔄 CI/CD Integration

### GitHub Actions

```yaml
name: Production Validation
on:
  schedule:
    - cron: '0 2 * * 0'  # Weekly on Sunday
  workflow_dispatch:

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install -r requirements-production-validation.txt
      - run: docker compose up -d
      - run: sleep 60
      - run: python run_production_validation.py --full
      - uses: actions/upload-artifact@v3
        with:
          name: validation-reports
          path: '*_report.json'
```

### Scheduled Validation

```bash
# Add to crontab for weekly validation
0 2 * * 0 cd /path/to/repo && ./run_validation.sh full >> /var/log/validation.log 2>&1
```

## 📈 Monitoring Integration

### Prometheus

Query SLO metrics:
```promql
# Availability
(sum(rate(http_requests_total{status="200"}[5m])) / 
 sum(rate(http_requests_total[5m]))) * 100

# P99 Latency
histogram_quantile(0.99, 
  sum(rate(http_request_duration_seconds_bucket[5m])) by (le))

# Error Rate
(sum(rate(http_requests_total{status=~"5.."}[5m])) / 
 sum(rate(http_requests_total[5m]))) * 100
```

### Grafana

Import dashboards from `configs/grafana/dashboards/`:
- SLO tracking dashboard
- API performance metrics
- Infrastructure monitoring

### Alertmanager

Configure alerts in `configs/prometheus/alert_rules.yml`:
- Availability < 99%
- P99 latency > 2000ms
- Data loss detected
- Error rate > 1%

## 🐛 Troubleshooting

### Common Issues

**High error rates:**
```bash
# Check service logs
docker compose logs -f api-server
docker compose logs -f gateway

# Check resource usage
docker stats

# Verify database connections
docker compose exec postgres pg_isready
```

**Timeout errors:**
```bash
# Check service health
curl http://localhost:8000/health
curl http://localhost:9002/health

# Verify network connectivity
docker compose exec api-server ping gateway

# Check resource allocation
docker inspect api-server | jq '.[0].HostConfig.Memory'
```

**Failed chaos tests:**
```bash
# Check restart policies
docker inspect api-server | jq '.[0].HostConfig.RestartPolicy'

# Verify health checks
docker inspect api-server | jq '.[0].State.Health'

# Test recovery manually
docker compose restart api-server
sleep 30
curl http://localhost:8000/health
```

See [PRODUCTION_VALIDATION.md](PRODUCTION_VALIDATION.md#troubleshooting) for detailed troubleshooting.

## 📅 Recommended Schedule

- **Daily**: Quick validation (10 minutes)
- **Weekly**: Full validation (60 minutes)
- **Monthly**: Extended validation + DR test
- **Quarterly**: Full DR drill + SLO review

## ✅ Success Criteria

### Overall Success
- ✓ All tests pass
- ✓ All SLOs met
- ✓ No critical vulnerabilities
- ✓ Zero data loss verified
- ✓ Resilience score ≥ 90%
- ✓ Security score ≥ 95%

### Per-Test Success
- **Load Testing**: P99 < 2s, Availability ≥ 99.5%
- **Chaos Engineering**: Resilience ≥ 90%
- **Security Audit**: No critical vulnerabilities
- **Backup/Restore**: 100% success rate, zero data loss

## 🎓 Best Practices

1. **Run regularly** - Weekly minimum for full validation
2. **Monitor trends** - Track SLO compliance over time
3. **Review reports** - Don't just check pass/fail
4. **Update tests** - Keep current with system changes
5. **Automate everything** - Integrate into CI/CD
6. **Document failures** - Learn from issues
7. **Test DR regularly** - Quarterly full DR tests
8. **Keep updated** - Security patches and dependencies
9. **Maintain runbooks** - For incident response
10. **Celebrate successes** - When SLOs are met!

## 📦 Components

### Files Created

| File | Purpose |
|------|---------|
| `k6_load_test.js` | k6 load testing script |
| `locust_load_test.py` | Locust load testing |
| `chaos_engineering.py` | Chaos experiments |
| `security_audit.py` | Security validation |
| `test_backup_restore.py` | Backup/restore testing |
| `run_production_validation.py` | Main orchestrator |
| `run_validation.sh` | Shell automation |
| `slo_definitions.yaml` | SLO configuration |
| `requirements-production-validation.txt` | Dependencies |

### Test Coverage

- ✅ Chat API load testing
- ✅ RAG service load testing
- ✅ MCP gateway load testing
- ✅ Container restart resilience
- ✅ CPU/Memory pressure handling
- ✅ Network partition recovery
- ✅ Container vulnerability scanning
- ✅ Penetration testing (8 types)
- ✅ Backup creation validation
- ✅ Restore verification
- ✅ Data integrity checks
- ✅ Zero data loss validation

## 🆘 Support

For questions or issues:

1. **Check Documentation**:
   - [Quick Start](PRODUCTION_VALIDATION_QUICKSTART.md)
   - [Complete Guide](PRODUCTION_VALIDATION.md)
   - [Checklist](PRODUCTION_VALIDATION_CHECKLIST.md)

2. **Review Logs**:
   ```bash
   docker compose logs -f
   cat production_validation_report.json | jq
   ```

3. **Check Service Health**:
   ```bash
   docker compose ps
   ./run_validation.sh check
   ```

4. **Examine Reports**:
   - Look at individual test reports
   - Check error messages in JSON
   - Review service logs during failures

## 🔗 Related Documentation

- [Backup System](BACKUP_README.md)
- [Security Features](SECURITY_FEATURES.md)
- [Observability](OBSERVABILITY_README.md)
- [Disaster Recovery](DISASTER_RECOVERY_RUNBOOK.md)
- [Agent Router](AGENT_ROUTER.md)
- [Architecture](ARCHITECTURE.md)

## 📄 License

See repository license.

## 🤝 Contributing

1. Keep tests updated with system changes
2. Add new test scenarios as features evolve
3. Improve SLO definitions based on learnings
4. Document issues and resolutions
5. Share best practices with team

---

**Production validation is complete and ready to use!**

**Key Features:**
- ✅ Comprehensive load testing (k6 + Locust)
- ✅ Chaos engineering (4 experiment types)
- ✅ Security auditing (Trivy + penetration tests)
- ✅ Backup/restore validation
- ✅ SLO compliance verification (99.5% availability, P99 < 2s, zero data loss)
- ✅ Automated orchestration
- ✅ Detailed reporting
- ✅ CI/CD ready
- ✅ Complete documentation

**Get started:** `./run_validation.sh quick`
