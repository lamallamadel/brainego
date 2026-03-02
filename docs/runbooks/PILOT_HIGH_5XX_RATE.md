# Pilot: High 5xx Error Rate Runbook

## Alert: High5xxRate

**Severity**: Critical  
**Component**: API Services  
**Pilot Critical**: Yes

---

## Overview

This alert fires when the rate of 5xx (server-side) errors exceeds 5% of total requests over a 5-minute window. This indicates a critical service degradation that requires immediate investigation.

5xx errors represent server-side failures and can indicate:
- Backend service crashes or unavailability
- Database connection failures
- Resource exhaustion (memory, CPU, connections)
- Unhandled exceptions in application code
- Infrastructure issues

---

## Quick Diagnosis (3 minutes)

### Step 1: Identify Affected Service

```bash
# Check which services are returning 5xx errors
curl http://prometheus:9090/api/v1/query --data-urlencode 'query=sum by (job, instance) (rate(http_requests_total{status=~"5.."}[5m]))'

# Check Grafana for visual analysis
open http://localhost:3000/d/sre-incident-response
```

### Step 2: Check Service Health

```bash
# Check pod/container status
docker compose ps
# or for Kubernetes
kubectl get pods -n production

# Check recent logs for errors
docker compose logs --tail=100 api-server | grep -i error
# or
kubectl logs -l app=api-server --tail=100 -n production | grep -i error
```

### Step 3: Determine Error Type

```bash
# Break down by specific status code
curl http://prometheus:9090/api/v1/query --data-urlencode 'query=sum by (status) (rate(http_requests_total{status=~"5.."}[5m]))'

# Common status codes:
# 500 - Internal Server Error (application bug)
# 502 - Bad Gateway (upstream service unavailable)
# 503 - Service Unavailable (overload or maintenance)
# 504 - Gateway Timeout (slow backend response)
```

---

## Investigation Steps

### Phase 1: Application Health

#### 1.1 Check Service Logs

```bash
# API Server logs
docker compose logs --tail=200 api-server | grep -E "500|502|503|504|ERROR|Exception"

# Look for patterns:
# - Stack traces (application bugs)
# - Connection errors (database/service issues)
# - Timeout errors (slow queries)
# - Resource errors (OOM, disk full)
```

#### 1.2 Check Resource Usage

```bash
# Check memory and CPU usage
docker stats --no-stream

# or for Kubernetes
kubectl top pods -n production

# Check if any container is OOM killed
docker compose logs api-server | grep -i "oom"
kubectl describe pod -l app=api-server -n production | grep -i "oom"
```

#### 1.3 Check Application Metrics

```bash
# Check request latency (slow requests may cause timeouts)
curl http://prometheus:9090/api/v1/query --data-urlencode 'query=histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))'

# Check concurrent requests
curl http://prometheus:9090/api/v1/query --data-urlencode 'query=http_requests_in_flight'

# Check error rate by endpoint
curl http://prometheus:9090/api/v1/query --data-urlencode 'query=sum by (path) (rate(http_requests_total{status=~"5.."}[5m]))'
```

---

### Phase 2: Backend Services

#### 2.1 Check Database Connectivity

```bash
# Test PostgreSQL connection
docker exec postgres psql -U ai_user -d ai_platform -c "SELECT 1"

# Check active connections
docker exec postgres psql -U ai_user -d ai_platform -c "
  SELECT count(*), state FROM pg_stat_activity GROUP BY state;
"

# Check for connection pool exhaustion
curl http://localhost:8000/metrics | grep db_pool
```

#### 2.2 Check Vector Database (Qdrant)

```bash
# Health check
curl http://localhost:6333/health

# Check if collections are available
curl http://localhost:6333/collections

# Check Qdrant metrics
curl http://localhost:6333/metrics | grep -E "error|latency"
```

#### 2.3 Check Graph Database (Neo4j)

```bash
# Health check
curl http://localhost:7474/

# Test query
docker exec neo4j cypher-shell -u neo4j -p neo4j_password "RETURN 1"

# Check for slow queries
docker exec neo4j cypher-shell -u neo4j -p neo4j_password "
  CALL dbms.listQueries() YIELD queryId, query, elapsedTimeMillis 
  WHERE elapsedTimeMillis > 5000
  RETURN queryId, query, elapsedTimeMillis;
"
```

#### 2.4 Check Redis Cache

```bash
# Check Redis connectivity
docker exec redis redis-cli ping

# Check memory usage
docker exec redis redis-cli info memory | grep used_memory_human

# Check for slow commands
docker exec redis redis-cli slowlog get 10
```

---

### Phase 3: Infrastructure

#### 3.1 Check Network Connectivity

```bash
# Test connectivity between services
docker compose exec api-server ping postgres
docker compose exec api-server ping qdrant
docker compose exec api-server ping neo4j

# Check DNS resolution
docker compose exec api-server nslookup postgres
```

#### 3.2 Check Disk Space

```bash
# Check available disk space
df -h

# Check Docker disk usage
docker system df

# Check if any service is affected by disk pressure
docker compose logs | grep -i "disk\|space"
```

#### 3.3 Check System Load

```bash
# Check system load
uptime

# Check CPU and memory on host
top -bn1 | head -20

# Check for resource constraints
dmesg | tail -50 | grep -i "oom\|killed"
```

---

## Remediation

