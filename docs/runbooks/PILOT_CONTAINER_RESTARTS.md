# Pilot: Container Restart Rate High Runbook

## Alert: ContainerRestartRateHigh / ContainerRestartCountHigh

**Severity**: Warning  
**Component**: Infrastructure  
**Pilot Critical**: Yes

---

## Overview

This alert fires when containers are restarting at an abnormal rate, indicating instability in the system. Frequent restarts can lead to:
- Service degradation or unavailability
- Data loss (if not persisted)
- Resource thrashing
- Cascading failures across dependent services

The alert uses two metrics:
- **ContainerRestartRateHigh**: Monitors `rate(container_last_seen[15m])` from cAdvisor
- **ContainerRestartCountHigh**: Monitors `increase(container_restarts_total[15m])`

---

## Quick Diagnosis (3 minutes)

### Step 1: Identify Restarting Containers

```bash
# Check container status
docker compose ps

# or for Kubernetes
kubectl get pods -n production --field-selector=status.phase!=Running

# Check restart counts
docker compose ps | awk '{print $1, $6}'
# or
kubectl get pods -n production -o custom-columns=NAME:.metadata.name,RESTARTS:.status.containerStatuses[0].restartCount
```

### Step 2: Check Recent Logs

```bash
# Check logs from last restart
docker compose logs --tail=50 <container_name>

# or for Kubernetes (last terminated container)
kubectl logs -l app=<app_name> -n production --previous

# Look for patterns:
# - OOM kills
# - Panic/crash messages
# - Failed health checks
# - Startup errors
```

### Step 3: Check Exit Codes

```bash
# Docker Compose (check exit reason)
docker inspect <container_id> | jq '.[0].State'

# Kubernetes
kubectl describe pod <pod_name> -n production | grep -A5 "Last State"

# Common exit codes:
# 0 - Normal exit (unexpected restart)
# 137 - SIGKILL (often OOM)
# 139 - SIGSEGV (segmentation fault)
# 143 - SIGTERM (graceful shutdown)
```

---

## Investigation Steps

### Phase 1: Container Health Analysis

#### 1.1 Check Resource Usage

```bash
# Check memory usage
docker stats --no-stream <container_name>

# or for Kubernetes
kubectl top pods -n production

# Check if container is hitting memory limits
docker inspect <container_id> | jq '.[0].HostConfig.Memory'
kubectl describe pod <pod_name> -n production | grep -A5 "Limits:"
```

#### 1.2 Check Container Logs for Errors

```bash
# Full logs from current instance
docker compose logs <container_name>

# Kubernetes: logs from all restarts (if available)
kubectl logs <pod_name> -n production --all-containers=true --previous

# Search for common issues:
# - "OutOfMemoryError" or "oom"
# - "panic" or "fatal"
# - "connection refused"
# - "health check failed"
# - "segmentation fault"
```

#### 1.3 Check Health Check Configuration

```bash
# Docker Compose - check healthcheck config
docker inspect <container_id> | jq '.[0].Config.Healthcheck'

# Kubernetes - check liveness/readiness probes
kubectl get pod <pod_name> -n production -o yaml | grep -A10 "livenessProbe\|readinessProbe"

# Test health check manually
curl -f http://localhost:<port>/health
# or
docker exec <container_name> curl -f http://localhost:<port>/health
```

---

### Phase 2: Root Cause Analysis

#### 2.1 Out of Memory (OOM) Kills

**Symptoms**: Exit code 137, OOM messages in logs

```bash
# Check OOM kills in system logs
dmesg | grep -i "oom"

# Check container memory limit vs usage
docker stats --no-stream <container_name>

# Kubernetes: check for OOM events
kubectl describe pod <pod_name> -n production | grep -i "oom"

# Check memory metrics in Prometheus
curl http://prometheus:9090/api/v1/query --data-urlencode 'query=container_memory_working_set_bytes{name="<container_name>"}'
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
          memory: 2G  # Increase from 1G

docker compose up -d api-server

# Kubernetes
kubectl set resources deployment/<deployment_name> \
  --limits=memory=2Gi \
  --requests=memory=1Gi \
  -n production
```

#### 2.2 Application Crashes

**Symptoms**: Stack traces, panic messages, segmentation faults

```bash
# Check application logs for crash details
docker compose logs <container_name> | grep -B10 "panic\|fatal\|segmentation"

# Check if specific requests trigger crashes
docker compose logs <container_name> | grep -B5 -A5 "error"

# Enable debug logging if available
kubectl set env deployment/<deployment_name> LOG_LEVEL=debug -n production
```

**Remediation**:

```bash
# Rollback to previous stable version
docker compose pull <service_name>:v1.2.3  # previous version
docker compose up -d <service_name>

# or for Kubernetes
kubectl rollout undo deployment/<deployment_name> -n production

# Monitor rollback
kubectl rollout status deployment/<deployment_name> -n production
```

#### 2.3 Failed Health Checks

**Symptoms**: Container restarts after health check failures

```bash
# Check health check endpoint manually
curl -v http://localhost:<port>/health

# Check health check logs
docker compose logs <container_name> | grep "health"

# Check if health check is too aggressive
docker inspect <container_id> | jq '.[0].Config.Healthcheck'

# Common issues:
# - Health check timeout too short
# - Health check interval too frequent
# - Startup time not accounted for
```

