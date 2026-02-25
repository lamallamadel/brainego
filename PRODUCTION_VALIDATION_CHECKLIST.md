# Production Validation Checklist

Quick reference checklist for running production validation.

## Pre-Validation Checklist

### System Requirements
- [ ] Docker installed and running
- [ ] Docker Compose v2.0+
- [ ] Python 3.11+
- [ ] At least 8GB RAM available
- [ ] At least 50GB disk space

### Services Health
- [ ] All containers running: `docker compose ps`
- [ ] API server healthy: `curl http://localhost:8000/health`
- [ ] Gateway healthy: `curl http://localhost:9002/health`
- [ ] MCP gateway healthy: `curl http://localhost:9100/health`
- [ ] PostgreSQL accessible
- [ ] Redis accessible
- [ ] Qdrant accessible

### Dependencies
- [ ] Python dependencies installed: `pip install -r requirements-production-validation.txt`
- [ ] k6 installed (optional): `k6 version`
- [ ] Trivy installed (optional): `trivy --version`
- [ ] Locust installed: `locust --version`
- [ ] Docker SDK installed: `pip show docker`

### Configuration
- [ ] SLO definitions reviewed: `slo_definitions.yaml`
- [ ] Environment variables set (if needed)
- [ ] Network connectivity verified
- [ ] Sufficient resources allocated to containers

## Validation Execution Checklist

### Quick Validation (10 minutes)
- [ ] Run: `python run_production_validation.py --quick`
- [ ] Or: `./run_validation.sh quick`
- [ ] Wait for completion
- [ ] Check exit code (0 = success)

### Full Validation (50-60 minutes)
- [ ] Run: `python run_production_validation.py --full`
- [ ] Or: `./run_validation.sh full`
- [ ] Monitor progress
- [ ] Check for errors
- [ ] Wait for completion

### Individual Tests

#### Load Testing - Locust
- [ ] Run: `./run_validation.sh locust`
- [ ] Check `locust_results.json`
- [ ] Review `locust_report.html`
- [ ] Verify P99 latency < 2000ms
- [ ] Verify availability ≥ 99.5%

#### Load Testing - k6
- [ ] Verify k6 installed
- [ ] Run: `./run_validation.sh k6`
- [ ] Check `k6_results.json`
- [ ] Verify SLO thresholds met

#### Chaos Engineering
- [ ] Run: `./run_validation.sh chaos`
- [ ] Check `chaos_report.json`
- [ ] Verify resilience score ≥ 90%
- [ ] Check no critical failures

#### Security Audit
- [ ] Run: `./run_validation.sh security`
- [ ] Check `security_audit_report.json`
- [ ] Review `trivy_scan_results.json`
- [ ] Verify security score ≥ 95%
- [ ] Check no critical vulnerabilities

#### Backup/Restore
- [ ] Run: `./run_validation.sh backup`
- [ ] Check `backup_restore_report.json`
- [ ] Verify zero data loss
- [ ] Verify 100% success rate

## Post-Validation Checklist

### Review Results
- [ ] Check `production_validation_report.json`
- [ ] Review overall status (PASSED/FAILED)
- [ ] Check SLO compliance section
- [ ] Review individual test results
- [ ] Examine any failures

### SLO Compliance
- [ ] Availability ≥ 99.5%: `___ %` ☐ PASS ☐ FAIL
- [ ] P99 Latency < 2000ms: `___ ms` ☐ PASS ☐ FAIL
- [ ] Data Loss = 0: `___ records` ☐ PASS ☐ FAIL
- [ ] Error Rate < 0.5%: `___ %` ☐ PASS ☐ FAIL

### Test Results
- [ ] Locust load test: ☐ PASS ☐ FAIL
- [ ] k6 load test: ☐ PASS ☐ FAIL ☐ SKIPPED
- [ ] Chaos engineering: ☐ PASS ☐ FAIL
- [ ] Security audit: ☐ PASS ☐ FAIL
- [ ] Backup/restore: ☐ PASS ☐ FAIL

### Report Analysis
- [ ] Load test metrics reviewed
- [ ] Chaos experiment results analyzed
- [ ] Security vulnerabilities assessed
- [ ] Backup integrity verified
- [ ] Error logs examined (if failures)

