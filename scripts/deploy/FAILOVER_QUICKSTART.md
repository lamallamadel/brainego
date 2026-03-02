# Multi-Region DNS Failover - Quick Start Guide

## Overview

This guide provides quick commands and procedures for multi-region DNS failover operations.

## Prerequisites

```bash
# Install dependencies
pip install -r scripts/deploy/requirements-deploy.txt

# Configure AWS credentials (for Route53)
aws configure

# Or configure GCP credentials (for Cloud DNS)
gcloud auth application-default login
```

## Configuration

Edit `configs/failover-config.yaml`:

```yaml
dns_provider: route53  # or cloud_dns
hosted_zone_id: Z1234567890ABC  # Your Route53 zone ID

regions:
  us-west-1:
    priority: 1  # Primary
  us-east-1:
    priority: 2  # Secondary
  eu-west-1:
    priority: 3  # Tertiary

thresholds:
  max_error_rate: 0.05
  max_latency_ms: 1000
  min_availability: 0.99
  consecutive_failures: 3
  consecutive_successes: 5
```

## Common Commands

### Check Current Status

```bash
python scripts/deploy/failover_region.py status \
  --config configs/failover-config.yaml \
  --prometheus-url http://prometheus:9090
```

### Start Automated Monitoring

```bash
# Foreground (for testing)
python scripts/deploy/failover_region.py monitor \
  --config configs/failover-config.yaml \
  --prometheus-url http://prometheus:9090 \
  --interval 60

# Background (production)
nohup python scripts/deploy/failover_region.py monitor \
  --config configs/failover-config.yaml \
  --prometheus-url http://prometheus:9090 \
  --interval 60 \
  --log-level INFO \
  > /var/log/failover-monitor.log 2>&1 &
```

### Manual Failover

```bash
# Dry run first
python scripts/deploy/failover_region.py failover \
  --config configs/failover-config.yaml \
  --prometheus-url http://prometheus:9090 \
  --to us-east-1 \
  --reason "Primary region outage" \
  --dry-run

# Actual failover
python scripts/deploy/failover_region.py failover \
  --config configs/failover-config.yaml \
  --prometheus-url http://prometheus:9090 \
  --to us-east-1 \
  --reason "Primary region outage"
```

### Manual Rollback

```bash
# Dry run first
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

## Regional Deployment

### Deploy to New Region

```bash
python scripts/deploy/deploy_region.py \
  --region us-east-1 \
  --cluster us-east-1-k8s \
  --values-file helm/ai-platform/values-multi-region.yaml
```

### Deploy with DNS Configuration

```bash
# Region config must include:
# - hosted_zone_id (for Route53)
# - gcp_project_id and gcp_dns_zone_name (for Cloud DNS)

python scripts/deploy/deploy_region.py \
  --region us-east-1 \
  --cluster us-east-1-k8s \
  --values-file helm/ai-platform/values-multi-region.yaml
```

## Systemd Service Setup

```bash
# Create service file
sudo tee /etc/systemd/system/multi-region-failover.service > /dev/null <<'EOF'
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

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable multi-region-failover
sudo systemctl start multi-region-failover

# Check status
sudo systemctl status multi-region-failover

# View logs
sudo journalctl -u multi-region-failover -f
```

## Monitoring Queries

### Check Region Health (Prometheus)

```bash
# Error rate
curl "http://prometheus:9090/api/v1/query?query=rate(http_requests_total{region='us-west-1',status=~'5..'}[5m])/rate(http_requests_total{region='us-west-1'}[5m])"

# Latency p95
curl "http://prometheus:9090/api/v1/query?query=histogram_quantile(0.95,rate(http_request_duration_seconds_bucket{region='us-west-1'}[5m]))"

# Availability
curl "http://prometheus:9090/api/v1/query?query=up{region='us-west-1'}"
```

### Check DNS Weights (Route53)

```bash
# List all records
aws route53 list-resource-record-sets \
  --hosted-zone-id Z1234567890ABC \
  --query "ResourceRecordSets[?Type=='A']"

# Check specific domain weights
aws route53 list-resource-record-sets \
  --hosted-zone-id Z1234567890ABC \
  --query "ResourceRecordSets[?Name=='ai-platform.example.com.']"
```

### Check DNS Weights (Cloud DNS)

```bash
# List records
gcloud dns record-sets list \
  --zone=ai-platform-zone \
  --filter="name:ai-platform.example.com"
