# Multi-Region DNS Failover System

## Overview

This directory contains the complete multi-region DNS failover automation system for the AI Platform. The system provides automatic and manual failover capabilities between geographic regions to ensure high availability and disaster recovery.

## Components

### 1. Regional Deployment Script (`deploy_region.py`)

Deploys the AI Platform to a new region with full DNS failover configuration.

**Features**:
- Kubernetes cluster deployment via Helm
- AWS Route53 integration with weighted routing
- Google Cloud DNS integration
- Health check configuration (HTTPS on port 9002)
- Automatic DNS weight assignment (primary=100, secondary=0)
- Cross-region data replication setup

**Usage**:
```bash
python scripts/deploy/deploy_region.py \
  --region us-east-1 \
  --cluster us-east-1-k8s \
  --values-file helm/ai-platform/values-multi-region.yaml
```

### 2. Failover Automation Script (`failover_region.py`)

Monitors region health via Prometheus and automatically performs DNS failover.

**Features**:
- Continuous health monitoring via Prometheus metrics
- Automatic failover on region degradation
- Automatic rollback when primary region recovers
- Manual failover and rollback commands
- Prometheus alert webhook integration
- Slack/webhook notifications
- Failover event history tracking

**Usage**:
```bash
# Automated monitoring
python scripts/deploy/failover_region.py monitor \
  --config configs/failover-config.yaml \
  --prometheus-url http://prometheus:9090

# Manual failover
python scripts/deploy/failover_region.py failover \
  --config configs/failover-config.yaml \
  --to us-east-1 \
  --reason "Primary region outage"

# Manual rollback
python scripts/deploy/failover_region.py rollback \
  --config configs/failover-config.yaml \
  --to us-west-1
```

### 3. Configuration File (`configs/failover-config.yaml`)

Central configuration for multi-region failover:
- Region definitions and priorities
- DNS provider settings (Route53 or Cloud DNS)
- Health check thresholds
- Failover/rollback criteria
- Notification webhooks

### 4. Documentation

- **`docs/MULTI_REGION_FAILOVER_RUNBOOK.md`**: Comprehensive operational runbook with procedures
- **`scripts/deploy/FAILOVER_QUICKSTART.md`**: Quick reference guide for common operations

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                       DNS Layer (Route53 / Cloud DNS)               │
│                     Weighted Routing + Health Checks                │
└────────────────┬────────────────┬──────────────┬────────────────────┘
                 │                │              │
                 │ Weight: 100    │ Weight: 0    │ Weight: 0
                 │ (Primary)      │ (Secondary)  │ (Tertiary)
                 │                │              │
                 ▼                ▼              ▼
         ┌───────────────┐ ┌──────────────┐ ┌──────────────┐
         │   us-west-1   │ │  us-east-1   │ │  eu-west-1   │
         │               │ │              │ │              │
         │  K8s Cluster  │ │  K8s Cluster │ │  K8s Cluster │
         │  + Services   │ │  + Services  │ │  + Services  │
         └───────┬───────┘ └──────┬───────┘ └──────┬───────┘
                 │                │              │
                 └────────────────┴──────────────┘
                          Cross-Region
                        Data Replication
