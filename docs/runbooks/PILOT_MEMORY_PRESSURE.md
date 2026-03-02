# Pilot: Memory Pressure Detected Runbook

## Alert: MemoryPressureDetected

**Severity**: Critical  
**Component**: Infrastructure  
**Pilot Critical**: Yes

---

## Overview

This alert fires when a container's memory usage exceeds 90% of its configured limit (`container_memory_working_set_bytes / container_spec_memory_limit_bytes > 0.9`). High memory pressure can lead to:
- Out of Memory (OOM) kills
- Performance degradation (swapping, GC thrashing)
- Application instability
- Service unavailability

---

## Quick Diagnosis (2 minutes)

### Step 1: Identify Affected Container

```bash
# Check current memory usage
docker stats --no-stream

# or for Kubernetes
kubectl top pods -n production

# Query Prometheus for high memory containers
curl http://prometheus:9090/api/v1/query --data-urlencode 'query=container_memory_working_set_bytes{name!=""} / container_spec_memory_limit_bytes{name!=""} > 0.9'
```

### Step 2: Check Container Status

```bash
# Check if container is still running
docker compose ps <container_name>
# or
kubectl get pod <pod_name> -n production

# Check for recent OOM kills
docker inspect <container_id> | jq '.[0].State.OOMKilled'
# or
kubectl describe pod <pod_name> -n production | grep -i oom
```

### Step 3: Check Memory Limit

```bash
# Check configured memory limit
docker inspect <container_id> | jq '.[0].HostConfig.Memory'
# or
kubectl describe pod <pod_name> -n production | grep -A5 "Limits:"

# Check current memory usage
docker stats --no-stream <container_name>
```

---

## Investigation Steps

### Phase 1: Memory Analysis

#### 1.1 Check Memory Usage Trend

```bash
# Check memory usage over time in Prometheus
curl http://prometheus:9090/api/v1/query --data-urlencode 'query=container_memory_working_set_bytes{name="<container_name>"}[1h]'

# Visualize in Grafana
open http://localhost:3000/d/container-metrics

# Is memory usage:
# - Steady state high? (undersized limit)
# - Growing over time? (memory leak)
# - Spiking? (traffic spike or specific operation)
```

#### 1.2 Check Application Logs

```bash
# Look for memory-related errors
docker compose logs <container_name> | grep -i "memory\|oom\|heap\|gc"

# Check for recent heavy operations
docker compose logs <container_name> --tail=200 | grep -i "processing\|batch\|import"

# Look for error patterns
docker compose logs <container_name> | grep -i "error\|exception" | tail -50
```

#### 1.3 Check Process Memory Usage

```bash
# Enter container and check processes
docker exec <container_name> top -bn1

# or detailed memory breakdown
docker exec <container_name> ps aux --sort=-%mem | head -10

# Kubernetes
kubectl exec <pod_name> -n production -- top -bn1
```

---

### Phase 2: Root Cause Analysis

#### 2.1 Insufficient Memory Limit

**Symptoms**: Consistent high usage, no leak pattern, OOM kills during normal operation

```bash
# Check historical usage patterns
curl http://prometheus:9090/api/v1/query_range \
  --data-urlencode 'query=container_memory_working_set_bytes{name="<container_name>"}' \
  --data-urlencode 'start=<timestamp_24h_ago>' \
  --data-urlencode 'end=<timestamp_now>' \
  --data-urlencode 'step=300'

# Calculate required memory: P95 + 20% buffer
# If consistently near limit, increase memory allocation
```

**Remediation**:

```bash
# Increase memory limit (Docker Compose)
# Edit docker-compose.yml
services:
  api-server:
    deploy:
      resources:
        limits:
          memory: 4G  # Increase from 2G
        reservations:
          memory: 2G

docker compose up -d api-server

# Kubernetes
kubectl set resources deployment/<deployment_name> \
  --limits=memory=4Gi \
  --requests=memory=2Gi \
  -n production

# Monitor the change
watch kubectl top pod -l app=<app_name> -n production
```

#### 2.2 Memory Leak

**Symptoms**: Memory usage grows steadily over time, never releases

