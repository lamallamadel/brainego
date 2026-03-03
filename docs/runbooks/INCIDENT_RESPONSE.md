# Incident Response Runbook

## Table of Contents
1. [Overview](#overview)
2. [Escalation Matrix](#escalation-matrix)
3. [Severity Definitions](#severity-definitions)
4. [Triage Procedure (10-Minute Loop)](#triage-procedure-10-minute-loop)
5. [Common Incident Patterns](#common-incident-patterns)
6. [Diagnostic Commands](#diagnostic-commands)
7. [On-Call Procedures](#on-call-procedures)
8. [Communication Protocols](#communication-protocols)
9. [Post-Incident Review](#post-incident-review)
10. [Tools and Resources](#tools-and-resources)

---

## Overview

This runbook defines the incident response process for the AI Platform. It covers escalation procedures, on-call responsibilities, incident management, and post-incident review processes.

### Response Objectives

- **Detection**: < 5 minutes
- **Acknowledgment**: < 10 minutes
- **Initial Response**: < 15 minutes
- **Triage Loop**: 10 minutes per cycle (symptom → check → mitigation)
- **Resolution Target (P0)**: < 1 hour
- **Resolution Target (P1)**: < 2 hours
- **Resolution Target (P2)**: < 4 hours

---

## Escalation Matrix

### P0 - Critical (Emergency)

**Definition**: Complete system outage or data loss

**Severity Criteria**:
- All users cannot access the system
- Data loss or corruption occurring
- Security breach actively happening
- Revenue loss > $10k/hour
- Multi-region total outage

**Response Requirements**:
- Immediate response (acknowledge < 5 minutes)
- Escalate to Level 3 immediately
- Update every 15 minutes
- All hands on deck

**Escalation Path**:
1. **Level 1 (0-5 min)**: On-Call SRE
2. **Level 2 (5 min)**: Senior SRE + Database Administrator
3. **Level 3 (Immediate)**: Platform Architect + Engineering Manager
4. **External**: CEO/CTO (if > 2 hour outage or regulatory impact)

**Contact Methods**:
- PagerDuty: Critical escalation
- Phone: Direct call (see on-call rotation)
- Slack: #executive-incidents

---

### P1 - High (Urgent)

**Definition**: Major functionality unavailable or severely degraded

**Severity Criteria**:
- Core features unavailable
- Impacts majority of users
- SLA breach imminent
- Error rate > 5%
- Workaround not available

**Response Requirements**:
- Response within 10 minutes
- Escalate to Level 2 if not resolved in 30 minutes
- Update every 30 minutes

**Escalation Path**:
1. **Level 1 (0-10 min)**: On-Call SRE
2. **Level 2 (30 min)**: Senior SRE
3. **Level 3 (1 hour)**: Engineering Manager (if not resolved)

**Contact Methods**:
- PagerDuty: High priority
- Slack: #sre-escalation
- Phone: (if no response after 15 minutes)

---

### P2 - Medium (Important)

**Definition**: Partial functionality impacted or performance degraded

**Severity Criteria**:
- Non-critical features unavailable
- Performance degradation noticeable
- Impacts subset of users
- Workaround available
- Memory usage > 85%
- P99 latency > 2s

**Response Requirements**:
- Response within 20 minutes
- Update every hour
- Can be resolved during business hours

**Escalation Path**:
1. **Level 1 (0-20 min)**: On-Call SRE
2. **Level 2 (2 hours)**: Senior SRE (if needed)

**Contact Methods**:
- PagerDuty: Normal priority
- Slack: #sre-oncall

---

## Severity Definitions

### Quick Severity Decision Tree

```
Is the system completely down? → P0
↓ No
Are core features failing for most users? → P1
↓ No
Are some features degraded or slow? → P2
↓ No
Minor issues, no user impact → P3
```

### P3 - Low (Planned Work)

**Definition**: Minor issues with minimal user impact

**Criteria**: Cosmetic issues, affects very few users, workarounds exist, no SLA impact

**Response**: Within 4 hours, update daily

---

## Triage Procedure (10-Minute Loop)

This procedure is designed to be repeated every 10 minutes until the incident is resolved. Each cycle focuses on: **symptom → check → mitigation**.

### Cycle 1 (Minutes 0-10): Initial Triage

**Minutes 0-2: Acknowledge & Gather Context**

```bash
# 1. Acknowledge alert
# PagerDuty: Click "Acknowledge"

# 2. Check Grafana SRE Incident Response dashboard
# URL: http://localhost:3000/d/sre-incident-response

# 3. Check Alertmanager for firing alerts
# URL: http://localhost:9093

# 4. Quick system health check
docker compose ps
# or
kubectl get pods --all-namespaces
```

**Minutes 2-5: Identify Affected Systems**

```bash
# Check which services are unhealthy
docker compose ps | grep -v "Up"

# Check recent errors
docker compose logs --tail=50 --since=10m | grep -i error

# Check Prometheus for high-level metrics
curl -s 'http://localhost:9090/api/v1/query?query=up{job="api-server"}' | jq '.data.result[0].value[1]'
curl -s 'http://localhost:9090/api/v1/query?query=rate(http_requests_total{status=~"5.."}[5m])' | jq
```

**Minutes 5-8: Determine Severity & Escalate if Needed**

- Use severity decision tree above
- Create incident in #incidents Slack channel
- Escalate immediately if P0, after 30 min if P1 not progressing

**Minutes 8-10: Initial Mitigation Attempt**

```bash
# If service is unhealthy, restart
docker compose restart <service_name>

# If resource exhaustion, scale up
kubectl scale deployment/<name> --replicas=5 -n production
```

---

### Cycle 2+ (Every 10 Minutes): Deep Investigation & Mitigation

**Minutes 0-3: Check Mitigation Status**

```bash
# Did the mitigation work?
docker compose ps | grep <service_name>

# Check error rate
curl -s 'http://localhost:9090/api/v1/query?query=rate(http_requests_total{status=~"5.."}[5m])' | jq

# Check latency
curl -s 'http://localhost:9090/api/v1/query?query=histogram_quantile(0.99,rate(http_request_duration_seconds_bucket[5m]))' | jq
```

**Minutes 3-7: Deep Dive Based on Pattern**

Refer to [Common Incident Patterns](#common-incident-patterns) section below.

**Minutes 7-10: Apply Next Mitigation & Update Stakeholders**

- Apply specific fix based on root cause
- Update #incidents Slack channel with findings
- If not resolved, prepare for next cycle

---

### Cycle Exit Criteria

Stop the 10-minute loop when:
1. ✅ All alerts cleared
2. ✅ Error rates back to baseline
3. ✅ Latency within SLA
4. ✅ No service restarts for 15 minutes
5. ✅ Health checks passing

Then proceed to **Post-Incident Review**.

---

## Common Incident Patterns

### Pattern 1: High Latency

**Symptoms**:
- P99 latency > 2s
- Alert: `HighLatency` or `LatencySpike`
- User complaints about slow responses

**10-Minute Check**:

```bash
# Check current P99 latency
curl -s 'http://localhost:9090/api/v1/query?query=histogram_quantile(0.99,rate(http_request_duration_seconds_bucket[5m]))' | jq -r '.data.result[0].value[1]'

# Check by endpoint
curl -s 'http://localhost:9090/api/v1/query?query=histogram_quantile(0.99,rate(http_request_duration_seconds_bucket[5m])) by (endpoint)' | jq

# Check resource usage
docker stats --no-stream | head -10

# Check database slow queries
docker exec postgres psql -U ai_user -d ai_platform -c "
  SELECT pid, now() - query_start as duration, query 
  FROM pg_stat_activity 
  WHERE state = 'active' AND now() - query_start > interval '5 seconds'
  ORDER BY duration DESC LIMIT 5;
"
```

**Immediate Mitigation**:

```bash
# Scale up if CPU > 80%
kubectl scale deployment/api-server --replicas=10 -n production

# Increase resource limits if needed
kubectl set resources deployment/api-server \
  --limits=cpu=2000m,memory=4Gi \
  -n production

# Check for slow database queries and kill if needed
docker exec postgres psql -U ai_user -d ai_platform -c "SELECT pg_terminate_backend(<pid>);"
```

**Full Runbook**: [DEBUG_LATENCY_SPIKE.md](./DEBUG_LATENCY_SPIKE.md)

---

### Pattern 2: 5xx Spike

**Symptoms**:
- Error rate > 5%
- Alert: `High5xxRate`
- HTTP 500, 502, 503, or 504 responses

**10-Minute Check**:

```bash
# Check error rate by service
curl -s 'http://localhost:9090/api/v1/query?query=sum by (job, instance) (rate(http_requests_total{status=~"5.."}[5m]))' | jq

# Check specific status codes
curl -s 'http://localhost:9090/api/v1/query?query=sum by (status) (rate(http_requests_total{status=~"5.."}[5m]))' | jq

# Check service logs for errors
docker compose logs --tail=100 api-server | grep -E "500|502|503|504|ERROR|Exception"

# Check backend connectivity
docker exec postgres psql -U ai_user -d ai_platform -c "SELECT 1"
curl http://localhost:6333/health  # Qdrant
curl http://localhost:7474/  # Neo4j
```

**Immediate Mitigation**:

```bash
# If application bug (500), rollback
kubectl rollout undo deployment/api-server -n production
# or
./scripts/deploy/deploy_vm.sh rollback previous

# If backend failure (502/503), restart service
docker compose restart api-server

# If connection pool exhaustion, increase pool size
kubectl set env deployment/api-server DB_POOL_SIZE=100 -n production

# If overload (503), scale up
kubectl scale deployment/api-server --replicas=5 -n production
```

**Full Runbook**: [PILOT_HIGH_5XX_RATE.md](./PILOT_HIGH_5XX_RATE.md)

---

### Pattern 3: Out of Memory (OOM)

**Symptoms**:
- Alert: `MemoryPressureDetected`
- Memory usage > 90%
- Container restarts due to OOM kill

**10-Minute Check**:

```bash
# Check memory usage
docker stats --no-stream | awk 'NR==1 || $7 > 80' 

# Check for OOM kills
docker compose logs | grep -i oom
kubectl describe pod <pod_name> -n production | grep -i oom

# Check memory trend
curl -s 'http://localhost:9090/api/v1/query?query=container_memory_working_set_bytes{name!=""} / container_spec_memory_limit_bytes{name!=""} > 0.8' | jq

# Check for memory leak (growing over time)
curl -s 'http://localhost:9090/api/v1/query?query=(container_memory_working_set_bytes{name!=""} - container_memory_working_set_bytes{name!=""} offset 1h)' | jq
```

**Immediate Mitigation**:

```bash
# Increase memory limit
kubectl set resources deployment/api-server \
  --limits=memory=4Gi \
  --requests=memory=2Gi \
  -n production

# Scale horizontally to distribute load
kubectl scale deployment/api-server --replicas=5 -n production

# Restart container if memory leak suspected
docker compose restart api-server

# Clear caches to free memory
curl -X POST http://localhost:8000/admin/cache/clear
```

**Full Runbook**: [PILOT_MEMORY_PRESSURE.md](./PILOT_MEMORY_PRESSURE.md)

---

### Pattern 4: Drift Alert

**Symptoms**:
- Alert: `DriftDetected` (drift_score > 0.15)
- Model performance degradation
- Prediction accuracy drop

**10-Minute Check**:

```bash
# Check drift score
curl -s 'http://localhost:9090/api/v1/query?query=drift_score' | jq

# Check drift details
curl http://drift-monitor:8004/api/drift/current | jq

# Check feature-level drift
curl http://drift-monitor:8004/api/drift/features | jq '.[] | select(.drift_score > 0.15)'

# Check evaluation score
curl -s 'http://localhost:9090/api/v1/query?query=drift_current_accuracy' | jq
```

**Immediate Mitigation**:

```bash
# If severe performance drop, enable fallback model
curl -X POST http://api-server:8000/admin/model/fallback \
  -H "Content-Type: application/json" \
  -d '{"enabled": true, "reason": "concept_drift"}'

# Trigger retraining
curl -X POST http://learning-engine:8003/api/finetune/trigger \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama-3.3-8b",
    "trigger_type": "drift_detected",
    "priority": "high"
  }'

# Check data quality for issues
curl http://drift-monitor:8004/api/drift/data-quality | jq
```

**Full Runbook**: [PILOT_DRIFT_DETECTED.md](./PILOT_DRIFT_DETECTED.md)

---

### Pattern 5: Rate Limit Exceeded

**Symptoms**:
- Alert: `KongRateLimitExceeded`
- HTTP 429 responses increasing
- Kong rejecting requests

**10-Minute Check**:

```bash
# Check 429 rate by consumer
curl -s 'http://localhost:9090/api/v1/query?query=sum by (route, consumer) (rate(kong_http_requests_total{code="429"}[5m]))' | jq

# Check Kong logs for affected consumers
kubectl logs -l app=kong --tail=100 | grep "429"

# Check rate limit configuration
curl http://kong-admin:8001/routes/{route_id}/plugins | jq '.[] | select(.name == "rate-limiting")'

# Analyze traffic pattern
curl -s 'http://localhost:9090/api/v1/query?query=sum by (consumer) (rate(kong_http_requests_total[5m]))' | jq
```

**Immediate Mitigation**:

```bash
# If legitimate traffic, increase limit
curl -X PATCH http://kong-admin:8001/plugins/{plugin_id} \
  -H "Content-Type: application/json" \
  -d '{"config": {"minute": 200, "hour": 10000}}'

# If abuse, block consumer
curl -X PATCH http://kong-admin:8001/consumers/{consumer_id} \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'

# Or revoke API key
curl -X DELETE http://kong-admin:8001/consumers/{consumer_id}/key-auth/{key_id}
```

**Full Runbook**: [PILOT_KONG_RATE_LIMIT.md](./PILOT_KONG_RATE_LIMIT.md)

---

## Diagnostic Commands

### Docker Compose Commands

**Service Status**:

```bash
# Check all services
docker compose ps

# Check specific service
docker compose ps api-server

# Check service health
docker compose ps --filter "health=unhealthy"
```

**Logs**:

```bash
# Last 100 lines of all services
docker compose logs --tail=100

# Follow logs for specific service
docker compose logs -f api-server

# Last 10 minutes of errors
docker compose logs --since=10m | grep -i error

# Save logs for analysis
docker compose logs --tail=1000 api-server > api-server.log
```

**Restart/Scale**:

```bash
# Restart single service
docker compose restart api-server

# Restart all services
docker compose restart

# Scale service (requires compose file support)
docker compose up -d --scale api-server=3
```

**Resource Usage**:

```bash
# Real-time stats
docker stats

# Single snapshot
docker stats --no-stream

# Specific service
docker stats api-server --no-stream
```

---

### Deployment Script Commands

**Check Deployment Status**:

```bash
# Show current deployment
./scripts/deploy/deploy_vm.sh status

# Output:
# - Current version (git SHA)
# - Previous version
# - Available releases
# - Running services
# - Recent downtime log
# - Recent rollback log
```

**Rollback**:

```bash
# Rollback to previous version
./scripts/deploy/deploy_vm.sh rollback previous

# Rollback to specific version
./scripts/deploy/deploy_vm.sh rollback abc123f

# Check rollback history
cat /opt/brainego/logs/rollback.log | tail -10
```

**View Logs**:

```bash
# All services
./scripts/deploy/deploy_vm.sh logs

# Specific service, last 50 lines
./scripts/deploy/deploy_vm.sh logs api-server 50

# Deployment log
tail -f /opt/brainego/logs/deployment.log

# Downtime log (CSV: timestamp, action, duration)
cat /opt/brainego/logs/downtime.log
```

---

### Prometheus Query Commands

**Error Rate**:

```bash
# Current 5xx error rate
curl -s 'http://localhost:9090/api/v1/query?query=rate(http_requests_total{status=~"5.."}[5m])' | jq '.data.result[0].value[1]'

# Error rate by service
curl -s 'http://localhost:9090/api/v1/query?query=sum by (job) (rate(http_requests_total{status=~"5.."}[5m]))' | jq

# Error rate by endpoint
curl -s 'http://localhost:9090/api/v1/query?query=sum by (path) (rate(http_requests_total{status=~"5.."}[5m]))' | jq
```

**Latency**:

```bash
# Current P99 latency
curl -s 'http://localhost:9090/api/v1/query?query=histogram_quantile(0.99,rate(http_request_duration_seconds_bucket[5m]))' | jq -r '.data.result[0].value[1]'

# P95 latency
curl -s 'http://localhost:9090/api/v1/query?query=histogram_quantile(0.95,rate(http_request_duration_seconds_bucket[5m]))' | jq -r '.data.result[0].value[1]'

# P50 latency
curl -s 'http://localhost:9090/api/v1/query?query=histogram_quantile(0.50,rate(http_request_duration_seconds_bucket[5m]))' | jq -r '.data.result[0].value[1]'

# Latency by endpoint
curl -s 'http://localhost:9090/api/v1/query?query=histogram_quantile(0.99,rate(http_request_duration_seconds_bucket[5m])) by (endpoint)' | jq
```

**Resource Usage**:

```bash
# Memory usage
curl -s 'http://localhost:9090/api/v1/query?query=container_memory_working_set_bytes' | jq

# Memory percentage
curl -s 'http://localhost:9090/api/v1/query?query=container_memory_working_set_bytes{name!=""} / container_spec_memory_limit_bytes{name!=""} * 100' | jq

# CPU usage
curl -s 'http://localhost:9090/api/v1/query?query=rate(container_cpu_usage_seconds_total[5m])' | jq

# Disk I/O
curl -s 'http://localhost:9090/api/v1/query?query=rate(container_fs_writes_bytes_total[5m])' | jq
```

**Service Health**:

```bash
# Service up/down status
curl -s 'http://localhost:9090/api/v1/query?query=up' | jq

# Services that are down
curl -s 'http://localhost:9090/api/v1/query?query=up==0' | jq

# Request rate
curl -s 'http://localhost:9090/api/v1/query?query=rate(http_requests_total[5m])' | jq

# Concurrent requests
curl -s 'http://localhost:9090/api/v1/query?query=http_requests_in_flight' | jq
```

**Custom Metrics**:

```bash
# Drift score
curl -s 'http://localhost:9090/api/v1/query?query=drift_score' | jq

# Circuit breaker status
curl -s 'http://localhost:9090/api/v1/query?query=circuit_breaker_state' | jq

# Database connection pool
curl -s 'http://localhost:9090/api/v1/query?query=db_pool_active_connections' | jq

# Kong rate limit metrics
curl -s 'http://localhost:9090/api/v1/query?query=sum by (consumer) (rate(kong_http_requests_total{code="429"}[5m]))' | jq
```

---

### Database Diagnostic Commands

**PostgreSQL**:

```bash
# Health check
docker exec postgres psql -U ai_user -d ai_platform -c "SELECT 1"

# Active connections
docker exec postgres psql -U ai_user -d ai_platform -c "
  SELECT count(*), state FROM pg_stat_activity GROUP BY state;
"

# Slow queries
docker exec postgres psql -U ai_user -d ai_platform -c "
  SELECT pid, now() - query_start as duration, query 
  FROM pg_stat_activity 
  WHERE state = 'active' AND now() - query_start > interval '5 seconds'
  ORDER BY duration DESC;
"

# Lock detection
docker exec postgres psql -U ai_user -d ai_platform -c "
  SELECT pid, usename, pg_blocking_pids(pid) as blocked_by, query 
  FROM pg_stat_activity 
  WHERE cardinality(pg_blocking_pids(pid)) > 0;
"

# Kill slow query
docker exec postgres psql -U ai_user -d ai_platform -c "SELECT pg_terminate_backend(<pid>);"
```

**Qdrant (Vector Database)**:

```bash
# Health check
curl http://localhost:6333/health

# Collections info
curl http://localhost:6333/collections | jq

# Specific collection stats
curl http://localhost:6333/collections/documents | jq

# Metrics
curl http://localhost:6333/metrics | grep qdrant_request_duration
```

**Neo4j (Graph Database)**:

```bash
# Health check
curl http://localhost:7474/

# Active queries
docker exec neo4j cypher-shell -u neo4j -p neo4j_password "
  CALL dbms.listQueries() 
  YIELD queryId, query, elapsedTimeMillis 
  WHERE elapsedTimeMillis > 5000
  RETURN queryId, query, elapsedTimeMillis;
"

# Kill slow query
docker exec neo4j cypher-shell -u neo4j -p neo4j_password "CALL dbms.killQuery('<queryId>');"

# Show indexes
docker exec neo4j cypher-shell -u neo4j -p neo4j_password "SHOW INDEXES;"
```

---

## On-Call Procedures

### On-Call Rotation Schedule

**Structure**:
- Primary: 7-day rotation, Monday 9:00 AM handoff
- Secondary: Backup coverage, 7-day rotation
- Overlap: 30-minute handoff meeting

**Rotation Placeholder**:

```
Week of 2025-02-03:
  Primary: [SRE Name]
  Secondary: [Backup SRE Name]
  Phone: [Rotation Phone Number]

Week of 2025-02-10:
  Primary: [SRE Name]
  Secondary: [Backup SRE Name]
  Phone: [Rotation Phone Number]

[Update this section with actual rotation schedule]
```

### Handoff Checklist

```
[ ] Review open incidents from previous week
[ ] Review upcoming maintenance windows
[ ] Verify PagerDuty configuration
[ ] Test alert notification (phone, SMS, push)
[ ] Review recent changes and deployments
[ ] Check monitoring dashboard health (Grafana/Prometheus)
[ ] Ensure VPN and access credentials work
[ ] Review any known issues or watch items
[ ] Verify access to:
    [ ] Production environment (SSH, kubectl)
    [ ] Grafana (http://localhost:3000)
    [ ] Prometheus (http://localhost:9090)
    [ ] Kong Admin (http://localhost:8001)
    [ ] Database credentials
```

### Response Time Requirements

| Severity | Acknowledgment | Initial Response | Updates      |
|----------|----------------|------------------|--------------|
| P0       | 5 minutes      | 10 minutes       | Every 15 min |
| P1       | 10 minutes     | 15 minutes       | Every 30 min |
| P2       | 20 minutes     | 30 minutes       | Every 1 hour |
| P3       | 1 hour         | 4 hours          | Daily        |

---

## Communication Protocols

### Internal Communication

**Slack Channels**:
- `#incidents` - Primary incident communication channel
- `#sre-oncall` - On-call coordination
- `#sre-escalation` - Escalation notifications
- `#alerts` - Automated alert notifications
- `#executive-incidents` - P0 incidents only

**Slack Incident Template**:

```
🚨 INCIDENT DECLARED 🚨
Incident ID: INC-20250130-1045
Severity: P1
Status: Investigating
Affected: API Server (5xx spike)
Impact: 40% error rate on /v1/chat/completions
Started: 2025-01-30 10:45 UTC
Assigned: @oncall-engineer

Next update: 11:15 UTC (30 min)
Grafana: http://localhost:3000/d/sre-incident-response
Runbook: docs/runbooks/PILOT_HIGH_5XX_RATE.md
```

### External Communication

**Status Page Updates** (if P0/P1):
- Update within 10 minutes
- Use clear, non-technical language
- Provide estimated time to resolution
- Update when status changes

---

## Post-Incident Review

### Blameless Post-Mortem Template

```markdown
# Incident Post-Mortem: [INC-ID]

## Incident Summary
- **Date**: YYYY-MM-DD
- **Duration**: XX minutes
- **Severity**: P[0-3]
- **Impact**: [users affected, revenue impact]
- **Responders**: [names]

## Timeline (All times UTC)
| Time  | Event |
|-------|-------|
| 10:45 | Alert fired: High error rate |
| 10:47 | On-call acknowledged |
| 10:52 | Root cause identified |
| 11:05 | Mitigation applied |
| 11:30 | Incident resolved |

## Root Cause
[Detailed explanation]

## Impact
- Users affected: [number]
- Services affected: [list]
- Revenue impact: $[amount]
- Data loss: [none/details]

## What Went Well
- Fast detection (< 2 minutes)
- Quick mitigation

## What Went Wrong
- [Issue 1]
- [Issue 2]

## Action Items
1. [JIRA-123] [Action] (Owner: [Name], Due: YYYY-MM-DD)
2. [JIRA-124] [Action] (Owner: [Name], Due: YYYY-MM-DD)
```

---

## Tools and Resources

### Monitoring Dashboards

**Grafana Dashboards**:
- **SRE Incident Response**: http://localhost:3000/d/sre-incident-response
  - Overview of all critical metrics
  - Error rates, latency, resource usage
  - Service health status
  
- **Kong Observability**: http://localhost:3000/d/kong-observability
  - Gateway metrics
  - Rate limiting status
  - Route performance
  
- **Platform Overview**: http://localhost:3000/d/platform-overview
  - High-level system health
  - Request throughput
  - Database performance

**Prometheus**:
- Query UI: http://localhost:9090
- Alerts: http://localhost:9090/alerts
- Targets: http://localhost:9090/targets

**Alertmanager**:
- UI: http://localhost:9093
- Silence management
- Alert routing

### Service Endpoints

**API Services**:
- API Server: http://localhost:8000
- Health: http://localhost:8000/health
- Metrics: http://localhost:8000/metrics

**Databases**:
- Qdrant UI: http://localhost:6333/dashboard
- Neo4j Browser: http://localhost:7474
- PostgreSQL: `psql -h localhost -U ai_user -d ai_platform`

**Gateway**:
- Kong Admin: http://localhost:8001
- Kong Proxy: http://localhost:8000

### Related Runbooks

- [Incident Response](./INCIDENT_RESPONSE.md) (this document)
- [Rollback Procedures](./ROLLBACK_PROCEDURES.md)
- [Debug Latency Spike](./DEBUG_LATENCY_SPIKE.md)
- [Debug Memory Leak](./DEBUG_MEMORY_LEAK.md)
- [Debug Circuit Breaker](./DEBUG_CIRCUIT_BREAKER.md)
- [High 5xx Rate](./PILOT_HIGH_5XX_RATE.md)
- [Memory Pressure](./PILOT_MEMORY_PRESSURE.md)
- [Drift Detected](./PILOT_DRIFT_DETECTED.md)
- [Kong Rate Limit](./PILOT_KONG_RATE_LIMIT.md)
- [Multi-Region Failover](../MULTI_REGION_FAILOVER_RUNBOOK.md)
- [Disaster Recovery](../../DISASTER_RECOVERY_RUNBOOK.md)

---

## Quick Reference Card

**First 60 Seconds**:

```bash
# 1. Acknowledge alert (PagerDuty)

# 2. Check dashboards
open http://localhost:3000/d/sre-incident-response

# 3. Quick health check
docker compose ps

# 4. Check recent errors
docker compose logs --tail=50 --since=5m | grep -i error

# 5. Determine severity (P0/P1/P2)

# 6. Post in #incidents
```

**Common Quick Fixes**:

```bash
# Restart service
docker compose restart <service>

# Scale up
kubectl scale deployment/<name> --replicas=5 -n production

# Rollback
./scripts/deploy/deploy_vm.sh rollback previous

# Check Prometheus for errors
curl -s 'http://localhost:9090/api/v1/query?query=rate(http_requests_total{status=~"5.."}[5m])' | jq
```

---

**Version**: 2.0  
**Last Updated**: 2025-01-30  
**Next Review**: 2025-02-28  
**Owner**: SRE Team
