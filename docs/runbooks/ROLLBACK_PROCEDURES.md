# Rollback Procedures Runbook

## Table of Contents
1. [Overview](#overview)
2. [Blue-Green Deployment Rollback](#blue-green-deployment-rollback)
3. [Configuration Rollback](#configuration-rollback)
4. [Database Rollback](#database-rollback)
5. [Kubernetes Rollback](#kubernetes-rollback)
6. [Docker Compose Rollback](#docker-compose-rollback)
7. [LoRA Model Rollback](#lora-model-rollback)
8. [Verification and Validation](#verification-and-validation)
9. [Troubleshooting](#troubleshooting)

---

## Overview

This runbook provides detailed procedures for rolling back various types of deployments and changes in the AI Platform. Rollbacks should be executed when a deployment causes issues that cannot be quickly fixed forward.

### When to Rollback

**Rollback If**:
- Critical bug introduced in production
- Performance degradation > 50%
- Error rate > 5%
- Data corruption risk identified
- Security vulnerability introduced
- Cannot fix forward within 30 minutes

**Fix Forward If**:
- Minor bug with known fix
- Can deploy hotfix within 15 minutes
- Rollback would cause more disruption
- Issue affects <1% of users

### Rollback Decision Matrix

| Issue Severity | Error Rate | Performance Impact | Action |
|----------------|------------|-------------------|--------|
| P0             | >10%       | >75% degradation  | Immediate rollback |
| P1             | 5-10%      | 50-75% degradation| Rollback (with approval) |
| P2             | 1-5%       | 25-50% degradation| Consider rollback vs fix |
| P3             | <1%        | <25% degradation  | Fix forward |

### Prerequisites

- [ ] Production access credentials
- [ ] kubectl configured for production cluster
- [ ] Docker access
- [ ] Git repository access
- [ ] Backup verification completed
- [ ] Change management approval (P0/P1)
- [ ] Stakeholder notification completed

---

## Blue-Green Deployment Rollback

### Architecture Overview

Blue-green deployment maintains two identical production environments:
- **Blue**: Currently active environment serving traffic
- **Green**: New version deployed but not receiving traffic

### Rollback Procedure

#### Step 1: Verify Current State

```bash
# Check current active deployment
curl http://localhost:8000/health | jq '.version'

# Check traffic routing
kubectl get service api-server -n production -o yaml | grep selector

# Verify both environments running
kubectl get deployments -n production | grep api-server
```

Expected output:
```
api-server-blue    3/3     3            3           2h
api-server-green   3/3     3            3           15m
```

#### Step 2: Identify Previous Version

```bash
# List recent deployments
kubectl rollout history deployment/api-server-blue -n production
kubectl rollout history deployment/api-server-green -n production

# Check git tags for version info
git tag --sort=-creatordate | head -5

# Verify previous version in registry
docker images | grep api-server | head -5
```

#### Step 3: Execute Blue-Green Swap

**Option A: Using Automated Script**

```bash
# Rollback to blue (if green is active)
./scripts/blue-green-swap.sh --rollback

# Verify swap
curl http://localhost:8000/health | jq '.version'
```

**Option B: Manual Kubernetes Service Update**

```bash
# Get current service selector
kubectl get service api-server -n production -o yaml > /tmp/api-service-backup.yaml

# Update service to point to blue environment
kubectl patch service api-server -n production -p '{"spec":{"selector":{"version":"blue"}}}'

# Verify traffic switch
kubectl get service api-server -n production -o yaml | grep version
```

#### Step 4: Monitor Traffic Switch

```bash
# Watch pod logs for incoming requests
kubectl logs -f -l app=api-server,version=blue -n production

# Check metrics in Grafana
# http://localhost:3000/d/platform-overview

# Monitor error rate
watch -n 5 'curl -s http://localhost:9090/api/v1/query?query=rate(http_requests_total{status=~\"5..\"}[5m]) | jq'
```

#### Step 5: Verify Rollback Success

```bash
# Run smoke tests
./smoke_tests.sh

# Check health endpoint
curl http://localhost:8000/health

# Verify all pods healthy
kubectl get pods -l app=api-server,version=blue -n production

# Check application logs for errors
kubectl logs -l app=api-server,version=blue --tail=50 -n production
```

#### Step 6: Decommission Failed Environment

```bash
# Scale down green environment
kubectl scale deployment api-server-green --replicas=0 -n production

# Delete green deployment (optional)
kubectl delete deployment api-server-green -n production

# Or keep for forensics/debugging
# Can delete after post-mortem
```

#### Step 7: Update Documentation

```bash
# Document rollback in incident log
incident_id="INC-$(date +%Y%m%d-%H%M%S)"
echo "Rollback executed: Blue-green swap" >> /tmp/$incident_id.log
echo "Rolled back from: green (v1.5.0)" >> /tmp/$incident_id.log
echo "Rolled back to: blue (v1.4.0)" >> /tmp/$incident_id.log
echo "Timestamp: $(date)" >> /tmp/$incident_id.log
```

---

## Configuration Rollback

### Application Configuration Rollback

#### Step 1: Identify Configuration Version

```bash
# Check ConfigMap version
kubectl get configmap api-server-config -n production -o yaml

# View configuration history
kubectl rollout history deployment/api-server -n production

# Check git history for config changes
git log --oneline -- configs/
```

#### Step 2: Rollback ConfigMap

**Option A: From Git History**

```bash
# Find previous working commit
git log --oneline -- configs/api-config.yaml | head -5

# Checkout previous version
git show <commit-hash>:configs/api-config.yaml > /tmp/api-config-previous.yaml

# Apply previous config
kubectl apply -f /tmp/api-config-previous.yaml -n production
```

**Option B: From Kubernetes History**

```bash
# List ConfigMap revisions
kubectl get configmap api-server-config -n production \
  -o jsonpath='{.metadata.annotations.kubectl\.kubernetes\.io/last-applied-configuration}' \
  | jq '.'

# Restore from backup
kubectl apply -f backups/configmaps/api-server-config-20250130.yaml -n production
```

#### Step 3: Restart Affected Pods

```bash
# Trigger rolling restart to pick up config
kubectl rollout restart deployment/api-server -n production

# Monitor restart
kubectl rollout status deployment/api-server -n production

# Verify new pods using old config
kubectl logs -l app=api-server --tail=20 -n production | grep "Config loaded"
```

#### Step 4: Verify Configuration Applied

```bash
# Check config values via API (if exposed)
curl http://localhost:8000/admin/config | jq

# Or check pod environment
kubectl exec -it deployment/api-server -n production -- env | grep CONFIG

# Verify application behavior
./smoke_tests.sh
```

### Feature Flag Rollback

```bash
# Disable problematic feature flag
curl -X POST http://localhost:8000/admin/features/disable \
  -H "Content-Type: application/json" \
  -d '{"feature": "new_inference_pipeline"}'

# Verify feature disabled
curl http://localhost:8000/admin/features | jq '.features.new_inference_pipeline'

# Monitor metrics for improvement
# Check Grafana dashboard
```

### Environment Variable Rollback

```bash
# Update deployment with previous env vars
kubectl set env deployment/api-server \
  MAX_CONNECTIONS=50 \
  POOL_SIZE=20 \
  -n production

# Verify update
kubectl get deployment api-server -n production -o yaml | grep -A 10 env:

# Rolling restart happens automatically
kubectl rollout status deployment/api-server -n production
```

---

## Database Rollback

### PostgreSQL Rollback

#### Schema Rollback

**Step 1: Identify Migration to Rollback**

```bash
# Check current migration version
docker exec postgres psql -U ai_user -d ai_platform \
  -c "SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 5;"

# List available rollback scripts
ls -lt migrations/rollback/
```

**Step 2: Backup Current Database State**

```bash
# Create pre-rollback backup
docker exec postgres pg_dump -U ai_user -Fc ai_platform > /tmp/pre_rollback_$(date +%Y%m%d_%H%M%S).dump

# Verify backup created
ls -lh /tmp/pre_rollback_*.dump
```

**Step 3: Execute Rollback Migration**

```bash
# Run rollback script
docker exec postgres psql -U ai_user -d ai_platform -f /migrations/rollback/20250130_rollback.sql

# Or using migration tool (e.g., Alembic, Flyway)
alembic downgrade -1

# Verify schema rolled back
docker exec postgres psql -U ai_user -d ai_platform \
  -c "\d+ users" # Check table structure
```

**Step 4: Validate Database State**

```bash
# Check data integrity
python validate_data_integrity.py

# Run database tests
pytest tests/integration/test_database.py -v

# Verify application connectivity
curl http://localhost:8000/health | jq '.database'
```

#### Data Rollback (Point-in-Time Recovery)

```bash
# Stop application to prevent new writes
kubectl scale deployment/api-server --replicas=0 -n production

# Restore from backup (see DISASTER_RECOVERY_RUNBOOK.md)
python restore_backup.py --type postgres --backup-id postgres_20250130_020000

# Validate restore
python restore_backup.py --validate-only --type postgres

# Restart application
kubectl scale deployment/api-server --replicas=3 -n production
```

### Qdrant Rollback

```bash
# Stop services using Qdrant
kubectl scale deployment api-server gateway --replicas=0 -n production

# Restore from snapshot (see DISASTER_RECOVERY_RUNBOOK.md)
python restore_backup.py --type qdrant --backup-id qdrant_20250130_020000

# Verify collections
curl http://localhost:6333/collections | jq

# Restart services
kubectl scale deployment api-server gateway --replicas=3 -n production
```

### Neo4j Rollback

```bash
# Stop services using Neo4j
kubectl scale deployment graph-service --replicas=0 -n production

# Restore from dump (see DISASTER_RECOVERY_RUNBOOK.md)
python restore_backup.py --type neo4j --backup-id neo4j_20250130_020000

# Verify graph database
docker exec neo4j cypher-shell -u neo4j -p neo4j_password \
  "MATCH (n) RETURN count(n) as node_count"

# Restart services
kubectl scale deployment graph-service --replicas=3 -n production
```

---

## Kubernetes Rollback

### Deployment Rollback

#### Quick Rollback to Previous Version

```bash
# Rollback to previous revision
kubectl rollout undo deployment/api-server -n production

# Monitor rollback progress
kubectl rollout status deployment/api-server -n production

# Verify pods running previous version
kubectl get pods -l app=api-server -n production -o wide
```

#### Rollback to Specific Revision

```bash
# List deployment history
kubectl rollout history deployment/api-server -n production

# View specific revision details
kubectl rollout history deployment/api-server -n production --revision=5

# Rollback to specific revision
kubectl rollout undo deployment/api-server -n production --to-revision=5

# Monitor rollback
kubectl rollout status deployment/api-server -n production
```

#### Rollback All Related Deployments

```bash
#!/bin/bash
# rollback_all.sh

NAMESPACE="production"
DEPLOYMENTS=("api-server" "gateway" "learning-engine" "drift-monitor")

for deploy in "${DEPLOYMENTS[@]}"; do
  echo "Rolling back $deploy..."
  kubectl rollout undo deployment/$deploy -n $NAMESPACE
  kubectl rollout status deployment/$deploy -n $NAMESPACE
done

echo "All deployments rolled back"
```

### StatefulSet Rollback

```bash
# Rollback StatefulSet (e.g., database)
kubectl rollout undo statefulset/postgres -n production

# Monitor rollback (happens one pod at a time)
kubectl rollout status statefulset/postgres -n production

# Verify pods
kubectl get pods -l app=postgres -n production
```

### DaemonSet Rollback

```bash
# Rollback DaemonSet (e.g., monitoring agent)
kubectl rollout undo daemonset/monitoring-agent -n production

# Monitor rollback
kubectl rollout status daemonset/monitoring-agent -n production
```

---

## Docker Compose Rollback

### Single Service Rollback

```bash
# Pull previous version from registry
docker pull registry.example.com/api-server:v1.4.0

# Update docker-compose.yaml to use previous version
sed -i 's/api-server:v1.5.0/api-server:v1.4.0/g' docker-compose.yaml

# Recreate service with previous version
docker compose up -d api-server

# Verify new container running
docker compose ps api-server

# Check logs for startup
docker compose logs -f api-server
```

### Full Stack Rollback

```bash
# Checkout previous version from git
git log --oneline | head -5
git checkout <previous-commit-hash>

# Pull all previous images
docker compose pull

# Recreate all services
docker compose up -d

# Verify all services running
docker compose ps

# Run smoke tests
./smoke_tests.sh
```

### Using Git Tags

```bash
# List available versions
git tag --sort=-creatordate | head -10

# Checkout specific version
git checkout v1.4.0

# Rebuild and restart
docker compose build
docker compose up -d

# Verify version
curl http://localhost:8000/health | jq '.version'
```

---

## LoRA Model Rollback

### Rollback LoRA Adapter

See also: `lora_kill_switch_rollback.md` for detailed procedures.

```bash
# Disable problematic LoRA adapter
curl -X POST http://localhost:8000/admin/lora/disable \
  -H "Content-Type: application/json" \
  -d '{"adapter_id": "customer-support-v2"}'

# Switch to previous adapter version
curl -X POST http://localhost:8000/admin/lora/activate \
  -H "Content-Type: application/json" \
  -d '{"adapter_id": "customer-support-v1"}'

# Verify active adapter
curl http://localhost:8000/admin/lora/active | jq

# Monitor inference quality
# Check Grafana Learning Engine dashboard
```

### Emergency LoRA Kill Switch

```bash
# Disable all LoRA adapters (fallback to base model)
curl -X POST http://localhost:8000/admin/lora/kill-switch \
  -H "Content-Type: application/json" \
  -d '{"reason": "quality_degradation"}'

# Verify base model active
curl http://localhost:8000/health | jq '.lora_enabled'
# Should return: "lora_enabled": false

# Monitor system stability
./smoke_tests.sh
```

---

## Verification and Validation

### Post-Rollback Checklist

- [ ] All pods/containers running and healthy
- [ ] Health checks passing
- [ ] Error rate returned to baseline (<1%)
- [ ] Latency within SLA (P99 < 1s)
- [ ] No alerts firing in Alertmanager
- [ ] Smoke tests passing
- [ ] Monitoring dashboards show normal metrics
- [ ] Database connectivity verified
- [ ] No data loss or corruption
- [ ] User-facing functionality working
- [ ] Status page updated

### Automated Validation

```bash
#!/bin/bash
# validate_rollback.sh

echo "Running post-rollback validation..."

# Health check
if ! curl -f http://localhost:8000/health; then
  echo "❌ Health check failed"
  exit 1
fi
echo "✅ Health check passed"

# Error rate check
error_rate=$(curl -s 'http://localhost:9090/api/v1/query?query=rate(http_requests_total{status=~"5.."}[5m])' | jq -r '.data.result[0].value[1]')
if (( $(echo "$error_rate > 0.01" | bc -l) )); then
  echo "❌ Error rate too high: $error_rate"
  exit 1
fi
echo "✅ Error rate normal: $error_rate"

# Latency check
latency=$(curl -s 'http://localhost:9090/api/v1/query?query=histogram_quantile(0.99,rate(http_request_duration_seconds_bucket[5m]))' | jq -r '.data.result[0].value[1]')
if (( $(echo "$latency > 1.0" | bc -l) )); then
  echo "❌ Latency too high: $latency"
  exit 1
fi
echo "✅ Latency acceptable: $latency"

# Run smoke tests
if ! ./smoke_tests.sh; then
  echo "❌ Smoke tests failed"
  exit 1
fi
echo "✅ Smoke tests passed"

echo "✅ All validation checks passed"
```

---

## Troubleshooting

### Rollback Stuck or Failed

**Issue**: Kubernetes rollback not progressing

```bash
# Check rollout status
kubectl describe deployment api-server -n production

# Check pod events
kubectl get events -n production --sort-by='.lastTimestamp' | tail -20

# Check pod status
kubectl get pods -l app=api-server -n production

# If pods stuck in ImagePullBackOff
kubectl describe pod <pod-name> -n production

# Force delete stuck pods
kubectl delete pod <pod-name> --force --grace-period=0 -n production
```

### Previous Version Not Available

**Issue**: Docker image for previous version not found

```bash
# Check available images in registry
docker images | grep api-server

# Pull specific version
docker pull registry.example.com/api-server:v1.4.0

# If image deleted, rebuild from git tag
git checkout v1.4.0
docker build -t api-server:v1.4.0 -f Dockerfile.api .
docker push registry.example.com/api-server:v1.4.0
```

### Database Rollback Fails

**Issue**: Database restore failing

```bash
# Check database logs
docker compose logs postgres

# Verify backup file integrity
sha256sum /tmp/postgres_backup.dump

# Try different backup
python restore_backup.py --list --type postgres
python restore_backup.py --type postgres --backup-id postgres_20250129_020000

# Manual restore if automated fails
docker exec -i postgres pg_restore -U ai_user -d ai_platform -c < /tmp/postgres_backup.dump
```

### Service Won't Start After Rollback

**Issue**: Service crashes on startup with old version

```bash
# Check logs for errors
docker compose logs api-server
kubectl logs -l app=api-server --tail=100 -n production

# Check for config incompatibility
# May need to rollback config too
kubectl rollout history deployment/api-server -n production

# Check for database schema mismatch
# May need to rollback database schema
docker exec postgres psql -U ai_user -d ai_platform -c "SELECT version FROM schema_migrations;"

# If all else fails, rollback multiple components together
./scripts/rollback_all.sh --to-version v1.4.0
```

### Performance Still Degraded After Rollback

**Issue**: Rollback completed but performance not improved

```bash
# Check if issue is external dependency
curl -w "@curl-format.txt" -o /dev/null -s http://external-api.example.com/health

# Check database performance
docker exec postgres psql -U ai_user -d ai_platform -c "SELECT * FROM pg_stat_activity;"

# Check resource utilization
kubectl top pods -n production
kubectl top nodes

# May need to scale up or restart dependencies
kubectl scale deployment api-server --replicas=5 -n production
docker compose restart postgres redis
```

---

## Rollback Checklist

### Pre-Rollback

- [ ] Incident declared and documented
- [ ] Rollback decision approved (P0/P1 requires manager approval)
- [ ] Stakeholders notified
- [ ] Backup of current state created
- [ ] Previous version verified available
- [ ] Rollback plan documented
- [ ] Rollback window scheduled (if non-emergency)

### During Rollback

- [ ] Rollback command executed
- [ ] Progress monitored
- [ ] Logs captured for post-mortem
- [ ] Metrics watched for improvement
- [ ] Stakeholders updated on progress

### Post-Rollback

- [ ] Validation checklist completed
- [ ] Smoke tests passed
- [ ] Metrics returned to baseline
- [ ] Alerts cleared
- [ ] Status page updated
- [ ] Incident log completed
- [ ] Post-mortem scheduled
- [ ] Runbooks updated with lessons learned

---

## Appendix: Rollback Scripts

### Blue-Green Swap Script

```bash
#!/bin/bash
# scripts/blue-green-swap.sh

set -e

NAMESPACE="production"
SERVICE="api-server"

# Get current active environment
current=$(kubectl get service $SERVICE -n $NAMESPACE -o jsonpath='{.spec.selector.version}')
echo "Current active: $current"

# Determine target environment
if [ "$current" == "blue" ]; then
  target="green"
else
  target="blue"
fi

echo "Swapping to: $target"

# Update service selector
kubectl patch service $SERVICE -n $NAMESPACE -p "{\"spec\":{\"selector\":{\"version\":\"$target\"}}}"

echo "Traffic switched to $target"
echo "Verify with: curl http://localhost:8000/health | jq '.version'"
```

---

**Version**: 1.0  
**Last Updated**: 2025-01-30  
**Next Review**: 2025-02-28  
**Owner**: SRE Team
