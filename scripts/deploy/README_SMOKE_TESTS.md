# Smoke Test Integration & Auto-Rollback

## Overview

The `deploy_vm.sh` script now integrates `prod_smoke_tests.py` as a post-deployment hook with automatic rollback on failure.

## Features

### 1. Post-Deploy Smoke Tests

After symlink activation and service startup, the deployment script automatically runs comprehensive smoke tests:

- **Health & Metrics**: `/health`, `/metrics` endpoints
- **Authentication**: Kong auth enforcement
- **Core APIs**: Chat completions, RAG queries, MCP tools with RBAC
- **Monitoring**: Prometheus metrics validation

### 2. Auto-Rollback on Failure

If smoke tests fail, the script automatically:

1. **Restores symlink** to previous release
2. **Restarts services** via `docker-compose restart`
3. **Logs rollback trail** with:
   - Release ID (failed SHA)
   - Previous release ID (restored SHA)
   - Timestamp (ISO 8601 UTC)
   - Failure reason

**Rollback log format** (pipe-delimited):
```
timestamp|failed_sha|restored_sha|trigger|reason
```

Example:
```
2024-01-15T14:32:45Z|abc123f|def456a|smoke_test_failure|smoke_tests_failed
```

**Log location**: `/opt/brainego/logs/rollback.log`

### 3. Skip-Smoke Flag

For emergency hotfixes, you can skip smoke tests with the `--skip-smoke` flag:

```bash
sudo bash scripts/deploy/deploy_vm.sh deploy abc123f \
  --skip-smoke \
  --skip-reason "Emergency P0 hotfix for critical security vulnerability"
```

**Required**: `--skip-smoke` MUST be accompanied by `--skip-reason`

**Optional**: `--skip-actor <actor>` (defaults to current user)

#### Skip-Smoke Audit Trail

When smoke tests are skipped, the script:

1. **Writes audit log** to `/opt/brainego/audit/skip-smoke.log`
2. **Posts Slack warning** (if `SLACK_WEBHOOK_URL` configured)
3. **Continues deployment** without smoke validation

**Audit log format** (pipe-delimited):
```
timestamp|sha|actor|reason
```

Example:
```
2024-01-15T14:32:45Z|abc123f|john.doe|Emergency P0 hotfix for critical security vulnerability
```

**Slack notification** (warning color):
```
⚠️ DEPLOYMENT WARNING: Smoke tests skipped for release abc123f
Reason: Emergency P0 hotfix for critical security vulnerability
Actor: john.doe
Host: prod-vm-01

⚠️ This deployment has NOT been validated via smoke tests.
```

## Usage

### Normal Deployment (with smoke tests)

```bash
# Set environment variables
export SMOKE_TEST_BASE_URL="http://localhost:8000"
export SMOKE_TEST_WORKSPACE_ID="production"
export SMOKE_TEST_AUTH_TOKEN="your-auth-token"
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"

# Deploy
sudo -E bash scripts/deploy/deploy_vm.sh deploy abc123f
```

**Flow**:
1. Build & deploy release `abc123f`
2. Activate symlink
3. Start services
4. Run health checks
5. **Run smoke tests**
6. ✅ Success → Mark release successful, send Slack success notification
7. ❌ Failure → Auto-rollback to previous release, send Slack failure alert

### Emergency Deployment (skip smoke tests)

```bash
sudo bash scripts/deploy/deploy_vm.sh deploy abc123f \
  --skip-smoke \
  --skip-reason "Emergency hotfix for CVE-2024-1234" \
  --skip-actor "oncall-engineer"
```

**Flow**:
1. Build & deploy release `abc123f`
2. Activate symlink
3. Start services
4. Run health checks
5. **Skip smoke tests** (log audit entry, send Slack warning)
6. Mark release successful (no validation)

### Configuration

Create `/opt/brainego/env/deploy.env` from template:

```bash
cp scripts/deploy/deploy.env.example /opt/brainego/env/deploy.env
vim /opt/brainego/env/deploy.env
```

**Example configuration**:
```bash
# Smoke Test Configuration
SMOKE_TEST_BASE_URL="http://localhost:8000"
SMOKE_TEST_WORKSPACE_ID="production"
SMOKE_TEST_AUTH_TOKEN="Bearer eyJhbGc..."

# Optional monitoring
PROMETHEUS_URL="http://prometheus:9090"
KONG_ADMIN_URL="http://kong-admin:8001"

# Slack notifications
SLACK_WEBHOOK_URL="https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXX"
```

Then source before deployment:
```bash
source /opt/brainego/env/deploy.env
sudo -E bash scripts/deploy/deploy_vm.sh deploy abc123f
```

## Rollback Log Structure

**File**: `/opt/brainego/logs/rollback.log`

**Format**: `timestamp|failed_sha|restored_sha|trigger|reason`

**Triggers**:
- `smoke_test_failure`: Automated rollback due to failed smoke tests
- `manual_rollback`: Manual rollback via `rollback` command