```bash
# Check memory growth rate
# Compare current usage to 1 hour ago, 24 hours ago
curl http://prometheus:9090/api/v1/query --data-urlencode 'query=container_memory_working_set_bytes{name="<container_name>"} - container_memory_working_set_bytes{name="<container_name>"} offset 1h'

# Check for known memory leak patterns in logs
docker compose logs <container_name> | grep -i "leak\|retained\|unreleased"
```

**Remediation** (Immediate):

```bash
# Restart container to free memory
docker compose restart <container_name>
# or
kubectl rollout restart deployment/<deployment_name> -n production

# Implement automatic restart schedule (temporary fix)
kubectl patch deployment/<deployment_name> -n production --type='json' -p='[
  {
    "op": "add",
    "path": "/spec/template/spec/containers/0/env/-",
    "value": {"name": "RESTART_POLICY", "value": "on-memory-pressure"}
  }
]'
```

**Long-term Fix**:

```bash
# Enable memory profiling (if available)
curl -X POST http://localhost:<port>/admin/debug/enable-profiling

# Capture heap dump for analysis
curl -X POST http://localhost:<port>/admin/debug/heap-dump > heap_dump.hprof

# or for Python applications
docker exec <container_name> python -m memory_profiler <script.py>

# Rollback to previous version while investigating
kubectl rollout undo deployment/<deployment_name> -n production
```

#### 2.3 Traffic Spike / Load Increase

**Symptoms**: Memory spike correlates with request spike

```bash
# Check request rate
curl http://prometheus:9090/api/v1/query --data-urlencode 'query=rate(http_requests_total[5m])'

# Check concurrent connections
curl http://prometheus:9090/api/v1/query --data-urlencode 'query=http_requests_in_flight'

# Check for specific heavy endpoints
docker compose logs <container_name> | grep -E "POST|GET" | awk '{print $7}' | sort | uniq -c | sort -rn | head -10
```

**Remediation**:

```bash
# Scale horizontally to distribute load
kubectl scale deployment/<deployment_name> --replicas=5 -n production

# Enable rate limiting (if not already enabled)
curl -X POST http://localhost:8000/admin/rate-limit/enable

# Increase memory limit temporarily
kubectl set resources deployment/<deployment_name> --limits=memory=6Gi -n production

# Add autoscaling based on memory
kubectl autoscale deployment/<deployment_name> \
  --cpu-percent=70 \
  --memory-percent=80 \
  --min=3 \
  --max=10 \
  -n production
```

#### 2.4 Large Data Processing / Caching

**Symptoms**: Memory spike during specific operations (batch jobs, imports, cache loading)

```bash
# Check for large in-memory caches
curl http://localhost:<port>/metrics | grep cache_size

# Check for batch processing
docker compose logs <container_name> | grep -i "batch\|import\|export\|sync"

# Check Redis/cache memory usage (if separate)
docker exec redis redis-cli info memory
```

**Remediation**:

```bash
# Limit cache size (application configuration)
kubectl set env deployment/<deployment_name> \
  MAX_CACHE_SIZE=500MB \
  CACHE_EVICTION_POLICY=lru \
  -n production

# Move heavy processing to background jobs
# (architecture change - requires code modification)

# Increase memory for batch processing pods specifically
kubectl set resources deployment/<deployment_name>-batch \
  --limits=memory=8Gi \
  -n production

# Clear caches if overloaded
curl -X POST http://localhost:<port>/admin/cache/clear
```

#### 2.5 Inefficient Data Structures / Queries

**Symptoms**: Memory usage high for dataset size, specific queries cause spikes

```bash
# Check for slow/heavy queries
docker exec postgres psql -U ai_user -d ai_platform -c "
  SELECT query, calls, mean_exec_time, rows
  FROM pg_stat_statements
  ORDER BY mean_exec_time DESC
  LIMIT 10;
"

# Check for large result sets
docker compose logs <container_name> | grep -i "fetching\|loading\|query" | grep -oP '\d+\s+(rows|records)' | sort -rn | head -10

# Check vector search batch sizes
curl http://localhost:6333/metrics | grep batch_size
```

**Remediation**:

```bash
# Add pagination to large queries (code change required)
# Limit result set sizes
kubectl set env deployment/<deployment_name> \
  MAX_QUERY_RESULTS=1000 \
  BATCH_SIZE=100 \
  -n production

# Add database indexes for common queries
docker exec postgres psql -U ai_user -d ai_platform -c "
  CREATE INDEX CONCURRENTLY idx_large_table ON large_table(frequently_queried_column);
"

# Use streaming for large data transfers (code change)
```

---

## Remediation Summary

### Immediate Actions (5 minutes)

1. **Identify Affected Container**
   ```bash
   kubectl top pods -n production
   ```

2. **Check for OOM Risk**
   ```bash
   kubectl describe pod <pod_name> -n production | grep -i oom
   ```

3. **Scale Horizontally** (distribute load)
   ```bash
   kubectl scale deployment/<name> --replicas=5 -n production
   ```

4. **Increase Memory Limit** (if undersized)
   ```bash
   kubectl set resources deployment/<name> --limits=memory=4Gi -n production
   ```

5. **Restart Container** (if memory leak suspected)
   ```bash
   kubectl rollout restart deployment/<name> -n production
   ```

### Long-term Actions

- Enable memory profiling and heap dumps
- Implement autoscaling based on memory usage
- Optimize data structures and queries
- Implement streaming for large data transfers
- Add memory leak detection in CI/CD

---

## Prevention

### 1. Set Appropriate Resource Limits

```yaml
# Start with generous limits, tune based on metrics
resources:
  requests:
    memory: "1Gi"
    cpu: "500m"
  limits:
    memory: "4Gi"  # 4x request for burst capacity
    cpu: "2000m"
```

### 2. Implement Memory Monitoring

```yaml
# Prometheus alerts for memory trends
- alert: MemoryUsageHigh
  expr: |
    container_memory_working_set_bytes{name!=""} /
    container_spec_memory_limit_bytes{name!=""} > 0.8
  for: 10m
  labels:
    severity: warning

- alert: MemoryLeakSuspected
  expr: |
    (
      container_memory_working_set_bytes{name!=""} -
      container_memory_working_set_bytes{name!=""} offset 6h
    ) / container_memory_working_set_bytes{name!=""} offset 6h > 0.3
  for: 1h
  labels:
    severity: warning
```

### 3. Implement Autoscaling

```yaml
# Horizontal Pod Autoscaler based on memory
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: api-server-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: api-server
  minReplicas: 3
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 70
```

### 4. Configure Garbage Collection

```python
# Example: Python GC tuning
import gc

# Adjust GC thresholds
gc.set_threshold(700, 10, 10)  # More aggressive GC

# Force GC periodically in long-running processes
@periodic(interval=300)  # Every 5 minutes
def force_gc():
    gc.collect()
```

### 5. Implement Memory Limits in Code

```python
# Example: Limit cache size
from cachetools import TTLCache

# 500MB max, 1 hour TTL
cache = TTLCache(maxsize=500_000_000, ttl=3600)

# Limit query result sizes
@app.get("/api/search")
async def search(query: str, limit: int = 100):
    if limit > 1000:
        raise ValueError("Limit cannot exceed 1000")
    return await db.query(query, limit=limit)
```

### 6. Use Memory-Efficient Data Structures

```python
# Use generators for large datasets
def process_large_dataset():
    for item in dataset:  # Stream, don't load all
        yield process(item)

# Use __slots__ for classes with many instances
class Event:
    __slots__ = ['timestamp', 'type', 'data']
    def __init__(self, timestamp, type, data):
        self.timestamp = timestamp
        self.type = type
        self.data = data
```

---

## Related Alerts

- **ContainerRestartRateHigh**: OOM kills causing restarts
- **High5xxRate**: Memory exhaustion causing errors
- **GCPauseTimeHigh**: GC thrashing due to memory pressure
- **SwapUsageHigh**: System swapping due to memory pressure

---

## Escalation

- **Immediate (<5 min)**: On-call SRE
- **Within 15 min**: Infrastructure Team
- **Within 30 min**: Engineering Lead (if application issue)

---

**Version**: 1.0  
**Last Updated**: 2025-01-30  
**Owner**: SRE Team
