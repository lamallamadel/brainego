# Debug Latency Spike Playbook

## Table of Contents
1. [Overview](#overview)
2. [Quick Diagnosis](#quick-diagnosis)
3. [Investigation Steps](#investigation-steps)
4. [Common Causes and Solutions](#common-causes-and-solutions)
5. [Mitigation Strategies](#mitigation-strategies)
6. [Prevention](#prevention)

---

## Overview

This playbook guides you through investigating and resolving latency spikes in the AI Platform.

### Latency SLA Thresholds

| Metric | Target | Warning | Critical |
|--------|--------|---------|----------|
| P50    | <200ms | >500ms  | >1s      |
| P95    | <500ms | >1s     | >2s      |
| P99    | <1s    | >1.5s   | >3s      |

### Symptoms

- P99 latency exceeds 1.5s
- User complaints about slow responses
- Timeout errors increasing
- Alert fired: `HighLatency` or `LatencySpike`

---

## Quick Diagnosis

### Step 1: Verify the Problem (2 minutes)

```bash
# Check current latency in Grafana
open http://localhost:3000/d/platform-overview

# Quick Prometheus query
curl -s 'http://localhost:9090/api/v1/query?query=histogram_quantile(0.99,rate(http_request_duration_seconds_bucket[5m]))' | jq

# Check if affecting all endpoints or specific ones
curl -s 'http://localhost:9090/api/v1/query?query=histogram_quantile(0.99,rate(http_request_duration_seconds_bucket[5m])) by (endpoint)' | jq
```

### Step 2: Identify Scope (3 minutes)

**Questions to Answer**:
- Is latency high for all endpoints or specific ones?
- Is it affecting all users or specific regions?
- When did it start? (correlate with deployments)
- Is error rate also elevated?

```bash
# Check by endpoint
kubectl logs -l app=api-server --tail=100 -n production | grep "duration_ms" | sort -k3 -n | tail -20

# Check by region (if multi-region)
curl -s 'http://localhost:9090/api/v1/query?query=histogram_quantile(0.99,rate(http_request_duration_seconds_bucket[5m])) by (region)' | jq

# Timeline: when did spike start?
# Check Grafana for correlation with deployments
```

### Step 3: Quick Wins (5 minutes)

Before deep investigation, try these quick fixes:

**A. Check for Resource Exhaustion**

```bash
# CPU usage
kubectl top pods -n production | grep api-server

# Memory usage
kubectl top pods -n production | grep api-server

# If CPU >80% or Memory >80%, scale up immediately
kubectl scale deployment/api-server --replicas=10 -n production
```

**B. Check Database Performance**

```bash
# PostgreSQL slow queries
docker exec postgres psql -U ai_user -d ai_platform -c "
  SELECT pid, now() - query_start as duration, query 
  FROM pg_stat_activity 
  WHERE state = 'active' AND now() - query_start > interval '5 seconds'
  ORDER BY duration DESC;
"

# Qdrant performance
curl http://localhost:6333/metrics | grep qdrant_request_duration

# Neo4j slow queries
docker exec neo4j cypher-shell -u neo4j -p neo4j_password "
  CALL dbms.listQueries() 
  YIELD queryId, query, elapsedTimeMillis 
  WHERE elapsedTimeMillis > 5000 
  RETURN queryId, query, elapsedTimeMillis;
"
```

**C. Check External Dependencies**

```bash
# Check external API latency (if applicable)
curl -w "\nTime: %{time_total}s\n" -o /dev/null -s http://external-api.example.com/health

# Check DNS resolution time
time nslookup qdrant
time nslookup postgres
```

---

## Investigation Steps

### Phase 1: Application Layer

#### 1.1 Analyze Request Traces

```bash
# Get slow request samples
kubectl logs -l app=api-server --tail=1000 -n production | \
  grep "duration_ms" | \
  awk '$NF > 1000 {print}' | \
  head -20

# Look for patterns
# - Same endpoint?
# - Same user?
# - Specific request parameters?
```

#### 1.2 Check Thread/Worker Saturation

```bash
# Check if workers are saturated
curl http://localhost:8000/metrics | grep "worker_busy_count"
curl http://localhost:8000/metrics | grep "worker_idle_count"

# Check request queue depth
curl http://localhost:8000/metrics | grep "request_queue_depth"

# If queue depth >100 or workers saturated, need more workers
```

#### 1.3 Profile Application Code

```bash
# Enable profiling (if not already enabled)
curl -X POST http://localhost:8000/admin/profiling/enable

# Collect profile for 30 seconds
curl -X POST http://localhost:8000/admin/profiling/start \
  -H "Content-Type: application/json" \
  -d '{"duration_seconds": 30}'

# Download profile
curl http://localhost:8000/admin/profiling/download > /tmp/profile.prof

# Analyze with py-spy or similar
py-spy top --pid $(pgrep -f api_server.py) --duration 30
```

#### 1.4 Check for Code-Level Issues

**Common Issues**:
- Blocking I/O in async code
- N+1 query problems
- Missing database indexes
- Large response payloads
- Inefficient serialization

```bash
# Check for blocking operations in logs
kubectl logs -l app=api-server --tail=500 -n production | grep -i "blocking\|sync\|wait"

# Check response size
kubectl logs -l app=api-server --tail=100 -n production | \
  grep "response_size" | \
  awk '{sum+=$NF; count++} END {print "Avg response size:", sum/count, "bytes"}'
```

---

### Phase 2: Database Layer

#### 2.1 PostgreSQL Investigation

```bash
# Check active connections
docker exec postgres psql -U ai_user -d ai_platform -c "
  SELECT count(*), state 
  FROM pg_stat_activity 
  GROUP BY state;
"

# Check for locks
docker exec postgres psql -U ai_user -d ai_platform -c "
  SELECT pid, usename, pg_blocking_pids(pid) as blocked_by, query 
  FROM pg_stat_activity 
  WHERE cardinality(pg_blocking_pids(pid)) > 0;
"

# Check table bloat
docker exec postgres psql -U ai_user -d ai_platform -c "
  SELECT schemaname, tablename, 
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
  FROM pg_tables 
  ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC 
  LIMIT 10;
"

# Check for missing indexes (slow queries)
docker exec postgres psql -U ai_user -d ai_platform -c "
  SELECT schemaname, tablename, attname, n_distinct, correlation
  FROM pg_stats
  WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
  ORDER BY abs(correlation) DESC
  LIMIT 20;
"

# Analyze slow queries (requires pg_stat_statements)
docker exec postgres psql -U ai_user -d ai_platform -c "
  SELECT query, calls, total_exec_time, mean_exec_time, max_exec_time
  FROM pg_stat_statements
  ORDER BY mean_exec_time DESC
  LIMIT 10;
"
```

**Solutions for PostgreSQL Issues**:

```bash
# Kill long-running query
docker exec postgres psql -U ai_user -d ai_platform -c "SELECT pg_terminate_backend(<pid>);"

# Add missing index
docker exec postgres psql -U ai_user -d ai_platform -c "
  CREATE INDEX CONCURRENTLY idx_users_email ON users(email);
"

# Vacuum bloated table
docker exec postgres psql -U ai_user -d ai_platform -c "VACUUM ANALYZE users;"

# Increase connection pool (if exhausted)
kubectl set env deployment/api-server DB_POOL_SIZE=100 -n production
```

#### 2.2 Qdrant Investigation

```bash
# Check Qdrant metrics
curl http://localhost:6333/metrics

# Check collection size and search performance
curl http://localhost:6333/collections | jq

# Check specific collection stats
curl http://localhost:6333/collections/documents | jq

# Test search latency
time curl -X POST http://localhost:6333/collections/documents/points/search \
  -H "Content-Type: application/json" \
  -d '{
    "vector": [0.1, 0.2, 0.3, ...],
    "limit": 10
  }'

# Check if HNSW index needs optimization
curl http://localhost:6333/collections/documents | jq '.result.config.hnsw_config'
```

**Solutions for Qdrant Issues**:

```bash
# Optimize HNSW index
curl -X POST http://localhost:6333/collections/documents/index \
  -H "Content-Type: application/json" \
  -d '{"action": "optimize"}'

# Increase HNSW ef parameter for better accuracy (but slower)
curl -X PATCH http://localhost:6333/collections/documents \
  -H "Content-Type: application/json" \
  -d '{
    "hnsw_config": {
      "ef_construct": 200,
      "m": 32
    }
  }'

# Scale Qdrant if needed
kubectl scale statefulset/qdrant --replicas=3 -n production
```

#### 2.3 Neo4j Investigation

```bash
# Check slow queries
docker exec neo4j cypher-shell -u neo4j -p neo4j_password "
  CALL dbms.listQueries() 
  YIELD queryId, query, elapsedTimeMillis, allocatedBytes
  WHERE elapsedTimeMillis > 1000
  RETURN queryId, query, elapsedTimeMillis, allocatedBytes;
"

# Check for missing indexes
docker exec neo4j cypher-shell -u neo4j -p neo4j_password "SHOW INDEXES;"

# Check cache hit rates
docker exec neo4j cypher-shell -u neo4j -p neo4j_password "
  CALL dbms.queryJmx('org.neo4j:*') 
  YIELD name, attributes
  WHERE name CONTAINS 'PageCache'
  RETURN name, attributes;
"
```

**Solutions for Neo4j Issues**:

```bash
# Kill slow query
docker exec neo4j cypher-shell -u neo4j -p neo4j_password "CALL dbms.killQuery('<queryId>');"

# Add missing index
docker exec neo4j cypher-shell -u neo4j -p neo4j_password "
  CREATE INDEX user_email IF NOT EXISTS FOR (u:User) ON (u.email);
"

# Warm up cache (after restart)
docker exec neo4j cypher-shell -u neo4j -p neo4j_password "
  MATCH (n) RETURN count(n);
"
```

---

### Phase 3: Infrastructure Layer

#### 3.1 CPU and Memory

```bash
# Check pod resource usage
kubectl top pods -n production --sort-by=cpu
kubectl top pods -n production --sort-by=memory

# Check node resource usage
kubectl top nodes

# Check for CPU throttling
kubectl describe pod <pod-name> -n production | grep -A 10 "Resource Limits"

# Check for OOM kills
kubectl get events -n production | grep OOM

# Check for context switches (high = CPU contention)
docker stats --no-stream | head -20
```

**Solutions**:

```bash
# Increase resource limits
kubectl set resources deployment/api-server \
  --limits=cpu=2000m,memory=4Gi \
  --requests=cpu=1000m,memory=2Gi \
  -n production

# Scale horizontally
kubectl scale deployment/api-server --replicas=10 -n production

# Add nodes to cluster (if cluster-level resource exhaustion)
# Cloud-specific commands
```

#### 3.2 Network Latency

```bash
# Check network latency between pods
kubectl exec -it deployment/api-server -n production -- ping postgres
kubectl exec -it deployment/api-server -n production -- ping qdrant

# Check DNS resolution time
kubectl exec -it deployment/api-server -n production -- time nslookup qdrant

# Check service mesh latency (if using Istio/Linkerd)
kubectl logs -l app=istio-proxy --tail=100 -n production | grep latency
```

**Solutions**:

```bash
# If DNS slow, use IP addresses or adjust DNS config
# If inter-pod latency high, check CNI plugin configuration
# If external dependency slow, add caching layer
```

#### 3.3 Disk I/O

```bash
# Check disk I/O wait
kubectl exec -it deployment/api-server -n production -- iostat -x 1 5

# Check for slow volumes
kubectl describe pvc -n production

# Check database disk performance
docker exec postgres df -h
docker exec postgres iostat -x 1 5
```

---

### Phase 4: Dependency Analysis

#### 4.1 Circuit Breaker Status

```bash
# Check circuit breaker status
curl http://localhost:8000/metrics | grep circuit_breaker

# Check which services have open circuit breakers
curl http://localhost:8000/admin/circuit-breaker/status | jq

# If circuit breaker open, investigate dependent service
```

#### 4.2 External API Latency

```bash
# Test external API directly
for i in {1..10}; do
  curl -w "Time: %{time_total}s\n" -o /dev/null -s http://external-api.example.com/health
  sleep 1
done

# Check application logs for external API calls
kubectl logs -l app=api-server --tail=500 -n production | grep "external_api" | grep "duration"
```

#### 4.3 Rate Limiting

```bash
# Check if hitting rate limits
kubectl logs -l app=api-server --tail=500 -n production | grep -i "rate.limit\|429"

# Check Kong/Gateway rate limit metrics
curl http://localhost:8001/metrics | grep rate_limit
```

---

## Common Causes and Solutions

### 1. Database Connection Pool Exhaustion

**Symptoms**:
- Latency spikes during peak traffic
- "connection pool exhausted" errors
- Increasing wait time for connections

**Solution**:
```bash
# Increase connection pool size
kubectl set env deployment/api-server \
  DB_POOL_SIZE=100 \
  DB_POOL_TIMEOUT=30 \
  -n production

# Monitor pool usage
curl http://localhost:8000/metrics | grep db_pool
```

---

### 2. Missing Database Index

**Symptoms**:
- Queries get slower as data grows
- High CPU on database
- Full table scans in query plans

**Solution**:
```bash
# Identify missing index
docker exec postgres psql -U ai_user -d ai_platform -c "
  EXPLAIN ANALYZE SELECT * FROM users WHERE email = 'test@example.com';
"

# Create index
docker exec postgres psql -U ai_user -d ai_platform -c "
  CREATE INDEX CONCURRENTLY idx_users_email ON users(email);
"
```

---

### 3. Memory Pressure / GC Pauses

**Symptoms**:
- Periodic latency spikes
- Sawtooth memory usage pattern
- GC logs showing long pause times

**Solution**:
```bash
# Increase memory allocation
kubectl set resources deployment/api-server \
  --limits=memory=4Gi \
  --requests=memory=2Gi \
  -n production

# Tune GC (Python)
kubectl set env deployment/api-server \
  PYTHONMALLOC=malloc \
  MALLOC_TRIM_THRESHOLD_=65536 \
  -n production
```

---

### 4. N+1 Query Problem

**Symptoms**:
- Latency increases with result set size
- Many small queries instead of few large ones
- Database connection count spikes

**Solution**:
```python
# Bad: N+1 queries
users = db.query(User).all()
for user in users:
    user.posts = db.query(Post).filter(Post.user_id == user.id).all()

# Good: Single query with join
users = db.query(User).options(joinedload(User.posts)).all()
```

---

### 5. Blocking I/O in Async Code

**Symptoms**:
- Entire service becomes unresponsive
- Thread pool exhaustion
- Worker processes stuck

**Solution**:
```python
# Bad: Blocking I/O in async function
async def get_data():
    result = requests.get('http://api.example.com')  # Blocks!
    return result.json()

# Good: Async HTTP client
async def get_data():
    async with httpx.AsyncClient() as client:
        result = await client.get('http://api.example.com')
        return result.json()
```

---

### 6. Large Payload Serialization

**Symptoms**:
- Latency correlates with response size
- High CPU during serialization
- Memory spikes

**Solution**:
```bash
# Enable response compression
kubectl set env deployment/api-server \
  ENABLE_GZIP=true \
  -n production

# Implement pagination
# Limit max response size
# Use streaming for large responses
```

---

### 7. Cold Start / Cache Miss

**Symptoms**:
- First request slow, subsequent requests fast
- Latency spike after deployments
- Latency spike after cache eviction

**Solution**:
```bash
# Pre-warm cache after deployment
curl http://localhost:8000/admin/cache/warmup

# Increase cache size
kubectl set env deployment/api-server \
  CACHE_SIZE_MB=512 \
  -n production

# Implement cache preloading in startup script
```

---

## Mitigation Strategies

### Immediate Actions (< 5 minutes)

1. **Scale Up**
   ```bash
   kubectl scale deployment/api-server --replicas=10 -n production
   ```

2. **Increase Timeouts** (temporary)
   ```bash
   kubectl set env deployment/api-server REQUEST_TIMEOUT=60 -n production
   ```

3. **Enable Caching** (if not already enabled)
   ```bash
   curl -X POST http://localhost:8000/admin/cache/enable
   ```

4. **Rate Limit Aggressive Clients**
   ```bash
   # Identify top clients
   kubectl logs -l app=api-server --tail=1000 -n production | \
     grep "client_ip" | \
     awk '{print $5}' | \
     sort | uniq -c | sort -rn | head -10
   
   # Add rate limit
   curl -X POST http://localhost:8001/admin/rate-limits \
     -H "Content-Type: application/json" \
     -d '{"client_ip": "1.2.3.4", "limit": "100/min"}'
   ```

### Short-term Fixes (< 1 hour)

1. **Optimize Slow Queries**
2. **Add Missing Indexes**
3. **Increase Resource Limits**
4. **Enable Read Replicas** (if available)
5. **Implement Circuit Breakers** (for external dependencies)

### Long-term Solutions

1. **Implement Caching Strategy**
2. **Database Query Optimization**
3. **Code Profiling and Optimization**
4. **Asynchronous Processing** (for slow operations)
5. **Content Delivery Network** (for static assets)
6. **Auto-scaling Policies**

---

## Prevention

### Monitoring and Alerting

```yaml
# Prometheus alert rules
- alert: LatencyHigh
  expr: histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m])) > 1.5
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "High latency detected"
    description: "P99 latency is {{ $value }}s"

- alert: LatencyCritical
  expr: histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m])) > 3.0
  for: 2m
  labels:
    severity: critical
  annotations:
    summary: "Critical latency spike"
    description: "P99 latency is {{ $value }}s"
```

### Load Testing

```bash
# Regular load tests to establish baselines
k6 run --vus 100 --duration 300s k6_load_test.js

# Stress testing before major releases
locust -f locust_load_test.py --users 1000 --spawn-rate 50
```

### Performance Budgets

- P50 latency < 200ms
- P95 latency < 500ms
- P99 latency < 1s
- Database query time < 100ms
- External API calls < 500ms

### Code Review Checklist

- [ ] No blocking I/O in async code
- [ ] Database queries use indexes
- [ ] Pagination implemented for large result sets
- [ ] Response size limited
- [ ] Caching strategy defined
- [ ] Timeouts configured for all external calls
- [ ] Load tested under expected peak traffic

---

## Appendix: Useful Commands

### Quick Metrics Check

```bash
# One-liner for current P99 latency
curl -s 'http://localhost:9090/api/v1/query?query=histogram_quantile(0.99,rate(http_request_duration_seconds_bucket[5m]))' | jq -r '.data.result[0].value[1]'

# Monitor latency in real-time
watch -n 5 "curl -s 'http://localhost:9090/api/v1/query?query=histogram_quantile(0.99,rate(http_request_duration_seconds_bucket[5m]))' | jq -r '.data.result[0].value[1]'"
```

### Log Analysis

```bash
# Find slowest requests
kubectl logs -l app=api-server --tail=5000 -n production | \
  grep "duration_ms" | \
  awk '{print $NF}' | \
  sort -n | \
  tail -20

# Average request duration
kubectl logs -l app=api-server --tail=1000 -n production | \
  grep "duration_ms" | \
  awk '{sum+=$NF; count++} END {print "Avg:", sum/count, "ms"}'
```

---

**Version**: 1.0  
**Last Updated**: 2025-01-30  
**Next Review**: 2025-02-28  
**Owner**: SRE Team