### Immediate Actions

#### 1. Restart Affected Service (if unhealthy)

```bash
# Docker Compose
docker compose restart api-server

# Kubernetes
kubectl rollout restart deployment/api-server -n production

# Monitor restart
docker compose logs -f api-server
# or
kubectl logs -f -l app=api-server -n production
```

#### 2. Scale Up Service (if overloaded)

```bash
# Docker Compose (requires compose file change)
docker compose up -d --scale api-server=3

# Kubernetes
kubectl scale deployment/api-server --replicas=5 -n production

# Verify scaling
kubectl get pods -l app=api-server -n production
```

#### 3. Enable Circuit Breakers (if backend failing)

```bash
# Enable circuit breaker to prevent cascading failures
curl -X POST http://localhost:8000/admin/circuit-breaker/enable/qdrant_search

# Enable degraded mode if needed
curl -X POST http://localhost:8000/admin/mode/degraded
```

#### 4. Clear Connection Pools (if connection exhaustion)

```bash
# Restart service to clear connection pools
docker compose restart api-server

# Or manually clear via admin endpoint (if available)
curl -X POST http://localhost:8000/admin/connections/reset
```

---

### Root Cause Fixes

#### Scenario 1: Application Bug (500 Internal Server Error)

**Symptoms**: Stack traces in logs, specific endpoints failing

```bash
# Identify failing endpoint
docker compose logs api-server | grep -B5 "500 Internal Server Error"

# Rollback to previous version
docker compose pull api-server:v1.2.3  # previous stable version
docker compose up -d api-server

# or for Kubernetes
kubectl rollout undo deployment/api-server -n production
```

#### Scenario 2: Database Connection Failure (502/503)

**Symptoms**: Connection errors, timeout errors

```bash
# Restart database if unhealthy
docker compose restart postgres

# Increase connection pool size
kubectl set env deployment/api-server DB_POOL_SIZE=100 -n production

# Check and terminate long-running queries
docker exec postgres psql -U ai_user -d ai_platform -c "
  SELECT pg_terminate_backend(pid) 
  FROM pg_stat_activity 
  WHERE state = 'active' AND now() - query_start > interval '5 minutes';
"
```

#### Scenario 3: Resource Exhaustion (503 Service Unavailable)

**Symptoms**: High memory/CPU usage, OOM kills

```bash
# Increase resource limits
kubectl set resources deployment/api-server \
  --limits=cpu=2000m,memory=4Gi \
  --requests=cpu=1000m,memory=2Gi \
  -n production

# Enable memory profiling (if available)
curl -X POST http://localhost:8000/admin/debug/heap-dump

# Clear caches to free memory
curl -X POST http://localhost:8000/admin/cache/clear
```

#### Scenario 4: Upstream Timeout (504 Gateway Timeout)

**Symptoms**: Slow backend responses, timeout errors

```bash
# Increase timeout settings
kubectl set env deployment/api-server \
  QDRANT_TIMEOUT=30 \
  POSTGRES_TIMEOUT=20 \
  -n production

# Optimize slow queries (identified in investigation)
docker exec postgres psql -U ai_user -d ai_platform -c "
  CREATE INDEX CONCURRENTLY idx_slow_query ON table_name(column_name);
"

# Scale backend services
kubectl scale statefulset/qdrant --replicas=3 -n production
```

---

## Prevention

### 1. Implement Health Checks

```yaml
# Docker Compose
services:
  api-server:
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
```

### 2. Add Retry Logic with Exponential Backoff

```python
# Example: Python retry decorator
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True
)
async def call_backend_service():
    return await http_client.get(url)
```

### 3. Implement Circuit Breakers

```python
# Use circuit breakers to prevent cascading failures
from pybreaker import CircuitBreaker

breaker = CircuitBreaker(fail_max=5, timeout_duration=60)

@breaker
async def query_database():
    return await db.execute(query)
```

### 4. Set Up Resource Limits

```yaml
# Kubernetes resource limits
resources:
  requests:
    memory: "512Mi"
    cpu: "500m"
  limits:
    memory: "2Gi"
    cpu: "2000m"
```

### 5. Monitor Error Budget

```yaml
# SLO: 99.9% success rate (0.1% error budget)
- alert: ErrorBudgetExhausted
  expr: |
    (
      sum(rate(http_requests_total{status=~"5.."}[7d])) /
      sum(rate(http_requests_total[7d]))
    ) > 0.001
  for: 1h
  labels:
    severity: warning
```

### 6. Implement Graceful Degradation

```python
# Fallback to cached results if backend fails
async def get_search_results(query):
    try:
        return await qdrant.search(query)
    except Exception as e:
        logger.warning(f"Qdrant search failed: {e}")
        return cache.get(f"search:{query}") or []
```

---

## Related Alerts

- **MemoryPressureDetected**: High memory usage leading to OOM
- **ContainerRestartRateHigh**: Services crashing and restarting
- **CircuitBreakerOpen**: Circuit breakers triggering due to failures
- **DatabaseConnectionPoolExhausted**: Connection pool issues

---

## Escalation

- **Immediate (<5 min)**: On-call SRE
- **Within 15 min**: Engineering Lead (if application bug)
- **Within 30 min**: VP Engineering (if prolonged outage)

---

**Version**: 1.0  
**Last Updated**: 2025-01-30  
**Owner**: SRE Team