```

## DNS Weighted Routing Strategy

### Normal Operation (Primary Healthy)

```
Region       Weight    Traffic
us-west-1    100       100%
us-east-1    0         0%
eu-west-1    0         0%
```

### After Failover (Primary Unhealthy)

```
Region       Weight    Traffic
us-west-1    0         0%
us-east-1    100       100%
eu-west-1    0         0%
```

### After Rollback (Primary Recovered)

```
Region       Weight    Traffic
us-west-1    100       100%
us-east-1    0         0%
eu-west-1    0         0%
```

## Health Check Configuration

Each region is monitored via:

- **HTTP Health Checks**: HTTPS requests to `/health` endpoint on port 9002
- **Check Interval**: 30 seconds
- **Timeout**: 5 seconds
- **Unhealthy Threshold**: 3 consecutive failures
- **Healthy Threshold**: 2 consecutive successes

## Prometheus Metrics

The failover system monitors:

### Error Rate
```promql
rate(http_requests_total{region="REGION",status=~"5.."}[5m]) 
/ 
rate(http_requests_total{region="REGION"}[5m])
```
**Threshold**: < 5%

### Latency (p95)
```promql
histogram_quantile(0.95, 
  rate(http_request_duration_seconds_bucket{region="REGION"}[5m])
)
```
**Threshold**: < 1000ms

### Availability
```promql
up{region="REGION"}
```
**Threshold**: >= 99%

## Failover Decision Logic

### Triggering Failover

Failover is triggered when **any** of these conditions are met:

1. **Metric-based**:
   - Error rate > 5% for 3 consecutive checks (default)
   - P95 latency > 1000ms for 3 consecutive checks
   - Availability < 99% for 3 consecutive checks

2. **Alert-based**:
   - Prometheus critical alert fires for primary region
   - Alert names: `HighErrorRate`, `HighLatency`, `ServiceDown`

3. **Manual**:
   - Operator initiates manual failover via CLI

### Triggering Rollback

Rollback to primary is triggered when:

1. **Automatic**:
   - Original primary region recovers
   - 5 consecutive successful health checks (default)
   - Current active region is not the original primary

2. **Manual**:
   - Operator initiates manual rollback via CLI

## DNS Propagation

- **DNS TTL**: 60 seconds
- **Health Check Detection**: 30-90 seconds
- **Total Failover Time**: 60-120 seconds
- **Global DNS Propagation**: Up to 5 minutes (varies by ISP)

## Security Considerations

### AWS Route53

Required IAM permissions:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "route53:GetHostedZone",
        "route53:ListResourceRecordSets",
        "route53:ChangeResourceRecordSets",
        "route53:GetChange",
        "route53:CreateHealthCheck",
        "route53:GetHealthCheck",
        "route53:DeleteHealthCheck"
      ],
      "Resource": "*"
    }
  ]
}
```

### Google Cloud DNS

Required IAM roles:
- `roles/dns.admin` or
- Custom role with: `dns.changes.create`, `dns.changes.get`, `dns.changes.list`, `dns.resourceRecordSets.*`

## Installation

### 1. Install Dependencies

```bash
pip install -r scripts/deploy/requirements-deploy.txt
```

This installs:
- `boto3>=1.26.0` (AWS Route53)
- `google-cloud-dns>=0.34.0` (Google Cloud DNS)
- `pyyaml>=6.0.1` (Configuration parsing)
- `requests>=2.31.0` (Prometheus API)
- `kubernetes>=28.1.0` (Kubernetes API)

### 2. Configure Credentials

**For AWS Route53**:
```bash
aws configure
# or
export AWS_ACCESS_KEY_ID=xxx
export AWS_SECRET_ACCESS_KEY=yyy
export AWS_DEFAULT_REGION=us-west-1
```

**For Google Cloud DNS**:
```bash
gcloud auth application-default login
# or
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
```

### 3. Configure Failover

Edit `configs/failover-config.yaml`:
```yaml
dns_provider: route53  # or cloud_dns
hosted_zone_id: Z1234567890ABC

regions:
  us-west-1:
    priority: 1
  us-east-1:
    priority: 2

thresholds:
  max_error_rate: 0.05
  max_latency_ms: 1000
  min_availability: 0.99
  consecutive_failures: 3
  consecutive_successes: 5
```

### 4. Deploy to Regions

```bash
# Deploy primary
python scripts/deploy/deploy_region.py \
  --region us-west-1 \
  --cluster us-west-1-k8s \
  --values-file helm/ai-platform/values-multi-region.yaml

# Deploy secondary
python scripts/deploy/deploy_region.py \
  --region us-east-1 \
  --cluster us-east-1-k8s \
  --values-file helm/ai-platform/values-multi-region.yaml
```

### 5. Start Failover Monitoring

```bash
# Start as systemd service (recommended for production)
sudo systemctl enable multi-region-failover
sudo systemctl start multi-region-failover

# Or run manually
python scripts/deploy/failover_region.py monitor \
  --config configs/failover-config.yaml \
  --prometheus-url http://prometheus:9090 \
  --interval 60
```

## Testing

### 1. Dry Run Testing

Always test with `--dry-run` first:

```bash
python scripts/deploy/failover_region.py failover \
  --config configs/failover-config.yaml \
  --to us-east-1 \
  --dry-run
```

### 2. Health Check Testing

Verify health checks are working:

```bash
# Check primary
curl https://us-west-1.ai-platform.example.com/health

# Check secondary
curl https://us-east-1.ai-platform.example.com/health
```

### 3. Prometheus Metrics Testing

Verify metrics are being collected:

```bash
curl "http://prometheus:9090/api/v1/query?query=up{region='us-west-1'}"
```

### 4. DNS Testing

Verify DNS records are configured:

```bash
# Route53
aws route53 list-resource-record-sets \
  --hosted-zone-id Z1234567890ABC

# Cloud DNS
gcloud dns record-sets list --zone=ai-platform-zone
```

## Monitoring

### Check Failover Status

```bash
python scripts/deploy/failover_region.py status \
  --config configs/failover-config.yaml \
  --prometheus-url http://prometheus:9090
```

### View Failover Service Logs

```bash
# Systemd service
sudo journalctl -u multi-region-failover -f

# Manual run
tail -f /var/log/failover-monitor.log
```

### Grafana Dashboard

Access the multi-region overview dashboard:
- URL: `https://grafana.ai-platform.example.com/d/multi-region-overview`
- Panels: Request rate, error rate, latency, DNS weights, failover timeline

## Troubleshooting

### Common Issues

1. **boto3 not available**
   ```bash
   pip install boto3>=1.26.0
   ```

2. **hosted_zone_id not configured**
   - Update `configs/failover-config.yaml` with your Route53 zone ID
   - Find it: `aws route53 list-hosted-zones`

3. **Health checks failing**
   - Verify firewall allows Route53 health checker IPs
   - Check `/health` endpoint returns HTTP 200
   - Verify TLS certificate is valid

4. **DNS changes not propagating**
   - Wait 60 seconds for TTL expiration
   - Check DNS cache: `dig ai-platform.example.com`
   - Verify Route53/Cloud DNS API call succeeded

For detailed troubleshooting, see `docs/MULTI_REGION_FAILOVER_RUNBOOK.md`.

## Operational Procedures

### Daily Operations

1. **Monitor dashboard**: Check Grafana for region health
2. **Review logs**: Check failover service logs daily
3. **Verify backups**: Ensure cross-region replication is working

### Weekly Operations

1. **Review failover history**: Check for unexpected failovers
2. **Test health checks**: Manually verify all regions healthy
3. **Update documentation**: Document any issues or changes

### Monthly Operations

1. **Test manual failover**: Practice failover procedures
2. **Review thresholds**: Adjust if needed based on metrics
3. **Update runbook**: Add lessons learned

### Quarterly Operations

1. **Full DR test**: Simulate complete primary region failure
2. **Load test**: Verify secondary regions can handle full traffic
3. **Security audit**: Review IAM permissions and access logs

## Best Practices

1. ✅ **Always use --dry-run** before making changes
2. ✅ **Verify secondary health** before initiating failover
3. ✅ **Wait for DNS propagation** (90 seconds) after changes
4. ✅ **Document failover reasons** using --reason flag
5. ✅ **Monitor metrics** during and after failover
6. ✅ **Run automated monitoring** in production (systemd service)
7. ✅ **Test regularly** (at least quarterly)
8. ✅ **Keep runbook updated** with lessons learned
9. ✅ **Use notifications** (Slack, PagerDuty) for alerts
10. ✅ **Review failover history** periodically

## Support

### Documentation

- **Runbook**: `docs/MULTI_REGION_FAILOVER_RUNBOOK.md` (detailed procedures)
- **Quick Start**: `scripts/deploy/FAILOVER_QUICKSTART.md` (common commands)
- **Deployment Guide**: `scripts/deploy/README.md` (general deployment info)

### Contact

- **Slack**: #sre-team
- **On-call**: oncall-sre@example.com
- **PagerDuty**: https://aiplatform.pagerduty.com
- **Status Page**: https://status.ai-platform.example.com

## License

Internal use only - AI Platform Infrastructure Team

## Changelog

| Date       | Version | Changes                                    |
|------------|---------|-------------------------------------------|
| 2024-01-15 | 1.0.0   | Initial implementation                    |
| 2024-01-20 | 1.1.0   | Added GCP Cloud DNS support               |
| 2024-02-01 | 1.2.0   | Added automatic rollback functionality    |

---

*Last Updated: 2024-01-15*  
*Maintained by: SRE Team*
