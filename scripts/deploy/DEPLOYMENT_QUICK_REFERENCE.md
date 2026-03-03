# Deployment Quick Reference Card

## Normal Deployment (with smoke tests)

```bash
# 1. Source deployment config
source /opt/brainego/env/deploy.env

# 2. Deploy with smoke tests
sudo -E bash scripts/deploy/deploy_vm.sh deploy <sha>
```

**What happens**:
- ✅ Build & deploy
- ✅ Activate symlink
- ✅ Start services
- ✅ Health checks
- ✅ **Smoke tests** (automatic)
- ✅ Success → Mark successful + Slack notification
- ❌ Failure → **Auto-rollback** to previous release

---

## Emergency Deployment (skip smoke tests)

```bash
sudo bash scripts/deploy/deploy_vm.sh deploy <sha> \
  --skip-smoke \
  --skip-reason "Emergency hotfix for [INCIDENT-ID]"
```

**What happens**:
- ✅ Build & deploy
- ✅ Activate symlink
- ✅ Start services
- ✅ Health checks
- ⚠️ **Smoke tests SKIPPED**
- ⚠️ Audit log + Slack warning
- ✅ Mark successful (but **NOT validated**)

**Use only for**: P0 incidents, critical security patches, production outages

---

## Rollback to Previous Release

```bash
sudo bash scripts/deploy/deploy_vm.sh rollback previous
```

**Rollback to Specific Release**:
```bash
sudo bash scripts/deploy/deploy_vm.sh rollback <sha>
```

---

## Check Deployment Status

```bash
sudo bash scripts/deploy/deploy_vm.sh status
```

**Shows**:
- Current & previous versions
- Available releases
- Running services
- Recent downtime log
- **Rollback log** (auto-rollbacks)
- **Skip-smoke audit** (skipped smoke tests)

---

## View Smoke Test Logs

```bash
# Most recent smoke test
cat /opt/brainego/logs/smoke_tests_*.log | tail -n 100

# Specific release
cat /opt/brainego/logs/smoke_tests_<sha>.log
```

---

## View Service Logs

```bash
# All services (last 100 lines, follow mode)
sudo bash scripts/deploy/deploy_vm.sh logs

# Specific service (last 50 lines)
sudo bash scripts/deploy/deploy_vm.sh logs api-server 50
```

---

## Environment Variables (Required)

**Minimal**:
```bash
export SMOKE_TEST_BASE_URL="http://localhost:8000"
export SMOKE_TEST_WORKSPACE_ID="production"
```

**Recommended**:
```bash
export SMOKE_TEST_AUTH_TOKEN="your-token"
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."
export PROMETHEUS_URL="http://prometheus:9090"
export KONG_ADMIN_URL="http://kong-admin:8001"
```

Save to `/opt/brainego/env/deploy.env` and source before deployment.

---

## Audit Logs

### Rollback Log
**File**: `/opt/brainego/logs/rollback.log`

**Format**: `timestamp|failed_sha|restored_sha|trigger|reason`

**View**:
```bash
cat /opt/brainego/logs/rollback.log
```

### Skip-Smoke Audit Log
**File**: `/opt/brainego/audit/skip-smoke.log`

**Format**: `timestamp|sha|actor|reason`

**View**:
```bash
cat /opt/brainego/audit/skip-smoke.log
```

---

## Common Troubleshooting

### Smoke tests failing

**Check smoke test log**:
```bash
cat /opt/brainego/logs/smoke_tests_<sha>.log
```

**Common causes**:
- Service not ready (wait 30s and retry)
- Auth token invalid/expired
- Base URL incorrect
- Missing dependencies (httpx, pyyaml)

### Auto-rollback triggered

**Check what happened**:
```bash
sudo bash scripts/deploy/deploy_vm.sh status
cat /opt/brainego/logs/rollback.log
```

**Action**:
1. Review smoke test log
2. Fix issues
3. Redeploy

### Rollback failed (CRITICAL)

**Immediate action required**:
1. Check previous release exists: `ls /opt/brainego/releases/`
2. Manually restore symlink: `ln -sfn /opt/brainego/releases/<good_sha> /opt/brainego/current`
3. Restart services: `cd /opt/brainego/current && docker-compose restart`
4. Page on-call engineer

---

## Exit Codes

- **0**: Success
- **1**: Failure (deployment failed OR auto-rollback completed)

---

## Deployment Checklist

### Before Deployment

- [ ] Review changes in staging
- [ ] Smoke tests pass in staging
- [ ] Backup database (if schema changes)
- [ ] Notify team in #deployments Slack channel
- [ ] Set `SLACK_WEBHOOK_URL` for alerts

### During Deployment

- [ ] Monitor deployment output
- [ ] Watch for smoke test results
- [ ] Check Slack for alerts

### After Deployment

- [ ] Verify smoke tests passed
- [ ] Check `/status` for rollback entries
- [ ] Monitor application metrics
- [ ] Update deployment log in Linear/Jira

### If Auto-Rollback Triggered

- [ ] Review smoke test logs
- [ ] Investigate failure cause
- [ ] Fix issues
- [ ] Test in staging
- [ ] Redeploy with fixes

---

## Emergency Contacts

- **On-call Engineer**: [pager/phone]
- **Slack Channel**: `#deployments`
- **Incident Response**: `#incidents`

---

## Quick Links

- [Full Documentation](README_SMOKE_TESTS.md)
- [Smoke Test Script](prod_smoke_tests.py)
- [Deployment Script](deploy_vm.sh)
- [Environment Template](deploy.env.example)
