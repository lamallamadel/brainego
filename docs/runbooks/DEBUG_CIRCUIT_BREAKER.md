# Debug Circuit Breaker Playbook

## Table of Contents
1. [Overview](#overview)
2. [Quick Diagnosis](#quick-diagnosis)
3. [Investigation Steps](#investigation-steps)
4. [Common Scenarios](#common-scenarios)
5. [Circuit Breaker States](#circuit-breaker-states)
6. [Remediation](#remediation)
7. [Prevention](#prevention)

---

## Overview

This playbook guides you through investigating and resolving circuit breaker issues in the AI Platform.

### Circuit Breaker Pattern

The circuit breaker pattern prevents cascading failures by:
1. **Closed**: Normal operation, requests pass through
2. **Open**: Failures exceeded threshold, requests blocked
3. **Half-Open**: Testing if service recovered, limited requests allowed

### Thresholds

| Metric | Closed → Open | Half-Open → Closed |
|--------|---------------|---------------------|
| Error Rate | >50% over 30s | <10% for 10 requests |
| Timeout Rate | >30% over 30s | <5% for 10 requests |
| Consecutive Failures | >5 | N/A |
| Recovery Time | N/A | 30 seconds |

### Symptoms

- Requests failing with "Circuit breaker open" errors
- Dependency unavailable errors
- Alert fired: `CircuitBreakerOpen` or `CircuitBreakerDegraded`
- Increased error rates without underlying service failure

---

## Quick Diagnosis

### Step 1: Check Circuit Breaker Status (2 minutes)

```bash
# Check all circuit breakers
curl http://localhost:8000/admin/circuit-breaker/status | jq

# Output example:
# {
#   "qdrant_search": {
#     "state": "open",
#     "failure_count": 15,
#     "last_failure": "2025-01-30T10:45:23Z",
#     "next_attempt": "2025-01-30T10:45:53Z"
#   },
#   "postgres_query": {
#     "state": "closed",
#     "failure_count": 0
#   }
# }

# Check circuit breaker metrics
curl http://localhost:8000/metrics | grep circuit_breaker

# Check Grafana dashboard
open http://localhost:3000/d/sre-incident-response
```

### Step 2: Identify Affected Service (1 minute)

```bash
# Which circuit breaker is open?
curl http://localhost:8000/admin/circuit-breaker/status | jq 'to_entries[] | select(.value.state == "open")'

# Check service health
curl http://localhost:6333/health  # Qdrant
curl http://localhost:7474/        # Neo4j
psql -h localhost -U ai_user -d ai_platform -c "SELECT 1"  # PostgreSQL
```

### Step 3: Determine Root Cause (3 minutes)

**Is the underlying service actually down?**

```bash
# Check service pods
kubectl get pods -n production | grep -E "qdrant|postgres|neo4j"

# Check service logs
kubectl logs -l app=qdrant --tail=50 -n production
kubectl logs -l app=postgres --tail=50 -n production

# Check service metrics
curl http://localhost:6333/metrics
curl http://localhost:9187/metrics  # Postgres exporter
```

**Or is it a configuration issue?**

```bash
# Check recent config changes
kubectl get configmap -n production
kubectl describe configmap api-server-config -n production

# Check deployment history
kubectl rollout history deployment/api-server -n production
```

---

## Investigation Steps

### Phase 1: Circuit Breaker Analysis

#### 1.1 Get Circuit Breaker Details

```bash
# Detailed status for specific circuit breaker
curl http://localhost:8000/admin/circuit-breaker/status/qdrant_search | jq

# Expected output:
# {
#   "name": "qdrant_search",
#   "state": "open",
#   "failure_count": 15,
#   "success_count": 0,
#   "last_failure_time": "2025-01-30T10:45:23Z",
#   "last_failure_reason": "ConnectionTimeout",
#   "consecutive_failures": 8,
#   "failure_rate": 0.85,
#   "next_attempt_time": "2025-01-30T10:45:53Z",
#   "half_open_allowed": false
# }
```

#### 1.2 Check Circuit Breaker History

```bash
# Get recent circuit breaker events
curl http://localhost:8000/admin/circuit-breaker/history | jq

# Or from logs
kubectl logs -l app=api-server --tail=500 -n production | grep "circuit_breaker"

# Look for patterns:
# - When did it open?
# - What triggered it?
# - Has it opened/closed multiple times?
```

#### 1.3 Review Circuit Breaker Configuration

```bash
# Get current configuration
curl http://localhost:8000/admin/circuit-breaker/config | jq

# Expected output:
# {
#   "qdrant_search": {
#     "failure_threshold": 5,
#     "recovery_timeout": 30,
#     "expected_exception": ["ConnectionError", "TimeoutError"],
#     "half_open_max_requests": 10
#   }
# }

# Check if thresholds are appropriate
# - Too sensitive? (opens too easily)
# - Too lenient? (doesn't protect from cascading failures)
```

---

### Phase 2: Underlying Service Health

#### 2.1 Qdrant Circuit Breaker

**Check Qdrant Health**:

```bash
# Health check
curl http://localhost:6333/health

# Check if Qdrant is responding
time curl http://localhost:6333/collections

# Check Qdrant metrics
curl http://localhost:6333/metrics | grep -E "error|timeout|latency"

# Check Qdrant logs
docker compose logs --tail=100 qdrant
# Or Kubernetes
kubectl logs -l app=qdrant --tail=100 -n production

# Check Qdrant resource usage
kubectl top pod -l app=qdrant -n production
```

**Common Qdrant Issues**:
- High memory usage causing OOM
- Index optimization in progress
- Disk I/O saturation
- Network connectivity issues
- Collection not found

**Solutions**:

```bash
# Restart Qdrant if hung
kubectl rollout restart statefulset/qdrant -n production

# Scale Qdrant if overloaded
kubectl scale statefulset/qdrant --replicas=3 -n production

# Optimize collection
curl -X POST http://localhost:6333/collections/documents/index \
  -H "Content-Type: application/json" \
  -d '{"action": "optimize"}'
```

#### 2.2 PostgreSQL Circuit Breaker

**Check PostgreSQL Health**:

```bash
# Connection test
psql -h localhost -U ai_user -d ai_platform -c "SELECT 1"

# Check active connections
docker exec postgres psql -U ai_user -d ai_platform -c "
  SELECT count(*), state FROM pg_stat_activity GROUP BY state;
"

# Check for long-running queries
docker exec postgres psql -U ai_user -d ai_platform -c "
  SELECT pid, now() - query_start as duration, state, query 
  FROM pg_stat_activity 
  WHERE state != 'idle' AND now() - query_start > interval '30 seconds'
  ORDER BY duration DESC;
"

# Check for locks
docker exec postgres psql -U ai_user -d ai_platform -c "
  SELECT pid, usename, pg_blocking_pids(pid) as blocked_by, query 
  FROM pg_stat_activity 
  WHERE cardinality(pg_blocking_pids(pid)) > 0;
"

# Check resource usage
kubectl top pod -l app=postgres -n production
```

**Common PostgreSQL Issues**:
- Connection pool exhausted
- Long-running queries causing timeouts
- Database locks
- Disk full
- Replication lag (if using replication)

**Solutions**:

```bash
# Increase connection pool
kubectl set env deployment/api-server DB_POOL_SIZE=100 -n production

# Kill long-running query
docker exec postgres psql -U ai_user -d ai_platform -c "SELECT pg_terminate_backend(<pid>);"

# Restart PostgreSQL if needed
kubectl rollout restart statefulset/postgres -n production
```

#### 2.3 Neo4j Circuit Breaker

**Check Neo4j Health**:

```bash
# Health check
curl http://localhost:7474/

# Test connection
docker exec neo4j cypher-shell -u neo4j -p neo4j_password "RETURN 1"

# Check for slow queries
docker exec neo4j cypher-shell -u neo4j -p neo4j_password "
  CALL dbms.listQueries() 
  YIELD queryId, query, elapsedTimeMillis 
  WHERE elapsedTimeMillis > 10000 
  RETURN queryId, query, elapsedTimeMillis;
"

# Check Neo4j status
docker exec neo4j neo4j status

# Check resource usage
kubectl top pod -l app=neo4j -n production
```

**Common Neo4j Issues**:
- Long-running graph queries
- Memory pressure
- Index building
- Transaction locks

**Solutions**:

```bash
# Kill slow query
docker exec neo4j cypher-shell -u neo4j -p neo4j_password "CALL dbms.killQuery('<queryId>');"

# Restart Neo4j
kubectl rollout restart statefulset/neo4j -n production

# Warm cache after restart
docker exec neo4j cypher-shell -u neo4j -p neo4j_password "MATCH (n) RETURN count(n);"
```

#### 2.4 External API Circuit Breaker

**Check External Service**:

```bash
# Direct health check
curl -w "\nTime: %{time_total}s\n" -o /dev/null -s http://external-api.example.com/health

# Test with timeout
timeout 10 curl http://external-api.example.com/health

# Check DNS resolution
nslookup external-api.example.com

# Check network connectivity
ping -c 5 external-api.example.com
```

**Common External API Issues**:
- Service outage (provider-side)
- Rate limiting
- Network issues
- DNS problems
- Authentication expired

**Solutions**:

```bash
# Increase timeout threshold
curl -X PATCH http://localhost:8000/admin/circuit-breaker/config/external_api \
  -H "Content-Type: application/json" \
  -d '{"timeout_seconds": 30}'

# Enable retry with backoff
curl -X PATCH http://localhost:8000/admin/circuit-breaker/config/external_api \
  -H "Content-Type: application/json" \
  -d '{"retry_count": 3, "backoff_seconds": 2}'

# If persistent issues, consider fallback/degraded mode
curl -X POST http://localhost:8000/admin/features/enable-fallback \
  -H "Content-Type: application/json" \
  -d '{"feature": "external_api_fallback"}'
```

---

### Phase 3: Network and Connectivity

#### 3.1 Check Network Connectivity

```bash
# Test connectivity from application pod
kubectl exec -it deployment/api-server -n production -- ping qdrant
kubectl exec -it deployment/api-server -n production -- ping postgres

# Check DNS resolution
kubectl exec -it deployment/api-server -n production -- nslookup qdrant
kubectl exec -it deployment/api-server -n production -- nslookup postgres

# Test port connectivity
kubectl exec -it deployment/api-server -n production -- telnet qdrant 6333
kubectl exec -it deployment/api-server -n production -- telnet postgres 5432
```

#### 3.2 Check Network Policies

```bash
# Check if network policies are blocking
kubectl get networkpolicies -n production

# Check service endpoints
kubectl get endpoints -n production

# Check service configuration
kubectl describe service qdrant -n production
kubectl describe service postgres -n production
```

#### 3.3 Check Timeouts

```bash
# Check application timeout configuration
kubectl get configmap api-server-config -n production -o yaml | grep -i timeout

# Check if timeouts are too aggressive
curl http://localhost:8000/admin/config | jq '.timeouts'

# Test actual latency
time curl http://localhost:6333/collections
time psql -h localhost -U ai_user -d ai_platform -c "SELECT 1"
```

---

## Common Scenarios

### Scenario 1: Circuit Breaker Opens During High Load

**Symptoms**:
- Circuit breaker opens when traffic increases
- Underlying service is healthy
- Timeouts during peak traffic

**Root Cause**: Service can't handle load, requests timing out

**Solution**:

```bash
# Scale underlying service
kubectl scale statefulset/qdrant --replicas=3 -n production

# Increase timeout threshold
curl -X PATCH http://localhost:8000/admin/circuit-breaker/config/qdrant_search \
  -H "Content-Type: application/json" \
  -d '{"timeout_seconds": 10, "failure_threshold": 10}'

# Add connection pooling/rate limiting
kubectl set env deployment/api-server \
  QDRANT_POOL_SIZE=50 \
  QDRANT_MAX_CONCURRENT=100 \
  -n production
```

---

### Scenario 2: Circuit Breaker Stuck Open

**Symptoms**:
- Circuit breaker stays open even after service recovered
- Half-open state never reached
- Manual intervention required

**Root Cause**: Configuration issue or bug in circuit breaker logic

**Solution**:

```bash
# Manually reset circuit breaker
curl -X POST http://localhost:8000/admin/circuit-breaker/reset/qdrant_search

# Or reset all
curl -X POST http://localhost:8000/admin/circuit-breaker/reset-all

# Verify service is actually healthy
curl http://localhost:6333/health

# Check circuit breaker configuration
curl http://localhost:8000/admin/circuit-breaker/config/qdrant_search | jq

# Adjust recovery timeout if needed
curl -X PATCH http://localhost:8000/admin/circuit-breaker/config/qdrant_search \
  -H "Content-Type: application/json" \
  -d '{"recovery_timeout": 15}'
```

---

### Scenario 3: Flapping Circuit Breaker

**Symptoms**:
- Circuit breaker repeatedly opens and closes
- System unstable
- Alert storm

**Root Cause**: Service is intermittently failing, thresholds too sensitive

**Solution**:

```bash
# Increase failure threshold
curl -X PATCH http://localhost:8000/admin/circuit-breaker/config/qdrant_search \
  -H "Content-Type: application/json" \
  -d '{"failure_threshold": 10, "recovery_timeout": 60}'

# Increase half-open test requests
curl -X PATCH http://localhost:8000/admin/circuit-breaker/config/qdrant_search \
  -H "Content-Type: application/json" \
  -d '{"half_open_max_requests": 20}'

# Check for underlying intermittent issues
kubectl logs -l app=qdrant --tail=200 -n production | grep -i error

# Consider adding retry logic before circuit breaker
```

---

### Scenario 4: Multiple Circuit Breakers Open

**Symptoms**:
- Multiple circuit breakers open simultaneously
- System-wide degradation
- Cascading failures

**Root Cause**: Infrastructure issue, network problem, or overload

**Solution**:

```bash
# Check infrastructure health
kubectl get nodes
kubectl top nodes

# Check for network issues
kubectl get pods -n production -o wide

# Check for recent changes
kubectl rollout history deployment/api-server -n production

# Consider emergency measures
# 1. Scale down load
curl -X POST http://localhost:8000/admin/rate-limit/enable-aggressive

# 2. Enable degraded mode
curl -X POST http://localhost:8000/admin/mode/degraded

# 3. Trigger failover if multi-region
# See MULTI_REGION_FAILOVER_RUNBOOK.md
```

---

### Scenario 5: Circuit Breaker Opens Due to Slow Queries

**Symptoms**:
- Circuit breaker opens due to timeouts
- Service is up but slow
- Query duration increases

**Root Cause**: Database performance issue

**Solution**:

```bash
# Identify slow queries
docker exec postgres psql -U ai_user -d ai_platform -c "
  SELECT query, calls, mean_exec_time, max_exec_time
  FROM pg_stat_statements
  ORDER BY mean_exec_time DESC
  LIMIT 10;
"

# Add missing indexes
docker exec postgres psql -U ai_user -d ai_platform -c "
  CREATE INDEX CONCURRENTLY idx_slow_query ON table_name(column_name);
"

# Increase timeout temporarily
curl -X PATCH http://localhost:8000/admin/circuit-breaker/config/postgres_query \
  -H "Content-Type: application/json" \
  -d '{"timeout_seconds": 30}'

# Optimize queries (application code change)
```

---

## Circuit Breaker States

### Closed State

**Behavior**:
- All requests pass through
- Failures are counted
- Transition to Open if failures exceed threshold

**Monitoring**:
```bash
curl http://localhost:8000/metrics | grep 'circuit_breaker_state{state="closed"}'
```

---

### Open State

**Behavior**:
- All requests immediately fail
- No requests sent to underlying service
- Wait for recovery timeout before trying again

**When Circuit Opens**:
- Failure rate > threshold
- Or consecutive failures > threshold

**Duration**: Configured recovery timeout (default 30s)

**Monitoring**:
```bash
curl http://localhost:8000/metrics | grep 'circuit_breaker_state{state="open"}'

# How long until next attempt?
curl http://localhost:8000/admin/circuit-breaker/status/qdrant_search | jq '.next_attempt_time'
```

---

### Half-Open State

**Behavior**:
- Limited requests allowed through (e.g., 10)
- Testing if service recovered
- If successful, transition to Closed
- If failures, transition back to Open

**Success Criteria**: e.g., 8/10 requests succeed

**Monitoring**:
```bash
curl http://localhost:8000/metrics | grep 'circuit_breaker_state{state="half_open"}'

# Current test results
curl http://localhost:8000/admin/circuit-breaker/status/qdrant_search | jq '.half_open_test_count'
```

---

## Remediation

### Immediate Actions

#### 1. Manual Circuit Breaker Reset

**When to Use**: Service is healthy but circuit breaker stuck open

```bash
# Verify service is healthy
curl http://localhost:6333/health

# Reset circuit breaker
curl -X POST http://localhost:8000/admin/circuit-breaker/reset/qdrant_search

# Monitor results
watch -n 5 'curl -s http://localhost:8000/admin/circuit-breaker/status/qdrant_search | jq'
```

#### 2. Adjust Circuit Breaker Thresholds

**When to Use**: Circuit breaker too sensitive or too lenient

```bash
# Make less sensitive (allow more failures)
curl -X PATCH http://localhost:8000/admin/circuit-breaker/config/qdrant_search \
  -H "Content-Type: application/json" \
  -d '{
    "failure_threshold": 10,
    "timeout_seconds": 10,
    "recovery_timeout": 60
  }'

# Verify changes
curl http://localhost:8000/admin/circuit-breaker/config/qdrant_search | jq
```

#### 3. Disable Circuit Breaker

**When to Use**: Emergency, circuit breaker causing more harm than good

```bash
# Disable specific circuit breaker
curl -X POST http://localhost:8000/admin/circuit-breaker/disable/qdrant_search

# Or disable all (use with caution!)
curl -X POST http://localhost:8000/admin/circuit-breaker/disable-all

# Re-enable when ready
curl -X POST http://localhost:8000/admin/circuit-breaker/enable/qdrant_search
```

#### 4. Enable Fallback Behavior

**When to Use**: Service degraded, need to continue operating

```bash
# Enable fallback for Qdrant (e.g., use cache or degraded results)
curl -X POST http://localhost:8000/admin/features/enable \
  -H "Content-Type: application/json" \
  -d '{"feature": "qdrant_fallback"}'

# Configure fallback behavior
curl -X PATCH http://localhost:8000/admin/circuit-breaker/config/qdrant_search \
  -H "Content-Type: application/json" \
  -d '{"fallback_enabled": true, "fallback_mode": "cache"}'
```

---

### Fix Underlying Service

#### Restart Service

```bash
# Kubernetes
kubectl rollout restart statefulset/qdrant -n production

# Docker Compose
docker compose restart qdrant

# Monitor restart
kubectl rollout status statefulset/qdrant -n production
```

#### Scale Service

```bash
# Horizontal scaling
kubectl scale statefulset/qdrant --replicas=3 -n production

# Vertical scaling (more resources)
kubectl set resources statefulset/qdrant \
  --limits=cpu=2000m,memory=4Gi \
  --requests=cpu=1000m,memory=2Gi \
  -n production
```

#### Rollback

```bash
# If circuit breaker issues started after deployment
kubectl rollout undo deployment/api-server -n production

# Or use blue-green rollback
# See ROLLBACK_PROCEDURES.md
```

---

## Prevention

### Circuit Breaker Best Practices

1. **Set Appropriate Thresholds**
   - Not too sensitive (false opens)
   - Not too lenient (doesn't protect)
   - Based on actual service SLAs

2. **Implement Fallback Behavior**
   ```python
   @circuit_breaker(fallback=use_cache)
   async def search_vectors(query):
       return await qdrant.search(query)
   
   def use_cache(query):
       # Return cached or degraded results
       return cache.get(query) or []
   ```

3. **Use Bulkheads**
   - Isolate failures
   - Separate thread pools for different services
   - Prevent one slow service from blocking others

4. **Implement Retry Logic**
   ```python
   @retry(max_attempts=3, backoff=exponential)
   @circuit_breaker()
   async def call_external_api():
       return await http_client.get('...')
   ```

5. **Monitor Circuit Breaker Health**
   ```yaml
   # Prometheus alerts
   - alert: CircuitBreakerOpen
     expr: circuit_breaker_state{state="open"} == 1
     for: 5m
     labels:
       severity: warning
   
   - alert: CircuitBreakerFlapping
     expr: rate(circuit_breaker_state_changes_total[5m]) > 0.5
     for: 5m
     labels:
       severity: warning
   ```

### Testing

```python
# Test circuit breaker behavior
def test_circuit_breaker_opens():
    # Simulate failures
    for i in range(6):
        with pytest.raises(ServiceUnavailable):
            call_service()
    
    # Circuit should be open
    assert circuit_breaker.state == "open"
    
    # Requests should fail fast
    with pytest.raises(CircuitBreakerOpen):
        call_service()

def test_circuit_breaker_recovers():
    # Open circuit
    open_circuit_breaker()
    
    # Wait for recovery timeout
    time.sleep(recovery_timeout)
    
    # Half-open state
    assert circuit_breaker.state == "half_open"
    
    # Successful requests close circuit
    for i in range(10):
        call_service()  # Succeed
    
    assert circuit_breaker.state == "closed"
```

### Configuration Guidelines

```yaml
# Example circuit breaker configuration
circuit_breakers:
  qdrant_search:
    failure_threshold: 5          # Open after 5 failures
    success_threshold: 10         # Close after 10 successes in half-open
    timeout_seconds: 5            # Request timeout
    recovery_timeout: 30          # Wait 30s before half-open
    expected_exceptions:
      - ConnectionError
      - TimeoutError
    half_open_max_requests: 10    # Allow 10 requests in half-open
    fallback_enabled: true
    
  external_api:
    failure_threshold: 3
    timeout_seconds: 10
    recovery_timeout: 60
    retry_count: 3
    retry_backoff: exponential
```

---

## Appendix: Circuit Breaker Implementation Reference

### Python Example (using pybreaker)

```python
from pybreaker import CircuitBreaker

# Configure circuit breaker
breaker = CircuitBreaker(
    fail_max=5,              # Open after 5 failures
    timeout_duration=30,     # Try half-open after 30s
    expected_exception=TimeoutError,
    name='qdrant_search'
)

@breaker
async def search_vectors(query: str):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            'http://qdrant:6333/collections/documents/points/search',
            json={'vector': query, 'limit': 10},
            timeout=5.0
        )
        return response.json()

# Usage with fallback
try:
    results = await search_vectors(query)
except CircuitBreakerError:
    # Circuit is open, use fallback
    results = get_from_cache(query)
```

### Monitoring Metrics

```python
from prometheus_client import Counter, Gauge, Histogram

# Circuit breaker state
circuit_breaker_state = Gauge(
    'circuit_breaker_state',
    'Circuit breaker state (0=closed, 1=open, 2=half_open)',
    ['name']
)

# State transitions
circuit_breaker_transitions = Counter(
    'circuit_breaker_state_changes_total',
    'Total circuit breaker state changes',
    ['name', 'from_state', 'to_state']
)

# Request outcomes
circuit_breaker_requests = Counter(
    'circuit_breaker_requests_total',
    'Total requests through circuit breaker',
    ['name', 'outcome']  # success, failure, rejected
)

# Response time
circuit_breaker_duration = Histogram(
    'circuit_breaker_request_duration_seconds',
    'Request duration through circuit breaker',
    ['name']
)
```

---

**Version**: 1.0  
**Last Updated**: 2025-01-30  
**Next Review**: 2025-02-28  
**Owner**: SRE Team