**Example entries**:
```
2024-01-15T14:32:45Z|abc123f|def456a|smoke_test_failure|smoke_tests_failed
2024-01-15T14:35:12Z|abc123f|def456a|rollback_success|
2024-01-16T09:15:33Z|ghi789j|def456a|smoke_test_failure|smoke_tests_failed
```

**View recent rollbacks**:
```bash
sudo bash scripts/deploy/deploy_vm.sh status
```

Output includes:
```
Recent rollback log (last 10 entries):
Timestamp                    Failed SHA  Restored SHA  Trigger              Reason
2024-01-15T14:32:45Z        abc123f     def456a       smoke_test_failure   smoke_tests_failed
```

## Skip-Smoke Audit Log Structure

**File**: `/opt/brainego/audit/skip-smoke.log`

**Format**: `timestamp|sha|actor|reason`

**Example entries**:
```
2024-01-15T14:32:45Z|abc123f|john.doe|Emergency P0 hotfix for critical security vulnerability
2024-01-16T09:15:33Z|ghi789j|oncall-engineer|Smoke tests timing out due to infra issue
```

**View recent skip-smoke events**:
```bash
sudo bash scripts/deploy/deploy_vm.sh status
```

Output includes:
```
Smoke test skip audit (last 10 entries):
Timestamp                    SHA      Actor             Reason
2024-01-15T14:32:45Z        abc123f  john.doe          Emergency P0 hotfix for critical security vulnerability
```

## Slack Notifications

The script sends Slack notifications for key deployment events (if `SLACK_WEBHOOK_URL` is configured):

### Success Notification (green)
```
✅ DEPLOYMENT SUCCESS: Release abc123f deployed and validated
Host: prod-vm-01
Previous: def456a
```

### Smoke Tests Skipped (yellow/warning)
```
⚠️ DEPLOYMENT WARNING: Smoke tests skipped for release abc123f
Reason: Emergency hotfix for CVE-2024-1234
Actor: oncall-engineer
Host: prod-vm-01

⚠️ This deployment has NOT been validated via smoke tests.
```

### Deployment Failed with Rollback (red/danger)
```
🚨 DEPLOYMENT FAILED: Release abc123f failed smoke tests and was auto-rolled back to def456a
Host: prod-vm-01

Action required: Review smoke test logs and fix issues before redeploying.
```

### Critical: Rollback Failed (red/danger)
```
🔥 CRITICAL: Deployment abc123f failed smoke tests AND rollback failed
Host: prod-vm-01

⚠️ IMMEDIATE ACTION REQUIRED - System may be unstable!
```

## Smoke Test Logs

Each deployment generates a smoke test log:

**Location**: `/opt/brainego/logs/smoke_tests_<sha>.log`

**Example**: `/opt/brainego/logs/smoke_tests_abc123f.log`

**View smoke test log**:
```bash
cat /opt/brainego/logs/smoke_tests_abc123f.log
```

**Last 30 lines** are automatically shown in deployment output if tests fail.

## Error Handling

### Scenario 1: Smoke Tests Fail (Previous Release Available)

```
[ERROR] SMOKE TESTS FAILED - INITIATING AUTO-ROLLBACK
Failed release: abc123f
Rolling back to: def456a
Reason: smoke_tests_failed

[SUCCESS] Rollback completed successfully
Active release: def456a
```

**Exit code**: `1`

### Scenario 2: Smoke Tests Fail (No Previous Release)

```
[ERROR] No previous version available for rollback
```

**Exit code**: `1`

**Action required**: Manual investigation and fix

### Scenario 3: Smoke Tests Fail + Rollback Fails

```
[ERROR] CRITICAL: ROLLBACK FAILED!
Deployment failed AND rollback failed
Manual intervention required immediately
```

**Exit code**: `1`

**Action required**: Immediate manual intervention

### Scenario 4: Smoke Tests Skipped

```
[WARN] SMOKE TESTS SKIPPED - RISK ACCEPTED
RISK ACCEPTED: Smoke tests skipped for abc123f
Reason: Emergency P0 hotfix
Actor: oncall-engineer
Proceeding without smoke test validation
```

**Exit code**: `0` (success, but not validated)

## Prerequisites

### Required Commands

- `docker`
- `docker-compose`
- `git`
- `bc`
- `python3`
- `curl`

### Python Dependencies

The `prod_smoke_tests.py` script requires:

```
httpx>=0.25.1
pyyaml>=6.0.1
```

Add to `requirements-deploy.txt` or install:
```bash
pip install httpx pyyaml
```

## Best Practices

### ✅ DO

- **Always run smoke tests** for normal deployments
- **Configure Slack webhook** for real-time alerts
- **Review rollback logs** regularly to identify patterns
- **Document skip-smoke reasons** thoroughly
- **Test smoke tests** in staging before production

### ❌ DON'T

- **Skip smoke tests** without a critical reason (P0 incident, security hotfix)
- **Use vague skip-smoke reasons** ("just testing", "in a hurry")
- **Ignore rollback failures** (requires immediate manual intervention)
- **Deploy without smoke test validation** in prod without explicit approval

## Troubleshooting

### Smoke tests not running