**Remediation**:

```yaml
# Adjust health check configuration (docker-compose.yml)
services:
  api-server:
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s      # Increase from 10s
      timeout: 10s       # Increase from 3s
      retries: 5         # Increase from 3
      start_period: 60s  # Add grace period for startup
```

```yaml
# Kubernetes: adjust probes
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      containers:
      - name: api-server
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 60  # Wait for startup
          periodSeconds: 30
          timeoutSeconds: 10
          failureThreshold: 5
```

#### 2.4 Dependency Failures

**Symptoms**: Errors connecting to databases, services

```bash
# Check if container can reach dependencies
docker compose exec <container_name> ping postgres
docker compose exec <container_name> ping redis
docker compose exec <container_name> ping qdrant

# Test connectivity to dependencies
docker compose exec <container_name> nc -zv postgres 5432
docker compose exec <container_name> nc -zv redis 6379

# Check dependency health
docker compose ps postgres redis qdrant
```

**Remediation**:

```yaml
# Add dependency waiting logic (docker-compose.yml)
services:
  api-server:
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    restart: on-failure
```

```bash
# Add init container to wait for dependencies (Kubernetes)
kubectl patch deployment/<deployment_name> -n production --type='json' -p='[
  {
    "op": "add",
    "path": "/spec/template/spec/initContainers",
    "value": [{
      "name": "wait-for-db",
      "image": "busybox:1.28",
      "command": ["sh", "-c", "until nc -z postgres 5432; do sleep 2; done"]
    }]
  }
]'
```

#### 2.5 Resource Contention

**Symptoms**: High CPU, slow startup, timeouts

```bash
# Check system resource availability
top -bn1 | head -20
free -h
df -h

# Check container resource usage
docker stats --no-stream

# Check for CPU throttling
docker inspect <container_id> | jq '.[0].HostConfig.CpuQuota, .[0].HostConfig.CpuPeriod'

# Kubernetes: check node pressure
kubectl describe nodes | grep -i "pressure\|condition"
```

**Remediation**:

```bash
# Increase CPU limits
kubectl set resources deployment/<deployment_name> \
  --limits=cpu=2000m \
  --requests=cpu=500m \
  -n production

# Scale horizontally if possible
kubectl scale deployment/<deployment_name> --replicas=3 -n production

# Add node selectors for dedicated nodes
kubectl patch deployment/<deployment_name> -n production --type='json' -p='[
  {
    "op": "add",
    "path": "/spec/template/spec/nodeSelector",
    "value": {"workload": "compute-intensive"}
  }
]'
```

---

## Remediation Summary

### Immediate Actions

1. **Check Container Status**
   ```bash
   docker compose ps
   kubectl get pods -n production
   ```

2. **Review Recent Logs**
   ```bash
   docker compose logs --tail=100 <container_name>
   kubectl logs <pod_name> -n production --previous
   ```

3. **Increase Resources (if OOM)**
   ```bash
   kubectl set resources deployment/<name> --limits=memory=2Gi -n production
   ```

4. **Rollback (if application issue)**
   ```bash
   kubectl rollout undo deployment/<name> -n production
   ```

5. **Adjust Health Checks (if too aggressive)**
   ```yaml
   # Increase timeouts and grace periods
   ```

---

## Prevention

### 1. Set Appropriate Resource Limits

```yaml
# Kubernetes
resources:
  requests:
    memory: "512Mi"
    cpu: "500m"
  limits:
    memory: "2Gi"
    cpu: "2000m"
```

### 2. Implement Gradual Rollouts

```yaml
# Kubernetes: rolling update strategy
spec:
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
```

### 3. Add Startup Probes

```yaml
# Kubernetes: separate startup probe
startupProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 10
  failureThreshold: 30  # Allow up to 5 minutes for startup
```

### 4. Monitor Memory Trends

```yaml
# Prometheus alert for memory growth
- alert: MemoryLeakDetected
  expr: |
    (
      container_memory_working_set_bytes{name!=""} -
      container_memory_working_set_bytes{name!=""} offset 1h
    ) / container_memory_working_set_bytes{name!=""} offset 1h > 0.2
  for: 1h
  labels:
    severity: warning
```

### 5. Implement Graceful Shutdown

```python
# Example: Python signal handling
import signal
import sys

def signal_handler(sig, frame):
    logger.info("Gracefully shutting down...")
    # Close connections
    db.close()
    redis.close()
    sys.exit(0)

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)
```

### 6. Use Pod Disruption Budgets (Kubernetes)

```yaml
# Ensure minimum availability during disruptions
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: api-server-pdb
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: api-server
```

---

## Related Alerts

- **MemoryPressureDetected**: High memory usage leading to OOM
- **High5xxRate**: Application errors causing crashes
- **PodCrashLoopBackOff**: Repeated startup failures
- **NodeNotReady**: Infrastructure issues affecting containers

---

## Escalation

- **Immediate (<5 min)**: On-call SRE
- **Within 15 min**: Infrastructure Team (if infrastructure issue)
- **Within 30 min**: Engineering Lead (if application issue)

---

**Version**: 1.0  
**Last Updated**: 2025-01-30  
**Owner**: SRE Team
