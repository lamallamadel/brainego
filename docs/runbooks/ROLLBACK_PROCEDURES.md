# Rollback Procedures Runbook

## Table of Contents
1. [Overview](#overview)
2. [When to Rollback](#when-to-rollback)
3. [Application Rollback](#application-rollback)
4. [Configuration Rollback](#configuration-rollback)
5. [Database Rollback Strategy](#database-rollback-strategy)
6. [Post-Rollback Validation](#post-rollback-validation)
7. [Communication Template](#communication-template)
8. [Troubleshooting](#troubleshooting)

---

## Overview

This runbook provides comprehensive procedures for rolling back deployments in the brainego platform. Rollbacks restore the system to a previous known-good state when forward fixes are not viable within the incident response window.

### Rollback Philosophy

**Principles**:
- Rollback is a tactical mitigation, not a long-term fix
- Always validate before considering rollback complete
- Document every rollback for post-mortem analysis
- Communicate proactively with stakeholders

**Key Concepts**:
- **Application Rollback**: Restore previous application code version
- **Config Rollback**: Revert configuration changes without code rollback
- **DB Rollback**: Special case - prefer forward-only migrations
- **Validation**: Smoke tests + metrics verification post-rollback

---

## When to Rollback

### Rollback Decision Matrix

| Scenario | Error Rate | Performance | User Impact | Action |
|----------|-----------|-------------|-------------|--------|
| Critical production bug | >10% | Any | >50% users | **Rollback immediately** |
| Smoke test failure | Auto-detected | Any | Pre-production | **Auto-rollback** (deploy_vm.sh) |
| Performance degradation | 5-10% | >50% slower | >25% users | **Rollback** (with approval) |
| Minor bug with fix | <1% | <25% slower | <10% users | **Fix forward** |
| Config issue only | Any | Any | Any | **Config rollback** (no code) |
| DB migration failure | Any | Any | Any | **DO NOT rollback** (see DB strategy) |

### Rollback vs Fix Forward

**Rollback if**:
- Critical bug introduced in production (P0)
- Cannot fix forward within 30 minutes
- Smoke tests failed (automatic rollback)
- Performance degradation >50%
- Security vulnerability introduced
- Data corruption risk identified

**Fix forward if**:
- Minor bug with known fix (<15 min to deploy)
- Issue affects <1% of users
- Rollback would cause more disruption (e.g., DB schema incompatibility)
- Hot-fixable via config change or feature flag

### Prerequisites for Manual Rollback

- [ ] Incident declared and documented
- [ ] Rollback decision approved (P0: Engineering Manager, P1: Senior SRE)
- [ ] Stakeholders notified (see Communication Template)
- [ ] Current deployment version identified
- [ ] Previous version verified available in release history
- [ ] Production access credentials ready
- [ ] Post-rollback validation plan prepared

---

## Application Rollback

### Architecture Overview

The brainego platform uses a **versioned release deployment** model:

```
/opt/brainego/
├── releases/
│   ├── abc123f/          # Release 1 (git SHA)
│   ├── def456a/          # Release 2 (git SHA)
│   └── ghi789b/          # Release 3 (git SHA) ← current
├── current -> releases/ghi789b/  # Symlink to active release
├── env/
│   └── prod.env          # Shared environment config
└── logs/
    ├── deployment.log    # Deployment history
    ├── rollback.log      # Rollback audit trail
    └── downtime.log      # Downtime measurements
```

**Benefits**:
- Fast rollback (symlink switch + container restart)
- Previous releases retained on disk
- Zero-downtime deployment target (≤30s)
- Automatic smoke test rollback

---

### Rollback Procedure

#### Step 1: Verify Current State and Prerequisites

**Check running version**:

```bash
# Check current deployed version
./scripts/deploy/deploy_vm.sh status

# Output shows:
# - Current version (git SHA)
# - Previous version (git SHA)
# - Available releases
# - Service health
# - Recent rollback history
```

**Prerequisites check** (automated by `deploy_vm.sh rollback`):

- [ ] Running as root/sudo
- [ ] Required commands available: `docker`, `docker-compose`, `git`, `bc`, `python3`
- [ ] Environment file exists: `/opt/brainego/env/prod.env`
- [ ] Previous release directory exists
- [ ] Current symlink is valid

**Manual verification**:

```bash
# Verify previous release exists
ls -la /opt/brainego/releases/

# Check current symlink
readlink -f /opt/brainego/current

# Verify Docker daemon running
docker ps

# Check service status
cd /opt/brainego/current
docker-compose ps
```

---

#### Step 2: Execute Rollback

**Automatic rollback to previous version**:

```bash
# Rollback to the most recent previous version
sudo ./scripts/deploy/deploy_vm.sh rollback previous

# This command will:
# 1. Validate prerequisites (docker, env file, etc.)
# 2. Identify previous version from release history
# 3. Stop current services (docker-compose down)
# 4. Switch symlink atomically to previous release
# 5. Start services from previous release
# 6. Run health checks
# 7. Measure and log downtime
# 8. Log rollback to audit trail
```

**Rollback to specific version**:

```bash
# Rollback to a specific git SHA
sudo ./scripts/deploy/deploy_vm.sh rollback abc123f

# Use case: Skip broken release, go back 2+ versions
```

**What happens during rollback**:

1. **Prerequisite check**: Validates environment, commands, access
2. **Version validation**: Ensures target SHA exists in `/opt/brainego/releases/`
3. **Service shutdown**: `docker-compose down --remove-orphans` on current version
4. **Symlink switch**: Atomic replacement of `/opt/brainego/current`
5. **Service restart**: `docker-compose up -d` with `IMAGE_TAG=<previous_sha>`
6. **Health check**: Waits up to 60s for services to be healthy
7. **Downtime logging**: Records rollback duration to `/opt/brainego/logs/downtime.log`
8. **Audit trail**: Logs to `/opt/brainego/logs/rollback.log`

**Expected output**:

```
[INFO] Rolling back from ghi789b to def456a
[INFO] Stopping services from current release...
[INFO] Restoring symlink to previous release...
[INFO] Restarting services from previous release...
[INFO] Performing health checks...
[SUCCESS] All services are healthy
[SUCCESS] Rollback complete. Downtime: 12.34s
[SUCCESS] Rollback to def456a completed successfully!
```

---

#### Step 3: Monitor Rollback Progress

**Watch service startup**:

```bash
# Follow logs for all services
./scripts/deploy/deploy_vm.sh logs

# Or specific service
./scripts/deploy/deploy_vm.sh logs api-server 50

# Or direct docker-compose logs
cd /opt/brainego/current
docker-compose logs -f --tail=50
```

**Check container health**:

```bash
# Verify all containers running
docker-compose ps

# Expected output:
# NAME                STATE         STATUS
# api-server          running       Up 30s (healthy)
# gateway             running       Up 30s (healthy)
# postgres            running       Up 30s (healthy)
# qdrant              running       Up 30s (healthy)
```

**Monitor metrics**:

```bash
# Check error rate (should decrease)
curl -s 'http://localhost:9090/api/v1/query?query=rate(http_requests_total{status=~"5.."}[5m])' | jq

# Check latency (should normalize)
curl -s 'http://localhost:9090/api/v1/query?query=histogram_quantile(0.99,rate(http_request_duration_seconds_bucket[5m]))' | jq

# Check in Grafana (visual monitoring)
open http://localhost:3000/d/sre-incident-response
```

---

#### Step 4: Verify Rollback Success

See [Post-Rollback Validation](#post-rollback-validation) section below for comprehensive validation steps.

**Quick verification**:

```bash
# 1. Health check
curl http://localhost:8000/health | jq '.'
# Expected: {"status": "healthy", "version": "def456a", ...}

# 2. Basic smoke test
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama-3.3-8b",
    "messages": [{"role": "user", "content": "Hello"}],
    "max_tokens": 10
  }' | jq '.'

# 3. Check Prometheus metrics
curl -s http://localhost:9090/api/v1/query?query=up | jq '.data.result[] | select(.value[1]=="0")'
# Should return empty (all services up)

# 4. Verify version in logs
docker-compose logs api-server | grep "Starting brainego" | tail -1
```

---

#### Step 5: Update Documentation and Stakeholders

**Log rollback details**:

```bash
# Rollback is automatically logged to:
cat /opt/brainego/logs/rollback.log

# Format: timestamp|failed_sha|restored_sha|trigger|reason
# Example:
# 2025-01-30T15:23:45Z|ghi789b|def456a|manual|high_error_rate_p1_incident
```

**Review rollback history**:

```bash
# View recent rollbacks
./scripts/deploy/deploy_vm.sh status
# Shows "Recent rollback log (last 10 entries)"

# Or direct file view
tail -10 /opt/brainego/logs/rollback.log | column -t -s '|'
```

**Update stakeholders**: See [Communication Template](#communication-template) section.

---

### Automatic Rollback on Smoke Test Failure

The `deploy_vm.sh` script includes **automatic rollback** when post-deployment smoke tests fail.

**How it works**:

1. Deployment runs (`deploy_vm.sh deploy <sha>`)
2. Services start successfully
3. Smoke tests execute (`scripts/deploy/prod_smoke_tests.py`)
4. **If smoke tests fail**:
   - Deployment is marked as failed
   - Previous release is identified
   - Services are stopped
   - Symlink is restored to previous release
   - Services are restarted from previous release
   - Rollback is logged to audit trail
   - Slack alert is sent (if configured)
5. **Exit code 1** - deployment failed and rolled back

**Disabling auto-rollback** (emergency only):

```bash
# Skip smoke tests (requires explicit reason)
sudo ./scripts/deploy/deploy_vm.sh deploy abc123f \
  --skip-smoke \
  --skip-reason "Emergency P0 hotfix for critical security issue" \
  --skip-actor "john.doe"

# This logs the skip decision to audit trail:
# /opt/brainego/audit/skip-smoke.log
```

**⚠️ WARNING**: Skipping smoke tests is **high risk**. Only use for:
- Emergency P0 hotfixes where smoke test environment is down
- Critical security patches that must deploy immediately
- Situations where rollback would be more dangerous than proceeding

**Audit trail**:

```bash
# Review smoke test skip history
cat /opt/brainego/audit/skip-smoke.log | tail -10 | column -t -s '|'

# Format: timestamp|sha|actor|reason
# Example:
# 2025-01-30T16:45:00Z|abc123f|john.doe|Emergency P0 hotfix for CVE-2025-1234
```

---

## Configuration Rollback

Configuration changes (environment variables, feature flags, ConfigMaps) can be rolled back **without full application rollback**.

### When to Use Config Rollback

**Use config rollback when**:
- Issue is caused by a config change, not code change
- Application code is working correctly
- Faster than full application rollback
- No DB schema changes involved

**Examples**:
- Feature flag enabling broken feature
- Environment variable causing performance issue (e.g., connection pool size)
- Rate limit threshold too low/high
- Timeout value incorrect

---

### Git Revert + Redeploy Flow

**Step 1: Identify the problematic config commit**:

```bash
# View recent config changes
cd /opt/brainego/current
git log --oneline --decorate -- configs/ .env.example | head -10

# Or view specific file history
git log --oneline -- configs/api-config.yaml

# Show diff for specific commit
git show abc123f -- configs/api-config.yaml
```

**Step 2: Create revert commit**:

```bash
# Revert the specific config commit (creates new commit)
git revert abc123f --no-edit

# Or revert specific file from previous commit
git checkout HEAD~1 -- configs/api-config.yaml
git commit -m "revert(config): restore API config to previous working state

Reverted due to P1 incident INC-20250130-1523
Previous commit: abc123f caused high latency issue"

# Push to repo
git push origin main
```

**Step 3: Deploy the reverted config**:

```bash
# Deploy the revert commit
NEW_SHA=$(git rev-parse HEAD)
sudo ./scripts/deploy/deploy_vm.sh deploy $NEW_SHA

# This will:
# 1. Deploy new release with reverted config
# 2. Run migrations (if any)
# 3. Switch traffic to new release
# 4. Run smoke tests
# 5. Auto-rollback if smoke tests fail
```

**Alternative: Fast config-only update** (no new deployment):

If the config is managed outside git (e.g., `/opt/brainego/env/prod.env`):

```bash
# 1. Edit the config file directly
sudo nano /opt/brainego/env/prod.env

# 2. Restart affected services to pick up changes
cd /opt/brainego/current
docker-compose restart api-server

# 3. Verify config applied
docker-compose logs api-server | grep "Config loaded"

# 4. Run smoke tests manually
python3 scripts/deploy/prod_smoke_tests.py --base-url http://localhost:8000
```

---

### Feature Flag Rollback

**Disable problematic feature via API** (if supported):

```bash
# Disable feature flag immediately (no deployment)
curl -X POST http://localhost:8000/admin/features/disable \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  -d '{
    "feature": "new_inference_pipeline",
    "reason": "High error rate in production",
    "disabled_by": "oncall-sre"
  }'

# Verify feature disabled
curl http://localhost:8000/admin/features | jq '.features.new_inference_pipeline'
# Expected: {"enabled": false, "disabled_at": "...", "reason": "..."}

# Monitor metrics for improvement
curl -s 'http://localhost:9090/api/v1/query?query=rate(http_requests_total{status=~"5.."}[5m])' | jq
```

**Or revert via git**:

```bash
# If feature flags are in git-managed config file
git show HEAD~1 -- configs/features.yaml > /tmp/features-reverted.yaml

# Apply to running system (method depends on config management)
# Option A: Restart service with new config
sudo cp /tmp/features-reverted.yaml /opt/brainego/current/configs/features.yaml
cd /opt/brainego/current
docker-compose restart api-server

# Option B: Deploy as new release (safer, uses deployment pipeline)
git checkout HEAD~1 -- configs/features.yaml
git commit -m "revert(features): disable new_inference_pipeline feature"
git push origin main
sudo ./scripts/deploy/deploy_vm.sh deploy $(git rev-parse HEAD)
```

---

### Environment Variable Rollback

**Docker Compose environment**:

```bash
# 1. Edit .env file in current release
cd /opt/brainego/current
sudo nano .env

# Example: Revert DB_POOL_SIZE from 100 to 50
# Before: DB_POOL_SIZE=100
# After:  DB_POOL_SIZE=50

# 2. Restart affected services
docker-compose restart api-server

# 3. Verify new value applied
docker-compose exec api-server env | grep DB_POOL_SIZE
# Expected: DB_POOL_SIZE=50

# 4. Monitor for improvement
docker-compose logs -f api-server
```

**Kubernetes environment** (if applicable):

```bash
# Update deployment env vars
kubectl set env deployment/api-server \
  DB_POOL_SIZE=50 \
  MAX_CONNECTIONS=100 \
  -n production

# Verify rollout
kubectl rollout status deployment/api-server -n production

# Check pod using new values
kubectl get pods -l app=api-server -n production
kubectl logs -l app=api-server --tail=20 -n production | grep "DB_POOL_SIZE"
```

---

## Database Rollback Strategy

### Forward-Only Migrations Policy

**Policy**: brainego follows a **forward-only migration strategy**. Database schema changes are **NOT** rolled back during application rollback.

**Rationale**:
- Backward migrations risk data loss
- Schema rollback can corrupt data
- Application code should be backward-compatible with schema
- Emergency data restore is a separate procedure

**Implications**:
- **Application rollback does NOT rollback database**
- New application version must work with new schema
- Old application version must work with new schema (graceful degradation)

---

### When NOT to Rollback Database

**DO NOT rollback database in these scenarios**:

1. **Application rollback**: Old code must tolerate new schema
2. **Minor schema additions**: New columns with defaults, new tables (no impact)
3. **Data-preserving migrations**: Renamed columns, added indexes (reversible but risky)
4. **Production runtime**: Rolling back schema during incident response is **too risky**

**Example**:

```
Deployment sequence:
1. Deploy new schema: Add column `users.email_verified` (default: false)
2. Deploy application code that uses `email_verified`
3. Smoke tests fail → Application rollback
4. Old code must handle `email_verified` column existing (graceful degradation)
   - Option 1: Ignore the column (SELECT only needed fields)
   - Option 2: Check if column exists before using
5. Database schema remains at new version
```

---

### When to Consider Database Rollback (Rare)

**Only rollback database when**:

1. **Migration failed mid-execution** (corrupted state)
   - Action: Restore from pre-migration backup
   - Requires downtime

2. **Data corruption detected immediately** (within backup window)
   - Action: Point-in-time restore
   - Requires downtime

3. **Schema change breaks ALL application versions** (catastrophic error)
   - Action: Manual schema rollback + data migration
   - Requires extended downtime and approval

**Approval required**: Engineering Manager + Database Administrator + Architect

---

### Emergency Database Restore Procedure

**Use Case**: Migration failed critically, system unstable, data corruption detected

**⚠️ WARNING**: This procedure causes **extended downtime** (10-60 minutes depending on DB size)

**Step 1: Declare Incident and Get Approval**:

```bash
# Incident severity: P0 (data corruption/loss risk)
# Required approval: Engineering Manager + DBA

# Notify in #incidents channel:
# "🚨 P0: Database corruption detected. Initiating emergency restore procedure."
# "Estimated downtime: 30-45 minutes"
# "Approval from: @eng-manager @dba-lead"
```

**Step 2: Stop All Services** (prevent new writes):

```bash
# Stop application services (keep database running)
cd /opt/brainego/current
docker-compose stop api-server gateway learning-engine drift-monitor

# Verify no active connections (except restore process)
docker exec postgres psql -U ai_user -d ai_platform -c "
  SELECT count(*) FROM pg_stat_activity WHERE datname='ai_platform';
"
# Should be minimal (1-2 connections)
```

**Step 3: Identify Restore Point**:

```bash
# List available backups
ls -lh /opt/brainego/backups/postgres/ | tail -10

# Identify backup before problematic migration
# Example: postgres_backup_20250130_020000.dump (pre-migration)

# Verify backup integrity
sha256sum /opt/brainego/backups/postgres/postgres_backup_20250130_020000.dump
# Compare with checksum file

# Check backup timestamp matches desired restore point
```

**Step 4: Execute Restore**:

```bash
# Drop and recreate database (⚠️ destructive!)
docker exec postgres psql -U ai_user -d postgres -c "
  SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='ai_platform';
  DROP DATABASE ai_platform;
  CREATE DATABASE ai_platform OWNER ai_user;
"

# Restore from backup
docker exec -i postgres pg_restore \
  -U ai_user \
  -d ai_platform \
  --verbose \
  --clean \
  --if-exists \
  < /opt/brainego/backups/postgres/postgres_backup_20250130_020000.dump

# Check restore status
echo $?  # Should be 0
```

**Step 5: Validate Database State**:

```bash
# Check tables exist
docker exec postgres psql -U ai_user -d ai_platform -c "\dt"

# Verify row counts match expectations
docker exec postgres psql -U ai_user -d ai_platform -c "
  SELECT 'users' as table_name, count(*) FROM users
  UNION ALL
  SELECT 'sessions', count(*) FROM sessions
  UNION ALL
  SELECT 'conversations', count(*) FROM conversations;
"

# Check schema version (should be pre-migration version)
docker exec postgres psql -U ai_user -d ai_platform -c "
  SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 5;
"
```

**Step 6: Restart Services**:

```bash
# Start services
cd /opt/brainego/current
docker-compose start api-server gateway learning-engine drift-monitor

# Wait for services to be healthy
docker-compose ps

# Run smoke tests
python3 scripts/deploy/prod_smoke_tests.py --base-url http://localhost:8000
```

**Step 7: Document Restore**:

```bash
# Log to incident report:
# - Backup used: postgres_backup_20250130_020000.dump
# - Data loss window: 02:00 - 15:23 UTC (13h 23m of data lost)
# - Restore duration: 27 minutes
# - Services restarted: 15:50 UTC
# - Smoke tests passed: 15:52 UTC
```

---

### Database Schema Hotfix (Alternative to Restore)

**Use Case**: Migration introduced schema bug, but data is intact

**Procedure**:

```bash
# 1. Identify the problematic migration
docker exec postgres psql -U ai_user -d ai_platform -c "
  SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 5;
"

# 2. Create a forward-fix migration (DO NOT rollback migration)
cat > migrations/20250130_153000_fix_email_column.sql <<'EOF'
-- Fix: Previous migration created email column as TEXT instead of VARCHAR(255)
ALTER TABLE users ALTER COLUMN email TYPE VARCHAR(255);
-- Add missing index
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
EOF

# 3. Apply the fix migration
docker exec postgres psql -U ai_user -d ai_platform -f /migrations/20250130_153000_fix_email_column.sql

# 4. Verify fix applied
docker exec postgres psql -U ai_user -d ai_platform -c "\d+ users"

# 5. Restart application (if needed)
cd /opt/brainego/current
docker-compose restart api-server
```

---

## Post-Rollback Validation

Validation is **mandatory** before declaring rollback successful. Do not skip validation steps.

### Validation Checklist

#### 1. Service Health Checks

**All containers running**:

```bash
# Check container status
docker-compose ps

# Expected: All services "Up" with "healthy" status
# If any service is "Restarting" or "Unhealthy", investigate logs

# Check for restart loops
docker-compose ps | grep -E "Restarting|Restart"
# Should return empty
```

**Application health endpoint**:

```bash
# Check health endpoint
curl -f http://localhost:8000/health | jq '.'

# Expected response:
# {
#   "status": "healthy",
#   "version": "def456a",
#   "timestamp": "2025-01-30T15:30:00Z",
#   "checks": {
#     "database": "healthy",
#     "qdrant": "healthy",
#     "redis": "healthy"
#   }
# }

# If health check fails (exit code != 0), rollback is NOT successful
if ! curl -f http://localhost:8000/health > /dev/null 2>&1; then
  echo "❌ Health check failed - rollback incomplete"
  exit 1
fi
```

**Database connectivity**:

```bash
# PostgreSQL connection test
docker exec postgres psql -U ai_user -d ai_platform -c "SELECT 1"
# Expected: 1 row returned

# Check for active connections
docker exec postgres psql -U ai_user -d ai_platform -c "
  SELECT count(*), state FROM pg_stat_activity WHERE datname='ai_platform' GROUP BY state;
"
# Expected: Multiple "active" and "idle" connections

# Qdrant health
curl -f http://localhost:6333/health
# Expected: HTTP 200

# Redis health (if applicable)
docker exec redis redis-cli ping
# Expected: PONG
```

---

#### 2. Smoke Tests

**Automated smoke test suite**:

```bash
# Run production smoke tests
cd /opt/brainego/current
python3 scripts/deploy/prod_smoke_tests.py \
  --base-url http://localhost:8000 \
  --workspace-id default

# Expected output:
# ✅ Health check: PASS
# ✅ Chat completion: PASS
# ✅ Embedding generation: PASS
# ✅ RAG query: PASS
# ✅ Memory store: PASS
# ✅ Drift monitoring: PASS
# All tests passed (6/6)

# If any test fails, investigate before declaring rollback successful
```

**Manual smoke test** (if automated tests unavailable):

```bash
# 1. Basic chat completion
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama-3.3-8b",
    "messages": [{"role": "user", "content": "Say hello"}],
    "max_tokens": 50
  }' | jq '.choices[0].message.content'
# Expected: Response with "hello" content

# 2. Embedding generation
curl -X POST http://localhost:8000/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama-3.3-8b",
    "input": "test embedding"
  }' | jq '.data[0].embedding | length'
# Expected: Number (embedding dimension, e.g., 4096)

# 3. Health check
curl http://localhost:8000/health | jq '.status'
# Expected: "healthy"
```

---

#### 3. Metrics Verification

**Error rate returned to baseline**:

```bash
# Check 5xx error rate (should be <1%)
ERROR_RATE=$(curl -s 'http://localhost:9090/api/v1/query?query=rate(http_requests_total{status=~"5.."}[5m])' | jq -r '.data.result[0].value[1] // 0')

echo "Current error rate: $ERROR_RATE"

# Validate error rate < 0.01 (1%)
if (( $(echo "$ERROR_RATE > 0.01" | bc -l) )); then
  echo "❌ Error rate still elevated: $ERROR_RATE"
else
  echo "✅ Error rate normal: $ERROR_RATE"
fi
```

**Latency within SLA**:

```bash
# Check P99 latency (should be <1s for chat completion)
P99_LATENCY=$(curl -s 'http://localhost:9090/api/v1/query?query=histogram_quantile(0.99,rate(http_request_duration_seconds_bucket{endpoint="/v1/chat/completions"}[5m]))' | jq -r '.data.result[0].value[1] // 0')

echo "Current P99 latency: ${P99_LATENCY}s"

# Validate latency < 1s
if (( $(echo "$P99_LATENCY > 1.0" | bc -l) )); then
  echo "⚠️ Latency still elevated: ${P99_LATENCY}s"
else
  echo "✅ Latency within SLA: ${P99_LATENCY}s"
fi
```

**Request rate stable**:

```bash
# Check request rate (should match pre-incident baseline)
REQUEST_RATE=$(curl -s 'http://localhost:9090/api/v1/query?query=rate(http_requests_total[5m])' | jq -r '.data.result[0].value[1] // 0')

echo "Current request rate: ${REQUEST_RATE} req/s"

# Compare with baseline (example: 100 req/s ± 20%)
# Adjust baseline based on your traffic patterns
BASELINE=100
if (( $(echo "$REQUEST_RATE < $BASELINE * 0.8" | bc -l) )); then
  echo "⚠️ Request rate lower than expected: ${REQUEST_RATE} req/s (baseline: ${BASELINE} req/s)"
  echo "   Possible causes: traffic not restored, upstream issue, users abandoning"
fi
```

**Grafana dashboard review**:

```bash
# Open SRE incident response dashboard
open http://localhost:3000/d/sre-incident-response

# Verify visually:
# - Error rate graph trending down
# - Latency graph returning to baseline
# - No new alerts firing
# - CPU/Memory usage stable
# - Database connection pool healthy
```

---

#### 4. Alert Status

**Verify all alerts cleared**:

```bash
# Check Alertmanager for firing alerts
curl -s http://localhost:9093/api/v1/alerts | jq '.data[] | select(.status.state=="active")'

# Expected: Empty (no active alerts)
# If alerts still firing, rollback may not have fixed the issue
```

**Check Prometheus alerts**:

```bash
# Check for pending or firing alerts
curl -s http://localhost:9090/api/v1/alerts | jq '.data.alerts[] | select(.state!="inactive") | {name:.labels.alertname, state:.state, value:.value}'

# Expected: Empty or only non-critical alerts
```

---

#### 5. Log Review

**Check for errors in last 5 minutes**:

```bash
# Review recent logs for errors
docker-compose logs --since=5m | grep -i -E "error|exception|fatal" | tail -20

# If errors found, investigate:
# - Are they related to the rollback?
# - Are they pre-existing issues?
# - Do they indicate rollback failure?
```

**Review service startup logs**:

```bash
# Check that services started cleanly
docker-compose logs api-server | grep "Starting brainego" | tail -1
docker-compose logs api-server | grep -i "error" | tail -10

# Look for:
# - Successful startup messages
# - No connection errors
# - No configuration errors
```

---

### Automated Validation Script

**Create validation script**:

```bash
#!/bin/bash
# /opt/brainego/scripts/validate_rollback.sh

set -e

echo "🔍 Running post-rollback validation..."

# 1. Health check
echo "Checking health endpoint..."
if ! curl -f http://localhost:8000/health > /dev/null 2>&1; then
  echo "❌ Health check failed"
  exit 1
fi
echo "✅ Health check passed"

# 2. Error rate
echo "Checking error rate..."
ERROR_RATE=$(curl -s 'http://localhost:9090/api/v1/query?query=rate(http_requests_total{status=~"5.."}[5m])' | jq -r '.data.result[0].value[1] // 0')
if (( $(echo "$ERROR_RATE > 0.01" | bc -l) )); then
  echo "❌ Error rate too high: $ERROR_RATE"
  exit 1
fi
echo "✅ Error rate normal: $ERROR_RATE"

# 3. Latency
echo "Checking latency..."
LATENCY=$(curl -s 'http://localhost:9090/api/v1/query?query=histogram_quantile(0.99,rate(http_request_duration_seconds_bucket[5m]))' | jq -r '.data.result[0].value[1] // 0')
if (( $(echo "$LATENCY > 1.0" | bc -l) )); then
  echo "⚠️ Latency elevated: ${LATENCY}s (warning, not failure)"
else
  echo "✅ Latency acceptable: ${LATENCY}s"
fi

# 4. Smoke tests
echo "Running smoke tests..."
if ! python3 /opt/brainego/current/scripts/deploy/prod_smoke_tests.py --base-url http://localhost:8000; then
  echo "❌ Smoke tests failed"
  exit 1
fi
echo "✅ Smoke tests passed"

# 5. Alerts
echo "Checking for active alerts..."
ACTIVE_ALERTS=$(curl -s http://localhost:9093/api/v1/alerts | jq -r '.data[] | select(.status.state=="active") | .labels.alertname')
if [ -n "$ACTIVE_ALERTS" ]; then
  echo "⚠️ Active alerts: $ACTIVE_ALERTS"
  echo "   Review alerts before declaring rollback successful"
else
  echo "✅ No active alerts"
fi

echo ""
echo "✅ All validation checks passed"
echo "Rollback is successful and system is stable"
```

**Run validation**:

```bash
sudo bash /opt/brainego/scripts/validate_rollback.sh
```

---

## Communication Template

Effective communication is critical during rollback incidents.

### Internal Communication (Slack)

**Rollback initiated message** (`#incidents` channel):

```
🔄 ROLLBACK INITIATED
Incident ID: INC-20250130-1523
Severity: P1
Trigger: High error rate (12%) after deployment of abc123f

Action: Rolling back to previous version def456a
Initiated by: @oncall-sre
Started: 2025-01-30 15:23 UTC

Expected completion: 15:30 UTC (7 min)
Downtime: Minimal (~15-30s during switchover)

Next update: 15:30 UTC

Commands:
  sudo ./scripts/deploy/deploy_vm.sh rollback previous

Grafana: http://localhost:3000/d/sre-incident-response
Runbook: docs/runbooks/ROLLBACK_PROCEDURES.md
```

**Rollback completed message**:

```
✅ ROLLBACK COMPLETED
Incident ID: INC-20250130-1523

Action: Rolled back from abc123f to def456a
Completed: 2025-01-30 15:29 UTC
Duration: 6 minutes
Downtime: 14.2 seconds

Status: All services healthy ✅
- Health checks passing
- Error rate: 0.3% (baseline)
- Latency P99: 245ms (within SLA)
- Smoke tests: PASSED

Next steps:
1. Continue monitoring for 30 minutes
2. Investigate root cause of abc123f failure
3. Schedule post-mortem for tomorrow 10:00 UTC

Assigned: @oncall-sre
```

**Rollback failed message** (escalation):

```
🚨 ROLLBACK FAILED - ESCALATION REQUIRED
Incident ID: INC-20250130-1523

Action: Attempted rollback to def456a
Status: FAILED ❌

Error: Services failed to start after rollback
Details: PostgreSQL connection errors, schema incompatibility

Current state:
- All services DOWN
- Investigating schema mismatch
- May require database restore

Escalated to: @senior-sre @dba-lead @eng-manager

Immediate action:
- Assessing database restore need
- Estimating extended downtime (30-60 min)

Next update: 15:40 UTC (10 min) or sooner if critical

War room: Zoom link [TODO: add link]
```

---

### External Communication (Status Page)

**Rollback in progress**:

```
Title: Service Degradation - Rollback in Progress
Status: Monitoring
Posted: 2025-01-30 15:23 UTC

We are experiencing elevated error rates affecting chat completion requests. 
We have identified the issue and are rolling back to the previous version.

Impact:
- Chat completion API: Partial degradation (12% error rate)
- Other services: Operating normally

Expected resolution: 15:30 UTC (7 minutes)

We will provide an update once the rollback is complete.
```

**Rollback completed**:

```
Title: Service Degradation - Resolved
Status: Resolved
Updated: 2025-01-30 15:30 UTC

The issue has been resolved. We successfully rolled back to the previous 
version and all services are operating normally.

Impact:
- Chat completion API: Fully restored
- Downtime: 14 seconds during rollback

Next steps:
- We are investigating the root cause
- No further user action required

We apologize for any inconvenience.
```

---

### Stakeholder Email Template

**Subject**: [P1] Production Rollback Completed - Service Restored

**Body**:

```
Hi team,

We experienced a production incident today that required a rollback. The issue has been resolved and services are fully operational.

Incident Summary:
- Incident ID: INC-20250130-1523
- Severity: P1
- Duration: 15:23 UTC - 15:30 UTC (7 minutes)
- Impact: Chat completion API experienced 12% error rate

Action Taken:
- Rolled back deployment from version abc123f to def456a
- Total downtime: 14.2 seconds during rollback
- All services verified healthy via smoke tests

Current Status:
- All services: Operational ✅
- Error rate: 0.3% (normal baseline)
- Latency: 245ms P99 (within SLA)
- No data loss

Root Cause:
- Under investigation
- Post-mortem scheduled: 2025-01-31 10:00 UTC

User Impact:
- ~12% of chat completion requests failed between 15:23-15:29 UTC
- Estimated affected users: ~150
- No data corruption or loss

Preventive Measures:
- TBD after root cause analysis

Next Steps:
- Continue monitoring for 24 hours
- Complete root cause analysis
- Implement preventive actions

Please let me know if you have any questions.

[Your Name]
On-call SRE
```

---

## Troubleshooting

### Issue: Rollback Command Fails with "Prerequisites check failed"

**Symptom**:

```
[ERROR] Required command not found: docker-compose
[ERROR] Prerequisites check failed
```

**Solution**:

```bash
# Check which prerequisites are missing
which docker docker-compose git bc python3

# Install missing commands (Ubuntu/Debian)
sudo apt-get update
sudo apt-get install -y docker.io docker-compose git bc python3

# Or install via pip (docker-compose)
sudo pip3 install docker-compose

# Verify Docker daemon running
sudo systemctl status docker
sudo systemctl start docker

# Re-run rollback
sudo ./scripts/deploy/deploy_vm.sh rollback previous
```

---

### Issue: "Previous version not found"

**Symptom**:

```
[ERROR] No previous version available for rollback
```

**Root cause**: Only one release exists in `/opt/brainego/releases/`

**Solution**:

```bash
# List available releases
ls -la /opt/brainego/releases/

# If only one release exists, cannot rollback
# Options:
# 1. Deploy a known-good version manually
# 2. Fix forward instead of rollback

# Option 1: Deploy known-good version
git checkout def456a  # Known good commit
sudo ./scripts/deploy/deploy_vm.sh deploy def456a

# Option 2: Fix forward with hotfix
# Make fix, commit, deploy
git commit -am "hotfix: fix critical bug"
sudo ./scripts/deploy/deploy_vm.sh deploy $(git rev-parse HEAD)
```

---

### Issue: Services fail to start after rollback

**Symptom**:

```
[ERROR] Health check failed after rollback
[ERROR] Services failed to become healthy after 30 attempts
```

**Solution**:

```bash
# Check which services are unhealthy
docker-compose ps

# Check logs for errors
docker-compose logs api-server --tail=50
docker-compose logs postgres --tail=50

# Common causes:
# 1. Database schema incompatibility
# 2. Environment variable missing/incorrect
# 3. Port conflict
# 4. Resource exhaustion

# Solution 1: Check database connectivity
docker exec postgres psql -U ai_user -d ai_platform -c "SELECT 1"

# Solution 2: Check environment file
cat /opt/brainego/current/.env | grep -E "DB_|QDRANT_|REDIS_"

# Solution 3: Restart Docker daemon (if resource exhaustion)
sudo systemctl restart docker
cd /opt/brainego/current
docker-compose up -d

# Solution 4: Manual service restart
docker-compose restart api-server
docker-compose logs -f api-server
```

---

### Issue: Error rate still high after rollback

**Symptom**: Rollback completed but error rate remains elevated

**Root cause**: Issue may not be in application code (external dependency, database, infrastructure)

**Solution**:

```bash
# Check if issue is external
# 1. Check database performance
docker exec postgres psql -U ai_user -d ai_platform -c "
  SELECT pid, now() - query_start as duration, query 
  FROM pg_stat_activity 
  WHERE state = 'active' AND now() - query_start > interval '5 seconds';"

# 2. Check Qdrant health
curl http://localhost:6333/health
curl http://localhost:6333/metrics | grep -E "request_duration|error"

# 3. Check resource utilization
docker stats --no-stream

# 4. Check upstream dependencies (if any)
# curl http://external-api.example.com/health

# 5. Scale up if resource constrained
# kubectl scale deployment/api-server --replicas=5 -n production

# If external issue, rollback won't help
# - Fix external dependency
# - Scale up resources
# - Enable circuit breaker/fallback
```

---

### Issue: Database connection errors after rollback

**Symptom**:

```
[ERROR] Could not connect to database
[ERROR] FATAL: password authentication failed for user "ai_user"
```

**Solution**:

```bash
# Check database is running
docker-compose ps postgres

# Check database logs
docker-compose logs postgres --tail=50

# Verify credentials in .env file
cat /opt/brainego/current/.env | grep DB_

# Test connection manually
docker exec postgres psql -U ai_user -d ai_platform -c "SELECT 1"

# If password incorrect, update .env
sudo nano /opt/brainego/current/.env
# Update DB_PASSWORD=<correct_password>

# Restart services
docker-compose restart api-server
```

---

### Issue: Downtime exceeded target (>30s)

**Symptom**: Rollback took longer than expected

**Review downtime log**:

```bash
# Check actual downtime
tail -5 /opt/brainego/logs/downtime.log | column -t -s ','

# Example output:
# 2025-01-30 15:29:45  rollback:def456a  47.3

# Reasons for slow rollback:
# 1. Large Docker images (slow pull/start)
# 2. Database migration on startup
# 3. Service initialization time
# 4. Health check timeout

# Optimization for future rollbacks:
# 1. Keep previous images cached (don't prune)
# 2. Reduce service startup time
# 3. Tune health check intervals
# 4. Consider blue-green deployment for zero-downtime
```

---

### Issue: Automatic rollback triggered incorrectly

**Symptom**: Smoke tests failed due to environment issue, not application bug

**Review smoke test logs**:

```bash
# Check smoke test failure reason
cat /opt/brainego/logs/smoke_tests_abc123f.log | tail -50

# Common false positives:
# - Prometheus not available (smoke test dependency)
# - Network timeout (transient issue)
# - External service down (not application issue)

# If false positive, redeploy with smoke tests skipped:
sudo ./scripts/deploy/deploy_vm.sh deploy abc123f \
  --skip-smoke \
  --skip-reason "Smoke test false positive due to Prometheus outage" \
  --skip-actor "$(whoami)"

# ⚠️ WARNING: Only skip smoke tests if you are CERTAIN the deployment is safe
```

---

## Quick Reference

### Rollback Commands

```bash
# Check deployment status
./scripts/deploy/deploy_vm.sh status

# Rollback to previous version (most common)
sudo ./scripts/deploy/deploy_vm.sh rollback previous

# Rollback to specific version
sudo ./scripts/deploy/deploy_vm.sh rollback <git_sha>

# View logs
./scripts/deploy/deploy_vm.sh logs
./scripts/deploy/deploy_vm.sh logs api-server 50

# View rollback history
cat /opt/brainego/logs/rollback.log | tail -10 | column -t -s '|'

# View downtime log
cat /opt/brainego/logs/downtime.log | tail -10 | column -t -s ','
```

### Validation Commands

```bash
# Health check
curl http://localhost:8000/health | jq '.'

# Error rate
curl -s 'http://localhost:9090/api/v1/query?query=rate(http_requests_total{status=~"5.."}[5m])' | jq

# Latency
curl -s 'http://localhost:9090/api/v1/query?query=histogram_quantile(0.99,rate(http_request_duration_seconds_bucket[5m]))' | jq

# Smoke tests
python3 scripts/deploy/prod_smoke_tests.py --base-url http://localhost:8000

# Service status
docker-compose ps

# Active alerts
curl -s http://localhost:9093/api/v1/alerts | jq '.data[] | select(.status.state=="active")'
```

### File Locations

```
/opt/brainego/
├── releases/<sha>/           # Versioned releases
├── current -> releases/<sha> # Active release symlink
├── env/prod.env              # Production environment config
├── logs/
│   ├── deployment.log        # Deployment history
│   ├── rollback.log          # Rollback audit trail
│   ├── downtime.log          # Downtime measurements
│   └── smoke_tests_<sha>.log # Smoke test results
└── audit/
    └── skip-smoke.log        # Smoke test skip audit
```

---

**Version**: 2.0  
**Last Updated**: 2025-01-30  
**Next Review**: 2025-02-28  
**Owner**: SRE Team
