# AlertManager Deployment Quickstart

This guide provides step-by-step instructions to deploy Prometheus AlertManager with Slack and email integration for the AI Platform.

## Prerequisites

- Kubernetes cluster with Helm 3.x installed
- Slack workspace with admin access
- SMTP server credentials (optional, for email notifications)
- `kubectl` configured to access your cluster

## Quick Start (5 minutes)

### 1. Create Slack Webhook

1. Go to https://api.slack.com/apps
2. Click "Create New App" → "From scratch"
3. Name it "AI Platform AlertManager"
4. Select your workspace
5. Go to "Incoming Webhooks" → Enable
6. Click "Add New Webhook to Workspace"
7. Select channel (e.g., `#ai-platform-alerts`)
8. Copy the webhook URL

### 2. Configure Secrets

Base64 encode your Slack webhook URL:

```bash
echo -n "https://hooks.slack.com/services/YOUR/WEBHOOK/URL" | base64
```

Edit `helm/ai-platform/values.yaml` and update:

```yaml
secrets:
  alertmanager:
    slackWebhookUrl: "YOUR_BASE64_ENCODED_WEBHOOK_URL"  # REQUIRED
```

### 3. Deploy AlertManager

```bash
# Install/upgrade the Helm chart
helm upgrade --install ai-platform ./helm/ai-platform \
  --namespace ai-platform \
  --create-namespace

# Verify deployment
kubectl get pods -n ai-platform | grep alertmanager
kubectl get svc -n ai-platform | grep alertmanager
```

### 4. Test Alert Delivery

```bash
# List available test alerts
python scripts/trigger_test_alert.py --list-alerts

# Trigger a test alert
python scripts/trigger_test_alert.py --alert-type kong-rate-limit

# Check Slack channel for alert notification
```

## Full Setup with Email (10 minutes)

### 1. Configure SMTP Credentials

For Gmail (example):

```bash
# Generate app password at https://myaccount.google.com/apppasswords
# Base64 encode credentials
echo -n "your-email@gmail.com" | base64
echo -n "your-app-password" | base64
```

Update `helm/ai-platform/values.yaml`:

```yaml
secrets:
  alertmanager:
    slackWebhookUrl: "YOUR_BASE64_ENCODED_WEBHOOK_URL"
    smtpUsername: "YOUR_BASE64_ENCODED_EMAIL"
    smtpPassword: "YOUR_BASE64_ENCODED_PASSWORD"
    oncallEmailPrimary: "b25jYWxsQGV4YW1wbGUuY29t"  # oncall@example.com
    oncallEmailSecondary: "YmFja3VwQGV4YW1wbGUuY29t"  # backup@example.com

alertmanager:
  enabled: true
  email:
    enabled: true
    smtp_host: "smtp.gmail.com"
    smtp_port: "587"
```

### 2. Redeploy with Email Support

```bash
helm upgrade --install ai-platform ./helm/ai-platform \
  --namespace ai-platform
```

### 3. Test Critical Alert (with Email)

```bash
# Trigger critical alert (will send email + Slack)
python scripts/trigger_test_alert.py \
  --alert-type critical-service-down \
  --severity critical

# Check both Slack and email for notifications
```

## Configuration Files

### AlertManager Deployment

- **Helm Template**: `helm/ai-platform/templates/alertmanager-deployment.yaml`
- **Values**: `helm/ai-platform/values.yaml` (alertmanager section)
- **Service Account**: Defined in RBAC section

### Alert Configuration

- **Routing Rules**: `configs/alertmanager/alertmanager.yml`
- **Alert Definitions**: `configs/prometheus/alerts/`
  - `kong-alerts.yml` - Kong Gateway alerts
  - `circuit-breaker-alerts.yml` - Circuit breaker alerts
  - `kubernetes-alerts.yml` - Pod/container alerts
  - `drift-alerts.yml` - ML drift detection

### Secrets

- **Kubernetes Secret**: `alertmanager-secrets` (namespace: ai-platform)
- **Fields**:
  - `slack-webhook-url` - Slack integration
  - `smtp-username` - Email username
  - `smtp-password` - Email password
  - `oncall-email-primary` - Primary on-call engineer
  - `oncall-email-secondary` - Backup on-call engineer
  - `management-email-list` - Management distribution list

## Alert Types and Routing

### Kong Gateway Alerts

- **KongRateLimitExceeded** - Rate limit 429 responses
- **KongHighErrorRate** - 5xx error rate > 5%
- **KongHighLatency** - P95 latency > 2s
- **KongUpstreamConnectionFailures** - Unhealthy upstreams
- **KongServiceUnavailable** - All upstreams down

**Routes to**: `#ai-platform-gateway`

### Circuit Breaker Alerts

- **CircuitBreakerOpen** - Circuit breaker open state
- **CircuitBreakerOpenExtended** - Open > 10 minutes (critical)
- **CircuitBreakerHighRejectionRate** - >50% requests rejected
- **CircuitBreakerTripRateSpike** - Frequent trips

**Routes to**: `#ai-platform-circuit-breaker`

### Kubernetes Alerts

