# Multi-Region Operations Guide

Operational procedures for managing multi-region AI Platform deployments.

## 🎯 Daily Operations

### Health Check Routine

```bash
#!/bin/bash
# Daily health check script

REGIONS=("us-west-1" "us-east-1" "eu-west-1" "ap-southeast-1")

echo "=== Daily Health Check ==="
date

for region in "${REGIONS[@]}"; do
  echo ""
  echo "--- Region: $region ---"
  
  # Switch context
  kubectl config use-context "ai-platform-$region"
  
  # Check pod status
  echo "Pods:"
  kubectl get pods -n ai-platform --no-headers | \
    awk '{print $3}' | sort | uniq -c
  
  # Check service endpoints
  echo "Services:"
  kubectl get svc -n ai-platform -o wide | \
    grep -E "gateway|agent-router|qdrant|postgres"
  
  # Check replication lag
  echo "Replication Lag:"
  kubectl exec -n ai-platform postgres-0 -- psql -U ai_user -d ai_platform \
    -t -c "SELECT subscription_name, lag_seconds FROM replication_status;" 2>/dev/null || echo "N/A"
done
```

### Monitoring Checklist

Daily monitoring checklist:

- [ ] All regions healthy (Grafana dashboard)
- [ ] Replication lag < 30s (PostgreSQL)
- [ ] Replication lag < 60s (Qdrant)
- [ ] Cross-region latency < 250ms (P95)
- [ ] No active alerts (Prometheus)
- [ ] Disk usage < 80%
- [ ] Memory usage < 85%
- [ ] CPU usage < 75%

## 🔄 Replication Management

### Check Replication Status

```bash
# PostgreSQL replication status
kubectl exec -n ai-platform postgres-0 -- psql -U ai_user -d ai_platform -c \
  "SELECT * FROM replication_status;"

# Detailed replication health
kubectl exec -n ai-platform postgres-0 -- psql -U ai_user -d ai_platform -c \
  "SELECT * FROM check_replication_health();"

# Check for alerts
kubectl exec -n ai-platform postgres-0 -- psql -U ai_user -d ai_platform -c \
  "SELECT * FROM check_replication_alerts();"

# Qdrant cluster status
kubectl exec -n ai-platform qdrant-0 -- curl -s http://localhost:6333/cluster | jq .
```

### Resolve Replication Lag

#### PostgreSQL Lag

```bash
# 1. Check replication slots
kubectl exec -n ai-platform postgres-0 -- psql -U ai_user -d ai_platform -c \
  "SELECT * FROM pg_replication_slots;"

# 2. Check WAL sender processes
kubectl exec -n ai-platform postgres-0 -- psql -U ai_user -d ai_platform -c \
  "SELECT * FROM pg_stat_replication;"

# 3. Check disk I/O
kubectl exec -n ai-platform postgres-0 -- iostat -x 1 5

# 4. If lag is too high, consider resync
# WARNING: This will re-sync all data
kubectl exec -n ai-platform postgres-0 -- psql -U ai_user -d ai_platform -c \
  "SELECT pglogical.alter_subscription_resynchronize_table('sub_from_us_west_1', 'public', 'table_name');"
```

#### Qdrant Lag

```bash
# 1. Check cluster peers
kubectl exec -n ai-platform qdrant-0 -- curl http://localhost:6333/cluster/peers

# 2. Check collection status
kubectl exec -n ai-platform qdrant-0 -- curl http://localhost:6333/collections/documents

# 3. Trigger snapshot if needed
kubectl exec -n ai-platform qdrant-0 -- curl -X POST \
  http://localhost:6333/collections/documents/snapshots

# 4. Check network connectivity
kubectl run -n ai-platform test-net --image=busybox --rm -it -- \
  nc -zv qdrant.us-west-1.ai-platform.svc.cluster.local 6334
```

### Pause/Resume Replication

```bash
# Pause PostgreSQL replication (for maintenance)
kubectl exec -n ai-platform postgres-0 -- psql -U ai_user -d ai_platform -c \
  "SELECT pglogical.alter_subscription_disable('sub_from_us_west_1');"

# Resume PostgreSQL replication
kubectl exec -n ai-platform postgres-0 -- psql -U ai_user -d ai_platform -c \
  "SELECT pglogical.alter_subscription_enable('sub_from_us_west_1');"

# Verify subscription status
kubectl exec -n ai-platform postgres-0 -- psql -U ai_user -d ai_platform -c \
  "SELECT * FROM pglogical.subscription;"
```

## 🚨 Incident Response

### Region Down