```

## Troubleshooting

### Check Script Logs

```bash
# If running as systemd service
sudo journalctl -u multi-region-failover -f

# If running in foreground
tail -f /var/log/failover-monitor.log
```

### Test DNS Resolution

```bash
# Check DNS resolution
dig ai-platform.example.com
nslookup ai-platform.example.com

# Check from different DNS servers
dig @8.8.8.8 ai-platform.example.com
dig @1.1.1.1 ai-platform.example.com
```

### Test Region Health

```bash
# Primary
curl -v https://us-west-1.ai-platform.example.com/health

# Secondary
curl -v https://us-east-1.ai-platform.example.com/health

# Tertiary
curl -v https://eu-west-1.ai-platform.example.com/health
```

### Check Prometheus Connectivity

```bash
# Test query
curl "http://prometheus:9090/api/v1/query?query=up"

# Check if region metrics exist
curl "http://prometheus:9090/api/v1/label/region/values"
```

## Emergency Procedures

### Immediate Failover (Primary Down)

```bash
# 1. Verify secondary is healthy
curl https://us-east-1.ai-platform.example.com/health

# 2. Execute failover
python scripts/deploy/failover_region.py failover \
  --config configs/failover-config.yaml \
  --prometheus-url http://prometheus:9090 \
  --to us-east-1 \
  --reason "EMERGENCY: Primary region down"

# 3. Wait for DNS propagation
sleep 90

# 4. Verify failover
python scripts/deploy/failover_region.py status \
  --config configs/failover-config.yaml \
  --prometheus-url http://prometheus:9090
```

### Rollback After Recovery

```bash
# 1. Verify primary is healthy
curl https://us-west-1.ai-platform.example.com/health

# 2. Run smoke tests
curl -X POST https://us-west-1.ai-platform.example.com/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"test"}]}'

# 3. Execute rollback
python scripts/deploy/failover_region.py rollback \
  --config configs/failover-config.yaml \
  --prometheus-url http://prometheus:9090 \
  --to us-west-1

# 4. Wait for DNS propagation
sleep 90

# 5. Verify rollback
python scripts/deploy/failover_region.py status \
  --config configs/failover-config.yaml \
  --prometheus-url http://prometheus:9090
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Route53 / Cloud DNS                         │
│                Weighted Routing + Health Checks                 │
└────────────────┬────────────────┬──────────────┬────────────────┘
                 │                │              │
                 ▼                ▼              ▼
         ┌───────────────┐ ┌─────────────┐ ┌─────────────┐
         │  us-west-1    │ │  us-east-1  │ │  eu-west-1  │
         │  (Primary)    │ │ (Secondary) │ │ (Tertiary)  │
         │  Weight: 100  │ │  Weight: 0  │ │  Weight: 0  │
         └───────────────┘ └─────────────┘ └─────────────┘
                 │                │              │
                 ▼                ▼              ▼
         ┌───────────────┐ ┌─────────────┐ ┌─────────────┐
         │   Kubernetes  │ │  Kubernetes │ │  Kubernetes │
         │   + Services  │ │  + Services │ │  + Services │
         └───────────────┘ └─────────────┘ └─────────────┘
```

## Key Concepts

### DNS Weights

- **Weight 100**: Receives 100% of traffic (active)
- **Weight 0**: Receives 0% of traffic (standby)
- **Weights are relative**: 50/50 = equal split

### Health Checks

- **Path**: `/health`
- **Port**: 9002
- **Interval**: 30 seconds
- **Timeout**: 5 seconds
- **Unhealthy threshold**: 3 failures

### Failover Triggers

- Error rate > 5% for 3 consecutive checks
- Latency p95 > 1000ms for 3 consecutive checks
- Availability < 99% for 3 consecutive checks
- Prometheus critical alert

### Rollback Triggers

- Original primary recovers
- 5 consecutive successful health checks
- Automatic (if monitoring enabled)

## Best Practices

1. **Always test with --dry-run first**
2. **Verify secondary health before failover**
3. **Wait 90 seconds after DNS changes for propagation**
4. **Monitor metrics during and after failover**
5. **Document failover reasons in --reason flag**
6. **Run automated monitoring in production**
7. **Test failover procedures regularly (quarterly)**
8. **Keep runbook updated with lessons learned**

## Support

For detailed procedures, see: `docs/MULTI_REGION_FAILOVER_RUNBOOK.md`

For issues or questions:
- Slack: #sre-team
- PagerDuty: https://aiplatform.pagerduty.com
- On-call: oncall-sre@