- **PodRestartRateHigh** - Restart rate > 0.1/sec
- **PodRestartRateCritical** - Restart rate > 0.3/sec (critical)
- **MemoryPressureDetected** - Memory usage > 90%
- **MemoryPressureCritical** - Memory usage > 95% (OOM imminent)
- **PodOOMKilled** - Container killed by OOM
- **PodCrashLoopBackOff** - Pod in crash loop

**Routes to**: `#ai-platform-k8s`

### Drift Detection Alerts

- **DriftDetected** - Drift score > 0.15
- **HighDriftScore** - Drift score > 0.25 (critical)
- **FeatureDriftDetected** - Input distribution changed
- **PredictionDriftDetected** - Output distribution changed
- **EvalScoreDropCritical** - Eval score dropped > 12%

**Routes to**: `#ai-platform-drift`

## Accessing AlertManager UI

### Port Forward (Development)

```bash
kubectl port-forward -n ai-platform svc/alertmanager 9093:9093
```

Open browser: http://localhost:9093

### Features

- View active alerts
- Create silences for maintenance windows
- View alert history
- Test notification receivers
- Debug routing rules

## Monitoring and Troubleshooting

### Check AlertManager Health

```bash
# Health check
kubectl exec -n ai-platform deployment/alertmanager -- \
  wget -qO- http://localhost:9093/-/healthy

# View active alerts
kubectl exec -n ai-platform deployment/alertmanager -- \
  wget -qO- http://localhost:9093/api/v2/alerts | jq
```

### View Logs

```bash
# Real-time logs
kubectl logs -n ai-platform deployment/alertmanager -f

# Last 100 lines
kubectl logs -n ai-platform deployment/alertmanager --tail=100
```

### Common Issues

#### Slack Webhooks Not Working

**Symptom**: Alerts not appearing in Slack

**Solution**:
1. Verify webhook URL is correct:
```bash
kubectl get secret alertmanager-secrets -n ai-platform \
  -o jsonpath='{.data.slack-webhook-url}' | base64 -d
```

2. Test webhook manually:
```bash
WEBHOOK_URL=$(kubectl get secret alertmanager-secrets -n ai-platform \
  -o jsonpath='{.data.slack-webhook-url}' | base64 -d)

curl -X POST -H 'Content-type: application/json' \
  --data '{"text":"Test from AlertManager"}' \
  "$WEBHOOK_URL"
```

#### Emails Not Sending

**Symptom**: Email notifications not received

**Solution**:
1. Check SMTP connectivity from pod:
```bash
kubectl exec -n ai-platform deployment/alertmanager -- \
  nc -zv smtp.gmail.com 587
```

2. Verify SMTP credentials are correct
3. Check AlertManager logs for SMTP errors

#### Alerts Not Routing

**Symptom**: Alerts sent but to wrong channel

**Solution**:
1. Check alert labels match routing rules:
```bash
kubectl logs -n ai-platform deployment/alertmanager | grep -i route
```

2. Verify alert component label:
```bash
python scripts/trigger_test_alert.py --alert-type kong-rate-limit
kubectl logs -n ai-platform deployment/alertmanager --tail=50
```

## Manual Alert Triggers

### Test All Alert Types

```bash
# Kong rate limit
python scripts/trigger_test_alert.py --alert-type kong-rate-limit

# Circuit breaker
python scripts/trigger_test_alert.py --alert-type circuit-breaker

# Pod restart
python scripts/trigger_test_alert.py --alert-type pod-restart

# Memory pressure
python scripts/trigger_test_alert.py --alert-type memory-pressure

# Drift detection
python scripts/trigger_test_alert.py --alert-type drift-detected

# Critical service down (triggers on-call)
python scripts/trigger_test_alert.py --alert-type critical-service-down --severity critical
```

### Custom Alert with Labels

```bash
python scripts/trigger_test_alert.py \
  --alert-type memory-pressure \
  --custom-label namespace=production \
  --custom-label pod=critical-api-server \
  --severity critical \
  --resolve
```

## Production Checklist

- [ ] Slack webhook configured and tested
- [ ] SMTP credentials configured (if using email)
- [ ] On-call rotation emails updated
- [ ] Test alerts sent to all receivers
- [ ] AlertManager deployment healthy
- [ ] Prometheus scraping AlertManager metrics
- [ ] Alert routing rules validated
- [ ] Runbook URLs updated in alert definitions
- [ ] Team trained on alert response procedures
- [ ] Silence management process documented

## Next Steps

1. **Customize Alert Thresholds**: Edit `configs/prometheus/alerts/*.yml` to adjust thresholds
2. **Add More Receivers**: Extend `configs/alertmanager/alertmanager.yml` with PagerDuty, OpsGenie, etc.
3. **Create Runbooks**: Document alert response procedures
4. **Set Up Dashboards**: Create Grafana dashboards for alert visualization
5. **Test Failure Scenarios**: Run chaos tests to validate alert delivery

## References

- [AlertManager Configuration Guide](configs/alertmanager/README.md)
- [Alert Definitions](configs/prometheus/alerts/)
- [Manual Trigger Script](scripts/trigger_test_alert.py)
- [Helm Chart Values](helm/ai-platform/values.yaml)