**Symptoms**: 
- Region health status = 0
- Services unreachable
- High error rates

**Response**:

```bash
# 1. Verify region is actually down
kubectl config use-context "ai-platform-$AFFECTED_REGION"
kubectl get nodes
kubectl get pods -n ai-platform

# 2. Check if it's a partial outage
kubectl get pods -n ai-platform --field-selector=status.phase!=Running

# 3. Verify failover occurred
# Check DNS routing
dig +short ai-platform.example.com
# Should not include affected region IP

# 4. Check if traffic is being served
for region in us-west-1 us-east-1 eu-west-1 ap-southeast-1; do
  if [ "$region" != "$AFFECTED_REGION" ]; then
    curl -s https://$region.ai-platform.example.com/health | jq .
  fi
done

# 5. Monitor remaining regions for capacity
kubectl top nodes
kubectl top pods -n ai-platform

# 6. Scale up if needed
kubectl scale deployment -n ai-platform gateway --replicas=5
kubectl scale deployment -n ai-platform agent-router --replicas=5
```

**Recovery**:

```bash
# 1. Investigate root cause
kubectl describe nodes
kubectl get events -n ai-platform --sort-by='.lastTimestamp'

# 2. Fix underlying issue
# (Node failure, network issue, resource exhaustion, etc.)

# 3. Verify pods are running
kubectl get pods -n ai-platform

# 4. Check replication catch-up
kubectl exec -n ai-platform postgres-0 -- psql -U ai_user -d ai_platform -c \
  "SELECT * FROM replication_status;"

# 5. Re-enable DNS routing once healthy
# Update health check or wait for automatic recovery

# 6. Monitor for 30 minutes to ensure stability
```

### High Replication Lag

**Symptoms**:
- Replication lag > 60 seconds
- Data inconsistency alerts
- Stale data in replica regions

**Response**:

```bash
# 1. Identify the bottleneck
# Check network latency
kubectl run -n ai-platform test-net --image=busybox --rm -it -- \
  ping postgres.us-west-1.ai-platform.svc.cluster.local

# Check disk I/O
kubectl exec -n ai-platform postgres-0 -- iostat -x 1 5

# Check CPU/Memory
kubectl top pod postgres-0 -n ai-platform

# 2. Check for locks
kubectl exec -n ai-platform postgres-0 -- psql -U ai_user -d ai_platform -c \
  "SELECT * FROM pg_locks WHERE NOT granted;"

# 3. Check for long-running queries
kubectl exec -n ai-platform postgres-0 -- psql -U ai_user -d ai_platform -c \
  "SELECT pid, now() - query_start AS duration, query FROM pg_stat_activity WHERE state = 'active' AND now() - query_start > interval '1 minute';"

# 4. Terminate problematic queries if safe
kubectl exec -n ai-platform postgres-0 -- psql -U ai_user -d ai_platform -c \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE pid = <pid>;"

# 5. Increase resources if needed
kubectl patch statefulset postgres -n ai-platform -p \
  '{"spec":{"template":{"spec":{"containers":[{"name":"postgres","resources":{"requests":{"memory":"8Gi","cpu":"4"},"limits":{"memory":"16Gi","cpu":"8"}}}]}}}}'
```

### Failover Storm

**Symptoms**:
- Rapid failover events (> 1/minute)
- Flapping between regions
- Inconsistent routing

**Response**:

```bash
# 1. Check failover rate
# In Grafana or Prometheus:
# rate(geo_routing_failovers_total[5m])

# 2. Increase circuit breaker timeout
# Edit configs/geo-routing.yaml
kubectl edit configmap geo-routing-config -n ai-platform

# 3. Check health check sensitivity
# May need to increase thresholds or intervals

# 4. Stabilize the unstable region
kubectl config use-context "ai-platform-$UNSTABLE_REGION"
kubectl get pods -n ai-platform -o wide
kubectl describe pods -n ai-platform

# 5. Temporarily remove unstable region from rotation
# Update DNS to exclude region

# 6. Fix underlying issue before re-adding
```

## 🔧 Maintenance Operations

### Rolling Update

```bash
# Update to new version in one region at a time

REGIONS=("us-west-1" "us-east-1" "eu-west-1" "ap-southeast-1")
NEW_VERSION="v2.1.0"

for region in "${REGIONS[@]}"; do
  echo "Updating $region to $NEW_VERSION"
  
  kubectl config use-context "ai-platform-$region"
  
  # Update helm release
  helm upgrade ai-platform helm/ai-platform \
    --namespace ai-platform \
    --values helm/ai-platform/values-multi-region.yaml \
    --set global.region=$region \
    --set agentRouter.image.tag=$NEW_VERSION \
    --set gateway.image.tag=$NEW_VERSION \
    --wait \
    --timeout 15m
  
  # Verify health
  kubectl rollout status deployment/gateway -n ai-platform
  kubectl rollout status deployment/agent-router -n ai-platform
  
  # Wait before next region
  echo "Waiting 5 minutes before next region..."
  sleep 300
done
```