### Actions Required
- [ ] Document any failures
- [ ] Create issues for improvements
- [ ] Update runbooks if needed
- [ ] Notify stakeholders of results
- [ ] Archive reports

## Troubleshooting Checklist

### High Error Rates
- [ ] Check service logs: `docker compose logs -f`
- [ ] Verify resource usage: `docker stats`
- [ ] Check database connections
- [ ] Review rate limiting configuration
- [ ] Check network connectivity

### Timeout Errors
- [ ] Increase timeout in test configs
- [ ] Check service health endpoints
- [ ] Verify resource allocation
- [ ] Review service performance
- [ ] Check for deadlocks

### Failed Chaos Tests
- [ ] Check Docker restart policies
- [ ] Verify health check configuration
- [ ] Review resource availability
- [ ] Examine container logs
- [ ] Test recovery manually

### Security Vulnerabilities
- [ ] Review vulnerability details
- [ ] Check if patches available
- [ ] Update base images
- [ ] Document accepted risks
- [ ] Create remediation plan

### Backup Failures
- [ ] Check service connectivity
- [ ] Verify credentials
- [ ] Test backup service manually
- [ ] Review backup logs
- [ ] Check disk space

## Reporting Checklist

### Documentation
- [ ] Update validation log
- [ ] Document any issues found
- [ ] Create incident reports (if failures)
- [ ] Update SLO tracking dashboard
- [ ] Archive validation reports

### Communication
- [ ] Notify team of results
- [ ] Escalate critical issues
- [ ] Update status page (if applicable)
- [ ] Send summary to stakeholders
- [ ] Schedule follow-up if needed

### Follow-up Actions
- [ ] Create tickets for improvements
- [ ] Schedule fixes for issues
- [ ] Update documentation
- [ ] Plan next validation
- [ ] Review SLO targets if needed

## Weekly Validation Checklist

Use this for regular weekly validation:

**Date:** _______________  
**Validator:** _______________  
**Duration:** _______________

### Pre-Flight
- [ ] All services running
- [ ] Dependencies installed
- [ ] Previous reports archived

### Execution
- [ ] Run full validation
- [ ] Monitor progress
- [ ] Note any issues

### Results
- [ ] Overall status: ☐ PASS ☐ FAIL
- [ ] Availability: ___ %
- [ ] P99 Latency: ___ ms
- [ ] Data Loss: ___ records
- [ ] Issues found: _______________

### Actions
- [ ] Reports reviewed
- [ ] Issues documented
- [ ] Stakeholders notified
- [ ] Next validation scheduled

### Sign-off
- [ ] Validation complete
- [ ] Results acceptable
- [ ] Follow-up planned

**Notes:**
_______________________________________________
_______________________________________________
_______________________________________________

## Quick Reference Commands

### Setup
```bash
# Install dependencies
pip install -r requirements-production-validation.txt

# Make script executable
chmod +x run_validation.sh

# Check prerequisites
./run_validation.sh check
```

### Run Validation
```bash
# Quick (10 min)
./run_validation.sh quick

# Full (60 min)
./run_validation.sh full

# Individual tests
./run_validation.sh locust
./run_validation.sh k6
./run_validation.sh chaos
./run_validation.sh security
./run_validation.sh backup
```

### Check Results
```bash
# View results
./run_validation.sh results

# Check specific report
cat production_validation_report.json | jq '.overall_status'
cat production_validation_report.json | jq '.slo_compliance'

# View HTML report
open locust_report.html  # macOS
xdg-open locust_report.html  # Linux
```

### Cleanup
```bash
# Remove result files
./run_validation.sh clean
```

## Validation Frequency

- **Daily**: Quick validation (10 min)
- **Weekly**: Full validation (60 min)
- **Monthly**: Extended validation + DR test
- **Quarterly**: Full DR drill + SLO review

## Contact Information

**On-Call Engineer:** _______________  
**Team Lead:** _______________  
**Emergency Contact:** _______________

## Resources

- [Full Guide](PRODUCTION_VALIDATION.md)
- [Quick Start](PRODUCTION_VALIDATION_QUICKSTART.md)
- [SLO Definitions](slo_definitions.yaml)
- [Troubleshooting Guide](PRODUCTION_VALIDATION.md#troubleshooting)

---

**Last Updated:** _______________  
**Next Review:** _______________
