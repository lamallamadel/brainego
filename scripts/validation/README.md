# Validation Scripts

This directory contains validation scripts for production validation and chaos engineering.

## Ultra-Basic Chaos Suite

### Overview

The ultra-basic chaos suite (`run_production_validation.py`) implements a lightweight chaos engineering test suite specifically designed for production validation.

### Features

1. **Container Kill & Auto-Restart**
   - Kills `api-server` container via `docker compose kill`
   - Verifies automatic restart
   - Measures Mean Time To Recovery (MTTR)
   - Checks if alerts were triggered

2. **Kong Gateway Testing** (if deployed)
   - Kills `kong` container
   - Verifies auto-restart
   - Checks circuit breaker/fallback behavior

3. **CPU Stress Testing**
   - Injects CPU stress on `learning-engine` via `docker exec learning-engine stress-ng --cpu 4 --timeout 60s`
   - Verifies service degrades gracefully
   - Checks if performance alerts fire
   - Service should remain running throughout stress test

4. **Database Integrity Verification**
   - Queries PostgreSQL `schema_migrations` table post-chaos
   - Ensures no database corruption occurred
   - Verifies table is intact and readable

5. **MTTR Report**
   - Generates per-service Mean Time To Recovery report
   - Tracks successful recoveries
   - Records alert triggering status

### What's NOT Included (by design)

- Database failover tests
- Network partition tests
- Memory pressure tests (beyond CPU stress)

### Usage

**Via production validation orchestrator:**
```bash
python run_production_validation.py --chaos-suite basic
```

**Direct execution:**
```bash
python scripts/validation/run_production_validation.py --chaos-suite basic
```

### Requirements

- Docker access for container manipulation
- `stress-ng` (auto-installed in containers during tests)
- PostgreSQL access for integrity checks
- AlertManager running (optional, for alert verification)

### Output

The suite generates a comprehensive JSON report (`chaos_report.json`) containing:
- Test results per service
- MTTR measurements
- Alert triggering status
- Database integrity check results
- Overall pass/fail status

### Example Report Structure

```json
{
  "suite": "ultra-basic",
  "timestamp": "2025-03-03T02:00:00.000000",
  "duration_seconds": 450.5,
  "summary": {
    "total_tests": 4,
    "passed_tests": 4,
    "failed_tests": 0,
    "overall_status": "PASSED"
  },
  "test_results": [
    {
      "test_name": "api_server_kill_restart",
      "service": "api-server",
      "passed": true,
      "details": {
        "recovery_successful": true,
        "mttr_seconds": 45.2,
        "alert_triggered": true
      }
    },
    ...
  ],
  "mttr_report": {
    "api-server": {
      "average_mttr": 45.2,
      "min_mttr": 45.2,
      "max_mttr": 45.2,
      "total_measurements": 1,
      "successful_recoveries": 1,
      "alerts_triggered": 1
    },
    ...
  }
}
```

### Integration with CI/CD

This script can be integrated into CI/CD pipelines for continuous chaos validation:

```yaml
# .github/workflows/chaos-validation.yml
- name: Run Ultra-Basic Chaos Suite
  run: |
    python run_production_validation.py --chaos-suite basic
```

### Exit Codes

- `0`: All tests passed
- `1`: One or more tests failed

### Logging

The suite provides detailed logging at each stage:
- Test start/completion
- Container status changes
- MTTR measurements
- Alert triggering status
- Database integrity checks

### Dependencies

All dependencies are included in `requirements-production-validation.txt`:
- `docker>=7.0.0`
- `psycopg2-binary>=2.9.9`
- `requests>=2.31.0`