### Backup and Restore

#### PostgreSQL Backup

```bash
# Create backup
kubectl exec -n ai-platform postgres-0 -- pg_dump -U ai_user ai_platform | \
  gzip > backup-$(date +%Y%m%d-%H%M%S).sql.gz

# Restore from backup
gunzip -c backup-20250302-120000.sql.gz | \
  kubectl exec -i -n ai-platform postgres-0 -- psql -U ai_user ai_platform
```

#### Qdrant Snapshot

```bash
# Create snapshot
kubectl exec -n ai-platform qdrant-0 -- curl -X POST \
  http://localhost:6333/collections/documents/snapshots

# List snapshots
kubectl exec -n ai-platform qdrant-0 -- curl \
  http://localhost:6333/collections/documents/snapshots

# Restore from snapshot
kubectl exec -n ai-platform qdrant-0 -- curl -X POST \
  http://localhost:6333/collections/documents/snapshots/restore \
  -H 'Content-Type: application/json' \
  -d '{"location":"s3://bucket/snapshot-name"}'
```

### Scale Operations

#### Scale Up for Traffic Spike

```bash
# Scale horizontally
kubectl scale deployment -n ai-platform gateway --replicas=10
kubectl scale deployment -n ai-platform agent-router --replicas=10
kubectl scale statefulset -n ai-platform qdrant --replicas=5

# Scale vertically (requires restart)
kubectl patch deployment gateway -n ai-platform -p \
  '{"spec":{"template":{"spec":{"containers":[{"name":"gateway","resources":{"requests":{"memory":"2Gi","cpu":"2"},"limits":{"memory":"4Gi","cpu":"4"}}}]}}}}'
```

#### Scale Down After Spike

```bash
# Gradually scale down
kubectl scale deployment -n ai-platform gateway --replicas=3
kubectl scale deployment -n ai-platform agent-router --replicas=3
kubectl scale statefulset -n ai-platform qdrant --replicas=3

# Wait and monitor
sleep 300
kubectl top pods -n ai-platform
```

### Add New Region

```bash
# 1. Provision cluster in new region
# (Cloud provider specific)

# 2. Deploy using deploy_region.py
python3 scripts/deploy/deploy_region.py \
  --region us-central-1 \
  --cluster ai-platform-us-central-1 \
  --values-file helm/ai-platform/values-multi-region.yaml

# 3. Setup replication
kubectl exec -n ai-platform postgres-0 -- psql -U ai_user -d ai_platform -c \
  "SELECT setup_replication_subscription('sub_from_us_west_1', 'host=postgres.us-west-1.ai-platform.svc.cluster.local port=5432 dbname=ai_platform user=replication_user');"

# 4. Add to geo-routing config
# Edit configs/geo-routing.yaml
kubectl apply -f configs/geo-routing.yaml -n ai-platform

# 5. Update DNS
# Add health check and routing rule

# 6. Monitor initial sync
watch kubectl exec -n ai-platform postgres-0 -- psql -U ai_user -d ai_platform \
  -t -c "SELECT lag_seconds FROM replication_status WHERE subscription_name='sub_from_us_west_1';"
```

## 📊 Performance Tuning

### Optimize Cross-Region Latency

```bash
# 1. Enable VPC peering (if not already enabled)
# Cloud provider specific

# 2. Increase cache TTL
kubectl edit configmap redis-config -n ai-platform
# Set TTL to 3600 (1 hour)

# 3. Enable regional read replicas
# Update values to direct reads to local region

# 4. Optimize Qdrant HNSW parameters
kubectl exec -n ai-platform qdrant-0 -- curl -X PATCH \
  http://localhost:6333/collections/documents \
  -H 'Content-Type: application/json' \
  -d '{"hnsw_config":{"ef_construct":200,"m":32}}'
```

### Optimize Replication Performance

