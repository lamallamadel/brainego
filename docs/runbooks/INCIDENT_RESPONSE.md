# Incident Response Runbook

## Table of Contents
1. [Overview](#overview)
2. [Escalation Matrix](#escalation-matrix)
3. [On-Call Procedures](#on-call-procedures)
4. [Incident Lifecycle](#incident-lifecycle)
5. [Severity Definitions](#severity-definitions)
6. [Communication Protocols](#communication-protocols)
7. [Post-Incident Review](#post-incident-review)
8. [Tools and Resources](#tools-and-resources)

---

## Overview

This runbook defines the incident response process for the AI Platform. It covers escalation procedures, on-call responsibilities, incident management, and post-incident review processes.

### Incident Definition

An **incident** is an unplanned interruption or degradation of service that impacts:
- System availability (uptime < 99.9%)
- User-facing functionality
- Data integrity or security
- SLA compliance

### Response Objectives

- **Detection**: < 5 minutes
- **Acknowledgment**: < 10 minutes
- **Initial Response**: < 15 minutes
- **Resolution Target (P1)**: < 2 hours
- **Resolution Target (P2)**: < 4 hours
- **Resolution Target (P3)**: < 24 hours

---

## Escalation Matrix

### Level 1: On-Call Engineer (Primary Responder)

**Responsibilities**:
- Monitor alerts and respond within 10 minutes
- Initial triage and assessment
- Execute standard runbook procedures
- Engage additional resources if needed
- Update status page and stakeholders

**Authority**:
- Restart services
- Execute rollbacks (with approval for P1)
- Scale resources within approved limits
- Access production logs and metrics

**Escalation Triggers**:
- Unable to identify root cause within 30 minutes
- Issue requires specialized expertise
- Multiple system failures
- Data loss or security breach

**Contact Methods**:
- PagerDuty (primary)
- Slack: #sre-oncall
- Phone: See on-call rotation spreadsheet

---

### Level 2: Senior SRE / Database Administrator

**Responsibilities**:
- Complex troubleshooting and diagnosis
- Database recovery operations
- Performance optimization during incidents
- Provide guidance to L1 responders
- Coordinate with multiple teams

**Authority**:
- All L1 permissions
- Database schema changes (emergency)
- Infrastructure modifications
- Multi-region failover decisions
- Approve major rollbacks

**Escalation Triggers**:
- Issue persists beyond 1 hour
- Requires database or infrastructure expertise
- Cross-team coordination needed
- Potential for extended outage

**Contact Methods**:
- PagerDuty (escalation)
- Slack: #sre-escalation
- Phone: See escalation contact list

---

### Level 3: Platform Architect / Engineering Manager

**Responsibilities**:
- Strategic decision-making during major incidents
- Approve high-risk changes
- External stakeholder communication
- Resource allocation decisions
- Incident commander for P0/P1 incidents

**Authority**:
- All permissions
- Budget approvals for emergency resources
- Public communication and status updates
- Declare major incident
- Authorize data center failover

**Escalation Triggers**:
- Multiple critical systems down
- Estimated downtime > 2 hours
- Revenue impact > $10k/hour
- Security breach or data loss
- Regulatory compliance implications
- Media or customer escalation

**Contact Methods**:
- PagerDuty (critical escalation)
- Direct phone call (P0 only)
- Slack: #executive-incidents

---

## On-Call Procedures

### On-Call Rotation

**Schedule**:
- Primary: 7-day rotation, Monday 9:00 AM handoff
- Secondary: Backup coverage, 7-day rotation
- Overlap: 30-minute handoff meeting

**Handoff Checklist**:
- [ ] Review open incidents from previous week
- [ ] Review upcoming maintenance windows
- [ ] Verify PagerDuty configuration
- [ ] Test alert notification (phone, SMS, push)
- [ ] Review recent changes and deployments
- [ ] Check monitoring dashboard health
- [ ] Ensure VPN and access credentials work
- [ ] Review any known issues or watch items

### Pre-Requisites

**Required Access**:
- [ ] Production Kubernetes cluster (kubectl configured)
- [ ] Grafana dashboards (http://localhost:3000)
- [ ] Prometheus/Alertmanager (http://localhost:9090, :9093)
- [ ] VPN connection to production network
- [ ] SSH keys for bastion hosts
- [ ] Database credentials (read-only and admin)
- [ ] Cloud provider console access (AWS/GCP/Azure)
- [ ] Docker registry access
- [ ] Git repository access

**Required Tools**:
- Laptop with full battery or near power
- Mobile phone with PagerDuty app installed
- Internet connectivity (backup mobile hotspot recommended)
- Latest version of kubectl, docker, and cloud CLI tools

### Response Time Requirements

| Severity | Acknowledgment | Initial Response | Updates |
|----------|----------------|------------------|---------|
| P0/P1    | 10 minutes     | 15 minutes       | Every 30 min |
| P2       | 20 minutes     | 30 minutes       | Every 1 hour |
| P3       | 1 hour         | 4 hours          | Daily |

### During On-Call

**Continuous Monitoring**:
- Keep PagerDuty mobile app notifications enabled
- Monitor Slack #alerts channel
- Check dashboard health at shift start and every 4 hours
- Review Grafana for anomalies

**Response Readiness**:
- Be available to respond within acknowledgment window
- Have laptop accessible during waking hours
- If unable to respond, arrange coverage and update schedule
- Test alert delivery weekly

**After-Hours Coverage**:
- Primary on-call receives all alerts
- If no response in 15 minutes, secondary is alerted
- Escalation to manager if no response in 30 minutes

---

## Incident Lifecycle

### Phase 1: Detection and Triage (0-10 minutes)

**1.1 Alert Received**
```bash
# Acknowledge alert in PagerDuty immediately
# Check Grafana SRE Incident Response dashboard
http://localhost:3000/d/sre-incident-response

# Check Alertmanager for firing alerts
http://localhost:9093

# Quick system health check
kubectl get pods --all-namespaces
docker compose ps
```

**1.2 Initial Assessment**
- Identify affected systems and services
- Determine severity (use severity matrix below)
- Check if multiple alerts are related
- Look for recent changes (deployments, config changes)

**1.3 Create Incident**
```bash
# Create incident log
incident_id="INC-$(date +%Y%m%d-%H%M%S)"
echo "Incident: $incident_id" > /tmp/$incident_id.log
echo "Detected: $(date)" >> /tmp/$incident_id.log
echo "Severity: P[1-3]" >> /tmp/$incident_id.log
echo "Alerts: [alert names]" >> /tmp/$incident_id.log
echo "Affected: [services]" >> /tmp/$incident_id.log
```

**1.4 Initial Communication**
- Post in #incidents Slack channel
- Update status page if user-facing
- Notify manager for P0/P1 incidents

---

### Phase 2: Investigation (10-30 minutes)

**2.1 Gather Information**
```bash
# Check service logs
kubectl logs -l app=api-server --tail=100 -n production
kubectl logs -l app=gateway --tail=100 -n production

# Or for docker compose
docker compose logs --tail=100 api-server
docker compose logs --tail=100 gateway

# Check resource utilization
kubectl top pods -n production
kubectl top nodes

# Check recent events
kubectl get events -n production --sort-by='.lastTimestamp' | tail -20
```

**2.2 Identify Root Cause**
- Review logs for errors and exceptions
- Check metrics for anomalies (CPU, memory, latency, errors)
- Correlate with recent deployments or changes
- Check dependencies (databases, external APIs)
- Review similar past incidents

**2.3 Determine Impact**
- Number of users affected
- Duration of impact
- Degraded vs completely unavailable
- Data integrity concerns
- Business/revenue impact

**2.4 Consult Runbooks**
- [Debug Latency Spike](./DEBUG_LATENCY_SPIKE.md)
- [Debug Memory Leak](./DEBUG_MEMORY_LEAK.md)
- [Debug Circuit Breaker](./DEBUG_CIRCUIT_BREAKER.md)
- [Disaster Recovery](../../DISASTER_RECOVERY_RUNBOOK.md)
- [Multi-Region Failover](../MULTI_REGION_FAILOVER_RUNBOOK.md)

---

### Phase 3: Mitigation (30-60 minutes)

**3.1 Immediate Mitigation**

Choose appropriate mitigation based on root cause:

**Service Restart**:
```bash
# Kubernetes
kubectl rollout restart deployment/api-server -n production

# Docker Compose
docker compose restart api-server
```

**Rollback Deployment**:
```bash
# See ROLLBACK_PROCEDURES.md for detailed steps
kubectl rollout undo deployment/api-server -n production

# Or blue-green swap
./scripts/blue-green-swap.sh --rollback
```

**Scale Resources**:
```bash
# Horizontal scaling
kubectl scale deployment/api-server --replicas=10 -n production

# Vertical scaling (add resources)
kubectl set resources deployment/api-server \
  --limits=cpu=2000m,memory=4Gi \
  --requests=cpu=1000m,memory=2Gi \
  -n production
```

**Circuit Breaker Reset**:
```bash
# See DEBUG_CIRCUIT_BREAKER.md
curl -X POST http://localhost:8000/admin/circuit-breaker/reset
```

**Database Failover**:
```bash
# See MULTI_REGION_FAILOVER_RUNBOOK.md
python scripts/failover_db.py --region us-west-2
```

**3.2 Verify Mitigation**
```bash
# Check service health
curl http://localhost:8000/health

# Run smoke tests
./smoke_tests.sh

# Check alerts cleared
# Visit Alertmanager to confirm
```

**3.3 Update Stakeholders**
- Post mitigation status in #incidents
- Update status page with resolution
- Notify manager if escalated

---

### Phase 4: Monitoring and Validation (1-2 hours)

**4.1 Monitor Recovery**
- Watch metrics for 30-60 minutes
- Ensure error rates return to baseline
- Verify latency within SLA
- Check for recurring issues

**4.2 Collect Evidence**
```bash
# Save logs for post-mortem
kubectl logs -l app=api-server --since=2h -n production > /tmp/${incident_id}_logs.txt

# Save metrics snapshots
# Take screenshots of relevant Grafana panels

# Document timeline
echo "Timeline:" >> /tmp/$incident_id.log
echo "10:15 - Alert received" >> /tmp/$incident_id.log
echo "10:18 - Root cause identified" >> /tmp/$incident_id.log
echo "10:25 - Mitigation deployed" >> /tmp/$incident_id.log
echo "10:30 - Incident resolved" >> /tmp/$incident_id.log
```

**4.3 Declare Resolution**
- Confirm all metrics back to normal
- Verify no related alerts firing
- Post resolution message in #incidents
- Update status page to "Operational"
- Close PagerDuty incident

---

### Phase 5: Post-Incident (24-48 hours)

**5.1 Document Incident**
- Complete incident report template
- Include timeline, root cause, impact
- Document mitigation steps taken
- List action items and prevention measures

**5.2 Schedule Post-Mortem**
- Schedule meeting within 48 hours
- Invite all involved parties
- Use blameless post-mortem format
- Focus on learning and improvement

**5.3 Action Items**
- Create Jira tickets for follow-up work
- Assign owners and deadlines
- Track to completion
- Update runbooks with lessons learned

---

## Severity Definitions

### P0 - Critical (Emergency)

**Definition**: Complete system outage or data loss

**Criteria**:
- All users cannot access the system
- Data loss or corruption occurring
- Security breach actively happening
- Revenue loss > $10k/hour

**Response**:
- Immediate response required
- Escalate to Platform Architect immediately
- Update every 15 minutes
- All hands on deck

**Examples**:
- Complete API server failure
- Database data loss
- Security breach with data exfiltration
- Multi-region total outage

---

### P1 - High (Urgent)

**Definition**: Major functionality unavailable or severely degraded

**Criteria**:
- Core features unavailable
- Impacts majority of users
- SLA breach imminent
- Workaround not available

**Response**:
- Response within 15 minutes
- Escalate to Senior SRE if not resolved in 30 minutes
- Update every 30 minutes
- Focus all resources on resolution

**Examples**:
- Inference API returning 50% errors
- Authentication system down
- Primary database unreachable
- Critical service memory leak causing crashes

---

### P2 - Medium (Important)

**Definition**: Partial functionality impacted or performance degraded

**Criteria**:
- Non-critical features unavailable
- Performance degradation noticeable
- Impacts subset of users
- Workaround available

**Response**:
- Response within 30 minutes
- Update every hour
- Can be resolved during business hours

**Examples**:
- Elevated latency (P99 > 2s)
- Secondary database replication lag
- Memory usage at 85%
- Circuit breaker open on non-critical service

---

### P3 - Low (Planned Work)

**Definition**: Minor issues with minimal user impact

**Criteria**:
- Cosmetic issues
- Affects very few users
- Workarounds exist
- No SLA impact

**Response**:
- Response within 4 hours
- Can be scheduled during business hours
- Update daily

**Examples**:
- Documentation outdated
- Minor UI glitch
- Non-critical dashboard not updating
- Debug logging too verbose

---

## Communication Protocols

### Internal Communication

**Slack Channels**:
- `#incidents` - Primary incident communication channel
- `#sre-oncall` - On-call coordination
- `#sre-escalation` - Escalation notifications
- `#alerts` - Automated alert notifications

**Slack Incident Template**:
```
🚨 INCIDENT DECLARED 🚨
Incident ID: INC-20250130-1045
Severity: P1
Status: Investigating
Affected: API Server, Inference Service
Impact: 40% error rate on /v1/chat/completions
Started: 2025-01-30 10:45 UTC
Assigned: @oncall-engineer

Next update: 11:15 UTC
Runbook: https://github.com/org/repo/blob/main/docs/runbooks/DEBUG_LATENCY_SPIKE.md
```

### External Communication

**Status Page Updates**:
- Update within 10 minutes of P0/P1 incidents
- Use clear, non-technical language
- Provide estimated time to resolution
- Update when status changes

**Status Page Template**:
```
Investigating - We are currently investigating elevated error rates 
affecting the chat completion API. Users may experience intermittent 
failures. We are actively working on a resolution.

Posted: 10:50 UTC
Next update: 11:30 UTC
```

### Escalation Communication

**To Manager (P0/P1)**:
```
Subject: P1 Incident - API Server Error Rate

We have a P1 incident affecting the API server with 40% error rate.
Root cause appears to be database connection pool exhaustion.
Currently implementing mitigation by scaling connection pool.
ETA for resolution: 30 minutes.

Will update in 30 minutes or sooner if status changes.
```

**To Executives (P0 only)**:
```
Subject: URGENT - System Outage

We are experiencing a complete API outage affecting all users.
Issue detected at 10:45 UTC.
Team is actively working on restoration.
Estimated impact: $5k revenue loss per hour.
Full team engaged. Next update in 15 minutes.
```

---

## Post-Incident Review

### Blameless Post-Mortem Process

**Objectives**:
- Understand what happened and why
- Identify improvements to prevent recurrence
- Share learnings across the organization
- Update runbooks and documentation

**Attendees**:
- Incident responder(s)
- System owner(s)
- SRE team
- Engineering manager
- Optional: Product, Support (for user-facing incidents)

**Timeline**:
- Schedule within 24-48 hours
- Duration: 1 hour
- Send pre-read materials 24 hours before

### Post-Mortem Template

```markdown
# Incident Post-Mortem: [Incident ID]

## Incident Summary
- **Date**: 2025-01-30
- **Duration**: 45 minutes
- **Severity**: P1
- **Impact**: 40% error rate, 500 users affected
- **Responders**: On-Call Engineer, Senior SRE

## Timeline (All times UTC)
- 10:45 - Alert fired: High error rate on API server
- 10:47 - On-call acknowledged, began investigation
- 10:52 - Root cause identified: DB connection pool exhaustion
- 10:55 - Mitigation started: Increased connection pool size
- 11:05 - Service recovered, error rate normalized
- 11:30 - Incident declared resolved after monitoring

## Root Cause
Database connection pool was configured for 50 connections, 
insufficient for peak load of 200 req/s introduced by new feature launch.

## Detection
- Automated alert from Prometheus: `high_error_rate`
- User reports in support channel
- Detection time: < 2 minutes

## Impact
- 500 users experienced intermittent 500 errors
- Estimated 2,000 failed requests
- No data loss or corruption
- Estimated revenue impact: ~$200

## Resolution
1. Increased database connection pool from 50 to 200
2. Restarted API server pods to apply change
3. Monitored for 30 minutes to confirm stability

## What Went Well
- Fast detection (< 2 minutes)
- Quick root cause identification (7 minutes)
- Effective mitigation (20 minutes to resolution)
- Good communication with stakeholders

## What Went Wrong
- Connection pool size not tested under peak load
- Feature launch did not include load testing
- No monitoring for connection pool exhaustion

## Action Items
1. [JIRA-123] Add connection pool metrics and alerting (Owner: SRE, Due: 2025-02-05)
2. [JIRA-124] Document load testing requirements for launches (Owner: QA, Due: 2025-02-10)
3. [JIRA-125] Review and right-size all connection pools (Owner: DBA, Due: 2025-02-15)
4. [JIRA-126] Update deployment checklist to include resource validation (Owner: SRE, Due: 2025-02-03)

## Lessons Learned
- Always load test with realistic traffic before major launches
- Monitor resource exhaustion, not just errors
- Connection pool sizing should be based on expected peak load
```

---

## Tools and Resources

### Monitoring and Alerting
- **Grafana**: http://localhost:3000
  - [SRE Incident Response Dashboard](http://localhost:3000/d/sre-incident-response)
  - [Platform Overview](http://localhost:3000/d/platform-overview)
- **Prometheus**: http://localhost:9090
- **Alertmanager**: http://localhost:9093

### Logs and Tracing
- **Loki**: http://localhost:3100
- **Grafana Logs Explorer**: http://localhost:3000/explore

### Infrastructure
- **Kubernetes Dashboard**: `kubectl proxy` then http://localhost:8001/api/v1/namespaces/kubernetes-dashboard/services/https:kubernetes-dashboard:/proxy/
- **Docker Compose**: `docker compose ps`, `docker compose logs`

### Databases
- **Qdrant UI**: http://localhost:6333/dashboard
- **Neo4j Browser**: http://localhost:7474
- **PostgreSQL**: `psql -h localhost -U ai_user -d ai_platform`

### Runbooks
- [Incident Response](./INCIDENT_RESPONSE.md) (this document)
- [Rollback Procedures](./ROLLBACK_PROCEDURES.md)
- [Debug Latency Spike](./DEBUG_LATENCY_SPIKE.md)
- [Debug Memory Leak](./DEBUG_MEMORY_LEAK.md)
- [Debug Circuit Breaker](./DEBUG_CIRCUIT_BREAKER.md)
- [Disaster Recovery](../../DISASTER_RECOVERY_RUNBOOK.md)
- [Multi-Region Failover](../MULTI_REGION_FAILOVER_RUNBOOK.md)

### External Resources
- **PagerDuty**: https://yourorg.pagerduty.com
- **Status Page**: https://status.yourplatform.com
- **Incident Management Tool**: Jira, ServiceNow, etc.
- **Documentation Wiki**: Confluence, Notion, etc.

---

## Appendix A: Quick Reference Commands

### Health Checks
```bash
# API health
curl http://localhost:8000/health

# All services
docker compose ps

# Kubernetes pods
kubectl get pods -n production

# Database connectivity
psql -h localhost -U ai_user -d ai_platform -c "SELECT 1"
curl http://localhost:6333/health
```

### Log Collection
```bash
# Last 1 hour of logs
kubectl logs -l app=api-server --since=1h -n production > api_logs.txt

# Stream live logs
docker compose logs -f api-server

# All container logs
for service in $(docker compose ps --services); do
  echo "=== $service ===" >> all_logs.txt
  docker compose logs --tail=100 $service >> all_logs.txt
done
```

### Metrics Queries
```bash
# Current error rate
curl -s 'http://localhost:9090/api/v1/query?query=rate(http_requests_total{status=~"5.."}[5m])'

# Memory usage
curl -s 'http://localhost:9090/api/v1/query?query=container_memory_usage_bytes'

# Request latency P99
curl -s 'http://localhost:9090/api/v1/query?query=histogram_quantile(0.99,rate(http_request_duration_seconds_bucket[5m]))'
```

---

## Appendix B: Incident Report Template

Save as `incident_report_${incident_id}.md`:

```markdown
# Incident Report: [INC-ID]

**Date**: YYYY-MM-DD  
**Duration**: XX minutes  
**Severity**: P[0-3]  
**Status**: Resolved  

## Executive Summary
[One paragraph summary for non-technical stakeholders]

## Timeline
| Time (UTC) | Event |
|------------|-------|
| 10:45 | Alert fired |
| 10:47 | Investigation started |
| 11:05 | Mitigation applied |
| 11:30 | Incident resolved |

## Root Cause
[Detailed technical explanation]

## Impact
- Users affected: [number]
- Services affected: [list]
- Duration: [minutes]
- Revenue impact: $[amount]
- Data loss: [none/details]

## Resolution
[Steps taken to resolve]

## Prevention
[What we'll do to prevent recurrence]

## Action Items
1. [Item with owner and due date]
2. [Item with owner and due date]
```

---

**Version**: 1.0  
**Last Updated**: 2025-01-30  
**Next Review**: 2025-02-28  
**Owner**: SRE Team
