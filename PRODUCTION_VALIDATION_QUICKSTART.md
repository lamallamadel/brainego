# Production Validation Quick Start

Get started with production validation in 5 minutes.

## Prerequisites

- Docker and Docker Compose running
- Python 3.11+
- Services deployed and healthy

## 1. Install Dependencies

```bash
# Install production validation dependencies
pip install -r requirements-production-validation.txt

# Install k6 (optional but recommended)
# Linux
curl https://github.com/grafana/k6/releases/download/v0.47.0/k6-v0.47.0-linux-amd64.tar.gz -L | tar xvz
sudo cp k6-v0.47.0-linux-amd64/k6 /usr/local/bin

# macOS
brew install k6

# Install Trivy (optional but recommended)
# Linux
curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh -s -- -b /usr/local/bin

# macOS
brew install aquasecurity/trivy/trivy
```

## 2. Verify Services

```bash
# Check all services are running
docker compose ps

# Verify health endpoints
curl http://localhost:8000/health
curl http://localhost:9002/health
curl http://localhost:9100/health
```

## 3. Run Quick Validation

```bash
# Quick validation (10 minutes)
python run_production_validation.py --quick

# This skips chaos engineering and k6 for faster results
```

## 4. Run Full Validation

```bash
# Full validation suite (50-60 minutes)
python run_production_validation.py --full
```

## 5. Check Results

```bash
# View main report
cat production_validation_report.json | jq

# Check SLO compliance
cat production_validation_report.json | jq '.slo_compliance'

# Overall status
cat production_validation_report.json | jq '.overall_status'
```

## Individual Tests

### Load Testing with Locust

```bash
# Headless mode
locust -f locust_load_test.py \
    --host=http://localhost:8000 \
    --users=50 \
    --spawn-rate=5 \
    --run-time=10m \
    --headless

# Interactive web UI
locust -f locust_load_test.py --host=http://localhost:8000
# Open http://localhost:8089
```

### Load Testing with k6

```bash
# Basic run
k6 run k6_load_test.js

# Custom settings
k6 run --vus 50 --duration 10m k6_load_test.js
```

### Chaos Engineering

```bash
# Run all chaos experiments
python chaos_engineering.py

# View results
cat chaos_report.json | jq
```

### Security Audit

```bash
# Run security audit
python security_audit.py

# View results
cat security_audit_report.json | jq
```

### Backup/Restore Testing

```bash
# Run backup/restore tests
python test_backup_restore.py

# View results
cat backup_restore_report.json | jq
```

## Understanding Results

### SLO Compliance

All tests check against these targets:
- **Availability**: ≥ 99.5%
- **P99 Latency**: < 2000ms
- **Data Loss**: 0 records

### Success Indicators

**PASSED Status:**
```json
{
  "overall_status": "PASSED",
  "slo_compliance": {
    "availability": {"met": true, "actual": 99.8},
    "p99_latency": {"met": true, "actual": 1450},
    "data_loss": {"met": true}
  }
}
```

**FAILED Status:**
```json
{
  "overall_status": "FAILED",
  "slo_compliance": {
    "availability": {"met": false, "actual": 98.2},
    "p99_latency": {"met": true, "actual": 1800},
    "data_loss": {"met": true}
  }
}
```

## Common Issues

### Services Not Ready

```bash
# Wait for all services to be healthy
docker compose ps

# Check service logs
docker compose logs -f api-server
docker compose logs -f gateway
```

### Port Conflicts

```bash
# Check if ports are in use
netstat -tuln | grep -E '8000|9002|9100'

# Stop conflicting services
docker compose down
docker compose up -d
```

### High Error Rates

```bash
# Check resource usage
docker stats

# Verify database connections
docker compose logs postgres
docker compose logs redis
docker compose logs qdrant
```

### Timeout Errors

```bash
# Increase timeout in test configs
# Edit locust_load_test.py or k6_load_test.js

# Check network connectivity
docker compose exec api-server curl max-serve-llama:8080/health
```

## Scheduled Validation

### Weekly Validation

Add to crontab:
```bash
# Run validation every Sunday at 2 AM
0 2 * * 0 cd /path/to/repo && python run_production_validation.py --full >> /var/log/validation.log 2>&1
```

### Continuous Monitoring

Start validation service:
```bash
# Run validation loop
while true; do
    python run_production_validation.py --quick
    sleep 3600  # Run every hour
done
```

## Integration with CI/CD

### GitHub Actions

Create `.github/workflows/production-validation.yml`:
```yaml
name: Production Validation
on:
  schedule:
    - cron: '0 2 * * 0'  # Weekly
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
      - run: sleep 60  # Wait for services
      - run: python run_production_validation.py --full
      - uses: actions/upload-artifact@v3
        with:
          name: reports
          path: '*_report.json'
```

## Next Steps

1. **Review Full Documentation**: [PRODUCTION_VALIDATION.md](PRODUCTION_VALIDATION.md)
2. **Check SLO Definitions**: [slo_definitions.yaml](slo_definitions.yaml)
3. **Setup Monitoring**: [Grafana Dashboards](configs/grafana/dashboards/)
4. **Configure Alerts**: [Alert Rules](configs/prometheus/alert_rules.yml)
5. **Review Security**: [SECURITY_FEATURES.md](SECURITY_FEATURES.md)

## Support

For detailed troubleshooting and advanced configuration, see the full [Production Validation Guide](PRODUCTION_VALIDATION.md).

---

**Remember**: Run validation regularly to ensure your system meets SLO commitments!