```bash
# PostgreSQL - Increase max_wal_senders
kubectl exec -n ai-platform postgres-0 -- psql -U ai_user -d ai_platform -c \
  "ALTER SYSTEM SET max_wal_senders = 20;"

# PostgreSQL - Increase wal_keep_size
kubectl exec -n ai-platform postgres-0 -- psql -U ai_user -d ai_platform -c \
  "ALTER SYSTEM SET wal_keep_size = '10GB';"

# Reload configuration
kubectl exec -n ai-platform postgres-0 -- psql -U ai_user -d ai_platform -c \
  "SELECT pg_reload_conf();"

# Verify changes
kubectl exec -n ai-platform postgres-0 -- psql -U ai_user -d ai_platform -c \
  "SHOW max_wal_senders; SHOW wal_keep_size;"
```

## 🔍 Troubleshooting Playbook

### Symptom: Requests Failing

```bash
# 1. Check region health
for region in us-west-1 us-east-1 eu-west-1 ap-southeast-1; do
  echo "$region: $(curl -s -o /dev/null -w '%{http_code}' https://$region.ai-platform.example.com/health)"
done

# 2. Check pod status
kubectl get pods -n ai-platform --all-namespaces

# 3. Check logs
kubectl logs -n ai-platform -l app.kubernetes.io/name=gateway --tail=100

# 4. Check Kong routing
kubectl logs -n ai-platform -l app=kong --tail=100 | grep ERROR
```

### Symptom: Slow Responses

```bash
# 1. Check latency metrics
# Grafana dashboard or Prometheus:
# histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))

# 2. Check resource usage
kubectl top pods -n ai-platform
kubectl top nodes

# 3. Check for high replication lag
kubectl exec -n ai-platform postgres-0 -- psql -U ai_user -d ai_platform -c \
  "SELECT * FROM replication_status WHERE lag_seconds > 30;"

# 4. Check for network issues
kubectl run -n ai-platform test-net --image=nicolaka/netshoot --rm -it -- \
  bash -c "for i in {1..10}; do ping -c 1 gateway.ai-platform.svc.cluster.local; done"
```

### Symptom: Data Inconsistency

```bash
# 1. Check vector counts in all regions
for region in us-west-1 us-east-1 eu-west-1 ap-southeast-1; do
  echo "$region:"
  kubectl --context=ai-platform-$region exec -n ai-platform qdrant-0 -- \
    curl -s http://localhost:6333/collections/documents | jq '.result.vectors_count'
done

# 2. Check PostgreSQL row counts
kubectl exec -n ai-platform postgres-0 -- psql -U ai_user -d ai_platform -c \
  "SELECT schemaname, tablename, n_live_tup FROM pg_stat_user_tables ORDER BY n_live_tup DESC;"

# 3. Force replication sync
kubectl exec -n ai-platform postgres-0 -- psql -U ai_user -d ai_platform -c \
  "SELECT pglogical.alter_subscription_synchronize('sub_from_us_west_1');"
```

## 📋 Runbooks

### Runbook: Complete Region Failure

1. **Detect**: Alert fires or monitoring shows region down
2. **Verify**: Confirm region is actually unreachable
3. **Assess**: Check impact (traffic rerouted? data loss?)
4. **Communicate**: Notify stakeholders
5. **Stabilize**: Ensure other regions handling load
6. **Investigate**: Determine root cause
7. **Repair**: Fix underlying issue
8. **Restore**: Bring region back online
9. **Verify**: Test all functionality
10. **Monitor**: Watch for 24 hours
11. **Document**: Record incident details
12. **Improve**: Implement preventive measures

### Runbook: Replication Failure

1. **Detect**: Replication lag > 60s or stopped
2. **Verify**: Check replication status
3. **Identify**: Determine bottleneck (network, disk, CPU)
4. **Isolate**: Pause non-critical writes if needed
5. **Resolve**: Address bottleneck
6. **Resume**: Allow replication to catch up
7. **Verify**: Confirm lag returns to normal
8. **Document**: Record cause and resolution

## 🎓 Best Practices

1. **Never scale to zero** in production regions
2. **Always test in staging** before production
3. **Monitor replication lag** continuously
4. **Keep DNS TTL low** (60s) for fast failover
5. **Document all changes** in change log
6. **Perform regular DR drills** (monthly)
7. **Maintain runbooks** up to date
8. **Review alerts weekly** and tune thresholds

## 📞 Escalation

### Level 1: On-Call Engineer
- Region health issues
- Replication lag < 60s
- Performance degradation

### Level 2: Senior SRE
- Multiple region failure
- Replication lag > 300s
- Data inconsistency

### Level 3: Engineering Lead
- Total platform outage
- Data loss event
- Security incident

---

**Last Updated**: 2025-03-02  
**Version**: 1.0  
**Maintainer**: SRE Team