**Check**:
1. Script exists: `/opt/brainego/releases/<sha>/scripts/deploy/prod_smoke_tests.py`
2. Python3 available: `which python3`
3. Dependencies installed: `python3 -m pip list | grep httpx`

### Rollback failed

**Check**:
1. Previous release directory exists: `ls /opt/brainego/releases/`
2. Docker Compose working: `docker-compose ps`
3. Permissions: Deployment script must run as root/sudo

### Slack notifications not working

**Check**:
1. `SLACK_WEBHOOK_URL` environment variable set
2. Webhook URL valid and active
3. Network connectivity: `curl -I https://hooks.slack.com`
4. Webhook permissions in Slack workspace

## Security Considerations

- **Audit logs** are append-only (no rotation by deployment script)
- **Skip-smoke reasons** are logged and auditable
- **Slack notifications** do NOT include secrets/tokens
- **Auth tokens** are passed via environment (not command-line args)
- **Rollback logs** include actor/timestamp for accountability

## Monitoring & Alerting

Set up alerts for:

1. **Frequent rollbacks** (> 2 per day) → Potential CI/CD issue
2. **Frequent skip-smoke** (> 1 per week) → Process violation
3. **Rollback failures** (any occurrence) → Critical incident
4. **Smoke test failures** (> 3 consecutive) → Systemic issue

Query rollback log:
```bash
# Count rollbacks today
grep "$(date -u +%Y-%m-%d)" /opt/brainego/logs/rollback.log | wc -l

# Count skip-smoke events this week
grep "$(date -u +%Y-%m)" /opt/brainego/audit/skip-smoke.log | wc -l
```

## Example Deployment Session

### Normal Deployment

```bash
$ source /opt/brainego/env/deploy.env
$ sudo -E bash scripts/deploy/deploy_vm.sh deploy abc123f

[INFO] Starting deployment of version: abc123f
[INFO] Current version: def456a
[INFO] Previous version: xyz789b
[INFO] Building Docker images...
[SUCCESS] Images built successfully
[INFO] Running migrations...
[SUCCESS] Migrations completed
[INFO] Stopping current services...
[INFO] Starting new services...
[SUCCESS] Switchover complete. Downtime: 12.5s
[SUCCESS] ✓ Downtime within target: 12.5s ≤ 30s
[INFO] Performing health checks...
[SUCCESS] All services are healthy

[INFO] ======================================================================
[INFO] POST-DEPLOY HOOK: Running Smoke Tests
[INFO] ======================================================================
[INFO] Smoke test configuration:
[INFO]   Base URL: http://localhost:8000
[INFO]   Workspace ID: production
[INFO]   Log file: /opt/brainego/logs/smoke_tests_abc123f.log
[SUCCESS] Smoke tests passed
[SUCCESS] Smoke tests passed - deployment validated

[SUCCESS] ======================================================================
[SUCCESS] Deployment of abc123f completed successfully!
[SUCCESS] ======================================================================
[INFO] Release directory: /opt/brainego/releases/abc123f
[INFO] Current symlink: /opt/brainego/current -> /opt/brainego/releases/abc123f
```

### Emergency Deployment (Skip Smoke)

```bash
$ sudo bash scripts/deploy/deploy_vm.sh deploy abc123f \
    --skip-smoke \
    --skip-reason "Emergency hotfix for CVE-2024-1234"

[INFO] Starting deployment of version: abc123f
...
[WARN] ======================================================================
[WARN] SMOKE TESTS SKIPPED - RISK ACCEPTED
[WARN] ======================================================================
[WARN] RISK ACCEPTED: Smoke tests skipped for abc123f
[WARN] Reason: Emergency hotfix for CVE-2024-1234
[WARN] Actor: root
[WARN] Audit logged to: /opt/brainego/audit/skip-smoke.log
[WARN] Proceeding without smoke test validation

[SUCCESS] ======================================================================
[SUCCESS] Deployment of abc123f completed successfully!
[SUCCESS] ======================================================================
```

### Failed Deployment (Auto-Rollback)

```bash
$ sudo -E bash scripts/deploy/deploy_vm.sh deploy bad123x

[INFO] Starting deployment of version: bad123x
...
[INFO] ======================================================================
[INFO] POST-DEPLOY HOOK: Running Smoke Tests
[INFO] ======================================================================
[ERROR] Smoke tests failed with exit code: 1
[ERROR] ======================================================================
[ERROR] SMOKE TESTS FAILED - INITIATING AUTO-ROLLBACK
[ERROR] ======================================================================
[ERROR] Failed release: bad123x
[ERROR] Rolling back to: abc123f
[ERROR] Reason: smoke_tests_failed

[INFO] Stopping services from failed release bad123x...
[INFO] Restoring symlink to previous release abc123f...
[INFO] Restarting services from previous release...
[SUCCESS] Services restarted successfully
[INFO] Waiting for services to stabilize...
[SUCCESS] Rollback completed successfully
[SUCCESS] Active release: abc123f

[ERROR] Deployment FAILED and ROLLED BACK to abc123f
[ERROR] Review smoke test logs before redeploying
```
