# Multi-Region Failover Runbook

## Overview

This runbook provides step-by-step procedures for managing multi-region DNS failover for the AI Platform. It covers both automated failover operations and manual intervention procedures.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [DNS Weighted Routing](#dns-weighted-routing)
3. [Automated Failover](#automated-failover)
4. [Manual Failover Procedures](#manual-failover-procedures)
5. [Rollback Procedures](#rollback-procedures)
6. [Monitoring & Alerts](#monitoring--alerts)
7. [Troubleshooting](#troubleshooting)
8. [Emergency Contacts](#emergency-contacts)

---

## Architecture Overview

### Multi-Region Setup

The AI Platform is deployed across multiple regions with the following architecture:

```
┌─────────────────────────────────────────────────────────────────┐
│                        Route53 / Cloud DNS                      │
│                   Weighted Routing + Health Checks              │
└────────────────┬────────────────┬───────────────┬───────────────┘
                 │                │               │
                 ▼                ▼               ▼
         ┌───────────────┐ ┌──────────────┐ ┌──────────────┐
         │   us-west-1   │ │  us-east-1   │ │  eu-west-1   │
         │  (Primary)    │ │ (Secondary)  │ │  (Tertiary)  │
         │  Weight: 100  │ │  Weight: 0   │ │  Weight: 0   │
         └───────────────┘ └──────────────┘ └──────────────┘
```

### Key Components

- **DNS Provider**: AWS Route53 or Google Cloud DNS
- **Load Balancers**: Regional load balancers in each region
- **Health Checks**: HTTP health checks on `/health` endpoint (port 9002)
- **Monitoring**: Prometheus metrics for error rate, latency, availability
- **Automation**: `failover_region.py` script for automated failover

### Region Priority

| Region     | Priority | Default Weight | Role      |
|------------|----------|----------------|-----------|
| us-west-1  | 1        | 100            | Primary   |
| us-east-1  | 2        | 0              | Secondary |
| eu-west-1  | 3        | 0              | Tertiary  |

---

## DNS Weighted Routing

### How It Works

DNS weighted routing distributes traffic based on weights assigned to each region:

- **Weight 100**: Receives all traffic
- **Weight 0**: Receives no traffic (standby)
- **Weight 50/50**: Splits traffic equally (for testing)

### Health Checks

Each region has a health check that monitors:

- **Path**: `/health`
- **Port**: 9002
- **Protocol**: HTTPS
- **Interval**: 30 seconds
- **Timeout**: 5 seconds
- **Healthy threshold**: 2 consecutive successes
- **Unhealthy threshold**: 3 consecutive failures

When a health check fails, Route53/Cloud DNS automatically stops routing traffic to that region.

### TTL (Time To Live)

- **DNS TTL**: 60 seconds
- **Cache propagation**: Up to 60 seconds for DNS changes to propagate globally
- **Effective failover time**: 60-90 seconds (TTL + health check detection)

---

## Automated Failover

### Monitoring Service

The `failover_region.py` script runs continuously and monitors region health via Prometheus metrics.

#### Starting the Monitor

```bash
# Start automated failover monitoring
python scripts/deploy/failover_region.py monitor \
  --config configs/failover-config.yaml \
  --prometheus-url http://prometheus:9090 \
  --interval 60 \
  --log-level INFO
```

#### Run as Systemd Service

```bash
# Create systemd service file
sudo tee /etc/systemd/system/multi-region-failover.service > /dev/null <<EOF
[Unit]
Description=Multi-Region Failover Automation
After=network.target

[Service]
Type=simple
User=platform
WorkingDirectory=/opt/ai-platform
ExecStart=/usr/bin/python3 scripts/deploy/failover_region.py monitor \
  --config configs/failover-config.yaml \
  --prometheus-url http://prometheus:9090 \
  --interval 60
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Enable and start service
sudo systemctl enable multi-region-failover
sudo systemctl start multi-region-failover
sudo systemctl status multi-region-failover
```

### Failover Triggers

Automated failover is triggered when:

1. **Metric-based**:
   - Error rate > 5% for 3 consecutive checks
   - P95 latency > 1000ms for 3 consecutive checks
   - Availability < 99% for 3 consecutive checks

2. **Alert-based**:
   - Prometheus alert fires: `HighErrorRate`, `HighLatency`, `ServiceDown`
   - Alert severity: `critical`
   - Alert affects primary region

### Failover Process

1. **Detection**: Monitor detects unhealthy primary region
2. **Validation**: Checks for 3 consecutive failures (configurable)
3. **Target Selection**: Finds healthy secondary region with highest priority
4. **DNS Update**: Shifts weights (primary → 0, secondary → 100)
5. **Notification**: Sends alert to Slack/webhook
6. **Logging**: Records failover event in history

### Rollback Process

Automated rollback occurs when:

1. Original primary region recovers
2. 5 consecutive successful health checks (configurable)
3. Current active region is not the original primary

Rollback process:

1. **Detection**: Monitor detects recovered primary region
2. **Validation**: Checks for 5 consecutive successes
3. **DNS Update**: Shifts weights back (primary → 100, secondary → 0)
4. **Notification**: Sends rollback notification
5. **Logging**: Records rollback event

---

## Manual Failover Procedures

### Prerequisites

```bash
# Install dependencies
pip install -r scripts/deploy/requirements-deploy.txt

# Verify AWS/GCP credentials
aws sts get-caller-identity  # For Route53
gcloud auth list              # For Cloud DNS

# Check current DNS status
python scripts/deploy/failover_region.py status \
  --config configs/failover-config.yaml \
  --prometheus-url http://prometheus:9090
```

### Scenario 1: Primary Region Outage

**Symptoms**: Primary region (us-west-1) is completely down or severely degraded.

**Procedure**:

1. **Assess the situation**:
   ```bash
   # Check region health
   python scripts/deploy/failover_region.py status \
     --config configs/failover-config.yaml \
     --prometheus-url http://prometheus:9090
   
   # Check Prometheus metrics
   curl "http://prometheus:9090/api/v1/query?query=up{region='us-west-1'}"
   
   # Test primary endpoint
   curl -v https://us-west-1.ai-platform.example.com/health
   ```

2. **Verify secondary region is healthy**:
   ```bash
   # Check secondary region
   curl -v https://us-east-1.ai-platform.example.com/health
   
   # Check Prometheus metrics
   curl "http://prometheus:9090/api/v1/query?query=up{region='us-east-1'}"
   ```

3. **Execute manual failover** (DRY RUN first):
   ```bash
   # Dry run
   python scripts/deploy/failover_region.py failover \
     --config configs/failover-config.yaml \
     --prometheus-url http://prometheus:9090 \
     --to us-east-1 \
     --reason "Primary region outage - incident #12345" \
     --dry-run
   
   # Actual failover
   python scripts/deploy/failover_region.py failover \
     --config configs/failover-config.yaml \
     --prometheus-url http://prometheus:9090 \
     --to us-east-1 \
     --reason "Primary region outage - incident #12345"
   ```

4. **Verify failover**:
   ```bash
   # Check DNS weights (wait 60 seconds for TTL)
   sleep 60
   
   # Check status
   python scripts/deploy/failover_region.py status \
     --config configs/failover-config.yaml \
     --prometheus-url http://prometheus:9090
   
   # Verify traffic is flowing to secondary
   curl https://ai-platform.example.com/health
   
   # Monitor Prometheus
   # Check that traffic metrics show us-east-1 receiving requests
   ```

5. **Notify stakeholders**:
   - Update incident ticket
   - Notify team via Slack/PagerDuty
   - Update status page

**Expected Result**: Traffic shifts from us-west-1 to us-east-1 within 60-90 seconds.

---

### Scenario 2: Planned Maintenance

**Use Case**: Need to perform maintenance on primary region (e.g., database migration, Kubernetes upgrade).

**Procedure**:

1. **Pre-maintenance checklist**:
   ```bash
   # Verify all regions are healthy
   python scripts/deploy/failover_region.py status \
     --config configs/failover-config.yaml \
     --prometheus-url http://prometheus:9090
   
   # Check data replication status
   # Verify Postgres replication lag < 5s
   # Verify Qdrant collections are synced
   ```

2. **Schedule maintenance window**:
   - Announce maintenance window (e.g., 2 AM - 4 AM UTC)
   - Update status page
   - Notify customers

3. **Failover to secondary** (before maintenance):
   ```bash
   # Failover to us-east-1
   python scripts/deploy/failover_region.py failover \
     --config configs/failover-config.yaml \
     --prometheus-url http://prometheus:9090 \
     --to us-east-1 \
     --reason "Planned maintenance - ticket #67890"
   
   # Wait for DNS propagation
   sleep 90
   
   # Verify no traffic to primary
   # Check Prometheus: rate(http_requests_total{region="us-west-1"}[5m]) should be 0
   ```

4. **Perform maintenance on primary**:
   - Execute maintenance tasks
   - Verify services are healthy after maintenance
   - Run smoke tests

5. **Rollback to primary** (after maintenance):
   ```bash
   # Verify primary is healthy
   curl https://us-west-1.ai-platform.example.com/health
   
   # Rollback
   python scripts/deploy/failover_region.py rollback \
     --config configs/failover-config.yaml \
     --prometheus-url http://prometheus:9090 \
     --to us-west-1
   
   # Wait for DNS propagation
   sleep 90
   
   # Verify traffic is back on primary
   ```

6. **Post-maintenance**:
   - Update incident ticket
   - Close maintenance window
   - Update status page

---

### Scenario 3: Degraded Performance

**Symptoms**: Primary region is responsive but showing degraded performance (high latency, elevated error rate).

**Procedure**:

1. **Investigate**:
   ```bash
   # Check metrics
   # Error rate: rate(http_requests_total{region="us-west-1",status=~"5.."}[5m])
   # Latency: histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{region="us-west-1"}[5m]))
   
   # Check logs
   kubectl logs -n ai-platform -l app=gateway --tail=100 -f
   
   # Check resource usage
   kubectl top nodes
   kubectl top pods -n ai-platform
   ```

2. **Determine severity**:
   - **Minor**: Latency 1-2x normal, error rate 1-3%
     → Monitor and investigate, do NOT failover
   
   - **Moderate**: Latency 2-3x normal, error rate 3-5%
     → Investigate root cause, prepare for failover
   
   - **Severe**: Latency >3x normal, error rate >5%
     → Execute immediate failover

3. **If severe, execute failover**:
   ```bash
   python scripts/deploy/failover_region.py failover \
     --config configs/failover-config.yaml \
     --prometheus-url http://prometheus:9090 \
     --to us-east-1 \
     --reason "Severe performance degradation - investigating"
   ```

4. **Investigate root cause** (while traffic is on secondary):
   - Check for resource exhaustion (CPU, memory, disk)
   - Check for network issues
   - Check for database connection pool exhaustion
   - Check for external service dependencies

5. **Remediate and rollback**:
   - Fix root cause
   - Verify primary region health
   - Execute rollback (see Scenario 2)

---

## Rollback Procedures

### Automatic Rollback

If automated monitoring is running, rollback will occur automatically when:

- Original primary region recovers
- 5 consecutive successful health checks
- No manual intervention needed

### Manual Rollback

**When to use**: After manual failover, when primary region has been restored.

**Procedure**:

1. **Verify primary region health**:
   ```bash
   # Health check
   curl -v https://us-west-1.ai-platform.example.com/health
   
   # Smoke tests
   curl -X POST https://us-west-1.ai-platform.example.com/v1/chat \
     -H "Content-Type: application/json" \
     -d '{"messages":[{"role":"user","content":"test"}]}'
   
   # Check metrics (5-10 min baseline)
   # Error rate should be < 1%
   # Latency p95 should be < 500ms
   ```

2. **Execute rollback** (DRY RUN first):
   ```bash
   # Dry run
   python scripts/deploy/failover_region.py rollback \
     --config configs/failover-config.yaml \
     --prometheus-url http://prometheus:9090 \
     --to us-west-1 \
     --dry-run
   
   # Actual rollback
   python scripts/deploy/failover_region.py rollback \
     --config configs/failover-config.yaml \
     --prometheus-url http://prometheus:9090 \
     --to us-west-1
   ```

3. **Monitor rollback**:
   ```bash
   # Wait for DNS propagation
   sleep 90
   
   # Check traffic distribution
   # Should see traffic shifting back to us-west-1
   watch -n 5 'curl -s "http://prometheus:9090/api/v1/query?query=rate(http_requests_total[5m])" | jq'
   ```

4. **Verify rollback success**:
   ```bash
   # Check DNS weights
   python scripts/deploy/failover_region.py status \
     --config configs/failover-config.yaml \
     --prometheus-url http://prometheus:9090
   
   # Verify metrics
   # Error rate, latency, availability should be normal
   ```

### Rollback Failure

**If rollback fails or primary shows issues after rollback**:

1. **Immediately fail forward to secondary**:
   ```bash
   python scripts/deploy/failover_region.py failover \
     --config configs/failover-config.yaml \
     --prometheus-url http://prometheus:9090 \
     --to us-east-1 \
     --reason "Rollback failed - primary still unhealthy"
   ```

2. **Escalate to engineering team**:
   - Create incident ticket
   - Page on-call engineer
   - Continue investigation on primary region

3. **Do NOT attempt rollback again** until root cause is identified and fixed

---

## Monitoring & Alerts

### Key Metrics

Monitor these metrics for each region:

#### Error Rate
```promql
rate(http_requests_total{region="REGION",status=~"5.."}[5m]) 
/ 
rate(http_requests_total{region="REGION"}[5m])
```

**Threshold**: < 5%

#### Latency (p95)
```promql
histogram_quantile(0.95, 
  rate(http_request_duration_seconds_bucket{region="REGION"}[5m])
)
```

**Threshold**: < 1000ms

#### Availability
```promql
up{region="REGION"}
```

**Threshold**: >= 99%

#### Request Rate
```promql
rate(http_requests_total{region="REGION"}[5m])
```

**Use**: Traffic distribution verification

### Prometheus Alerts

#### High Error Rate
```yaml
- alert: HighErrorRate
  expr: |
    rate(http_requests_total{status=~"5.."}[5m]) 
    / 
    rate(http_requests_total[5m]) > 0.05
  for: 3m
  labels:
    severity: critical
  annotations:
    summary: "High error rate in {{ $labels.region }}"
    description: "Error rate is {{ $value | humanizePercentage }}"
```

#### High Latency
```yaml
- alert: HighLatency
  expr: |
    histogram_quantile(0.95, 
      rate(http_request_duration_seconds_bucket[5m])
    ) > 1.0
  for: 3m
  labels:
    severity: critical
  annotations:
    summary: "High latency in {{ $labels.region }}"
    description: "p95 latency is {{ $value }}s"
```

#### Service Down
```yaml
- alert: ServiceDown
  expr: up == 0
  for: 2m
  labels:
    severity: critical
  annotations:
    summary: "Service down in {{ $labels.region }}"
    description: "Service has been down for 2+ minutes"
```

### Grafana Dashboards

**Multi-Region Overview Dashboard**:
- Panel 1: Request rate per region
- Panel 2: Error rate per region
- Panel 3: Latency (p50, p95, p99) per region
- Panel 4: DNS weights per region
- Panel 5: Failover event timeline

**Access**: https://grafana.ai-platform.example.com/d/multi-region-overview

---

## Troubleshooting

### DNS Changes Not Taking Effect

**Symptoms**: DNS weights updated but traffic not shifting.

**Diagnosis**:
```bash
# Check DNS propagation
dig ai-platform.example.com
nslookup ai-platform.example.com

# Check Route53 change status
aws route53 get-change --id /change/C123456789

# Check current DNS records
aws route53 list-resource-record-sets \
  --hosted-zone-id Z1234567890ABC \
  --query "ResourceRecordSets[?Name=='ai-platform.example.com.']"
```

**Resolution**:
- Wait for TTL expiration (60 seconds)
- Check DNS resolver cache
- Verify Route53/Cloud DNS API calls succeeded
- Check IAM permissions for DNS updates

---

### Health Check Failing but Service is Healthy

**Symptoms**: Health check reports unhealthy, but manual curl succeeds.

**Diagnosis**:
```bash
# Check from health check origin IP
# (Route53 health checkers come from specific IP ranges)

# Check security groups / firewall rules
kubectl get service gateway -n ai-platform -o yaml

# Check health endpoint
curl -v https://us-west-1.ai-platform.example.com/health

# Check logs
kubectl logs -n ai-platform -l app=gateway --tail=100 | grep "/health"
```

**Resolution**:
- Verify firewall allows Route53 health checker IPs
- Check TLS certificate validity
- Verify health endpoint is not rate-limited
- Check load balancer configuration

---

### Failover Script Errors

**Error**: `boto3 not available`

**Resolution**:
```bash
pip install boto3>=1.26.0
```

---

**Error**: `hosted_zone_id not configured`

**Resolution**:
```bash
# Update configs/failover-config.yaml
# Set hosted_zone_id to your Route53 zone ID

# Find your hosted zone ID
aws route53 list-hosted-zones
```

---

**Error**: `No healthy secondary region available`

**Resolution**:
- Check health of all regions
- Verify at least one secondary region is healthy
- If all regions unhealthy, investigate infrastructure issue
- Consider deploying to additional region

---

### Rollback Not Triggering Automatically

**Symptoms**: Primary recovered, but automated rollback not occurring.

**Diagnosis**:
```bash
# Check if monitoring service is running
sudo systemctl status multi-region-failover

# Check logs
sudo journalctl -u multi-region-failover -f

# Check consecutive_successes threshold
# Default: 5 consecutive successes needed
```

**Resolution**:
- Verify monitoring service is running
- Check Prometheus connectivity
- Verify consecutive_successes threshold in config
- Manual rollback if needed

---

## Emergency Contacts

### On-Call Rotation

| Role                  | Primary Contact       | Backup Contact        |
|-----------------------|-----------------------|-----------------------|
| Platform Engineer     | oncall-platform@      | platform-lead@        |
| SRE                   | oncall-sre@           | sre-lead@             |
| DevOps                | oncall-devops@        | devops-lead@          |

### Escalation Path

1. **L1**: On-call engineer (respond within 15 min)
2. **L2**: Team lead (escalate after 30 min if unresolved)
3. **L3**: Director of Engineering (escalate for major outage)

### Communication Channels

- **Incident Slack**: #incidents
- **On-call Slack**: #oncall
- **Status Page**: https://status.ai-platform.example.com
- **PagerDuty**: https://aiplatform.pagerduty.com

---

## Appendix

### DNS Weight Testing

**Test 50/50 split** (for gradual rollout):

```bash
# Edit configs/failover-config.yaml or use direct API call
aws route53 change-resource-record-sets \
  --hosted-zone-id Z1234567890ABC \
  --change-batch '{
    "Changes": [{
      "Action": "UPSERT",
      "ResourceRecordSet": {
        "Name": "ai-platform.example.com.",
        "Type": "A",
        "SetIdentifier": "us-west-1",
        "Weight": 50,
        ...
      }
    }, {
      "Action": "UPSERT",
      "ResourceRecordSet": {
        "Name": "ai-platform.example.com.",
        "Type": "A",
        "SetIdentifier": "us-east-1",
        "Weight": 50,
        ...
      }
    }]
  }'
```

### Manual DNS Update (AWS CLI)

```bash
# Get current record sets
aws route53 list-resource-record-sets \
  --hosted-zone-id Z1234567890ABC \
  --output json > current-records.json

# Edit current-records.json to update weights

# Apply changes
aws route53 change-resource-record-sets \
  --hosted-zone-id Z1234567890ABC \
  --change-batch file://change-batch.json
```

### Manual DNS Update (gcloud CLI)

```bash
# List current records
gcloud dns record-sets list \
  --zone=ai-platform-zone

# Update record (transaction)
gcloud dns record-sets transaction start \
  --zone=ai-platform-zone

gcloud dns record-sets transaction remove \
  --name=ai-platform.example.com. \
  --ttl=60 \
  --type=A \
  --zone=ai-platform-zone \
  [old-ip]

gcloud dns record-sets transaction add \
  --name=ai-platform.example.com. \
  --ttl=60 \
  --type=A \
  --zone=ai-platform-zone \
  [new-ip]

gcloud dns record-sets transaction execute \
  --zone=ai-platform-zone
```

---

## Change Log

| Date       | Version | Author | Changes                                  |
|------------|---------|--------|------------------------------------------|
| 2024-01-15 | 1.0     | SRE    | Initial runbook creation                 |
| 2024-01-20 | 1.1     | SRE    | Added troubleshooting section            |
| 2024-02-01 | 1.2     | SRE    | Added Prometheus alert examples          |

---

**Document Owner**: SRE Team  
**Last Reviewed**: 2024-01-15  
**Next Review**: 2024-04-15  

---

*For questions or updates to this runbook, contact the SRE team via #sre-team on Slack.*
