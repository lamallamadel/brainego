# AlertManager Configuration

This directory contains the AlertManager configuration for the AI Platform, including alert routing rules, notification receivers (Slack, Email), and on-call rotation setup.

## Files

- **alertmanager.yml**: Main AlertManager configuration with routing rules and receivers

## Configuration Overview

### Global Settings

The AlertManager is configured with:
- **Slack Integration**: Primary notification channel for all alerts
- **Email Integration**: Critical alerts and management notifications via SMTP
- **On-Call Rotation**: Primary and secondary on-call engineer notifications

### Alert Routing

Alerts are routed based on:
1. **Severity**: `critical` alerts trigger on-call notifications with email + Slack
2. **Component**: Different components route to different Slack channels
   - `kong`: Kong Gateway alerts → `#ai-platform-gateway`
   - `circuit-breaker`: Circuit breaker alerts → `#ai-platform-circuit-breaker`
   - `kubernetes`: Kubernetes infrastructure → `#ai-platform-k8s`
   - `drift-monitor`: Model drift detection → `#ai-platform-drift`
   - `gpu`: GPU monitoring → `#ai-platform-gpu`

### Receivers

#### Slack Receivers
- `slack-default`: General alerts
- `slack-critical`: Critical severity alerts
- `slack-kong`: Kong Gateway alerts
- `slack-circuit-breaker`: Circuit breaker alerts
- `slack-kubernetes`: Kubernetes infrastructure alerts
- `slack-gpu`: GPU monitoring alerts
- `slack-drift`: Model drift alerts
- `slack-safety`: Safety policy alerts
- `slack-budget`: Memory budget alerts
- `slack-infrastructure`: Infrastructure alerts

#### On-Call Critical
- Sends to Slack channel `#ai-platform-oncall` with `@channel` mentions
- Emails primary and secondary on-call engineers
- HTML-formatted email with high priority

#### Email Management
- Sends digest emails to management/stakeholders
- Plain HTML format for readability

### Environment Variables

Required environment variables (set via Kubernetes secrets):

```bash
# Slack (required)
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL

# SMTP (optional - for email notifications)
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=alertmanager@example.com
SMTP_PASSWORD=your-smtp-password

# On-Call Rotation (optional - for critical alerts)
ONCALL_EMAIL_PRIMARY=oncall-primary@example.com
ONCALL_EMAIL_SECONDARY=oncall-backup@example.com

# Management Notifications (optional)
MANAGEMENT_EMAIL_LIST=manager1@example.com,manager2@example.com
```

## Setting Up Secrets

### 1. Create Slack Webhook

1. Go to your Slack workspace settings
2. Navigate to Apps → Manage → Custom Integrations → Incoming Webhooks
3. Create a webhook for each channel (or use one webhook with channel overrides)
4. Base64 encode the webhook URL:

```bash
echo -n "https://hooks.slack.com/services/YOUR/WEBHOOK/URL" | base64
```

### 2. Configure SMTP (Optional)

For email notifications, configure your SMTP server credentials:

```bash
# Base64 encode credentials
echo -n "smtp.gmail.com" | base64
echo -n "587" | base64
echo -n "your-email@gmail.com" | base64
echo -n "your-app-password" | base64
```

### 3. Set On-Call Rotation (Optional)

```bash
# Base64 encode on-call emails
echo -n "oncall-primary@example.com" | base64
echo -n "oncall-secondary@example.com" | base64
echo -n "manager@example.com,director@example.com" | base64
```

### 4. Update Helm Values

Edit `helm/ai-platform/values.yaml`:

```yaml
secrets:
  alertmanager:
    slackWebhookUrl: "aHR0cHM6Ly9ob29rcy5zbGFjay5jb20vc2VydmljZXMvLi4u"  # REQUIRED
    smtpUsername: "eW91ci1lbWFpbEBnbWFpbC5jb20="  # optional
    smtpPassword: "eW91ci1hcHAtcGFzc3dvcmQ="  # optional
    oncallEmailPrimary: "b25jYWxsLXByaW1hcnlAZXhhbXBsZS5jb20="  # optional
    oncallEmailSecondary: "b25jYWxsLXNlY29uZGFyeUBleGFtcGxlLmNvbQ=="  # optional
    managementEmailList: "bWFuYWdlckBleGFtcGxlLmNvbQ=="  # optional

alertmanager:
  enabled: true
  email:
    enabled: true  # Set to false if not using email
    smtp_host: "smtp.gmail.com"
    smtp_port: "587"
```

## Alert Definitions

Alert rules are defined in `configs/prometheus/alerts/`:

- **kong-alerts.yml**: Kong Gateway alerts (rate limiting, errors, latency)
- **circuit-breaker-alerts.yml**: Circuit breaker state and rejection alerts
- **kubernetes-alerts.yml**: Pod restarts, memory pressure, OOM kills
- **drift-alerts.yml**: Model drift detection and data quality

## Testing Alerts

Use the manual trigger script to test alert delivery:

```bash
# List available test alerts
python scripts/trigger_test_alert.py --list-alerts

# Trigger a Kong rate limit alert
python scripts/trigger_test_alert.py --alert-type kong-rate-limit

# Trigger a critical circuit breaker alert
python scripts/trigger_test_alert.py --alert-type circuit-breaker --severity critical

# Trigger a memory pressure alert
python scripts/trigger_test_alert.py --alert-type memory-pressure

# Trigger an alert with auto-resolve after 10 seconds
python scripts/trigger_test_alert.py --alert-type drift-detected --resolve

# Trigger with custom labels
python scripts/trigger_test_alert.py --alert-type pod-restart --custom-label namespace=production --custom-label pod=critical-service
```

## Monitoring AlertManager

### Health Check

```bash
# Check AlertManager health
curl http://alertmanager:9093/-/healthy

# Check readiness
curl http://alertmanager:9093/-/ready
```

### View Active Alerts

```bash
# List all active alerts
curl http://alertmanager:9093/api/v2/alerts
```

### Silence Alerts

```bash
# Create a silence (via API or UI)
curl -X POST http://alertmanager:9093/api/v2/silences -d '{
  "matchers": [{"name": "alertname", "value": "KongRateLimitExceeded", "isRegex": false}],
  "startsAt": "2024-01-01T00:00:00Z",
  "endsAt": "2024-01-01T01:00:00Z",
  "createdBy": "admin",
  "comment": "Maintenance window"
}'
```

## Troubleshooting

### Alerts Not Sending to Slack

1. Verify Slack webhook URL is correct:
```bash
kubectl get secret alertmanager-secrets -n ai-platform -o jsonpath='{.data.slack-webhook-url}' | base64 -d
```

2. Check AlertManager logs:
```bash
kubectl logs -n ai-platform deployment/alertmanager -f
```

3. Test webhook manually:
```bash
curl -X POST -H 'Content-type: application/json' \
  --data '{"text":"Test from AlertManager"}' \
  YOUR_SLACK_WEBHOOK_URL
```

### Emails Not Sending

1. Verify SMTP configuration:
```bash
kubectl get secret alertmanager-secrets -n ai-platform -o yaml
```

2. Check SMTP connectivity:
```bash
kubectl exec -n ai-platform deployment/alertmanager -- nc -zv smtp.example.com 587
```

3. Review AlertManager logs for SMTP errors

### Alerts Not Routing Correctly

1. Check AlertManager config:
```bash
kubectl get configmap alertmanager-config -n ai-platform -o yaml
```

2. Verify route matching in logs:
```bash
kubectl logs -n ai-platform deployment/alertmanager | grep -i route
```

## Best Practices

1. **Slack Channels**: Create dedicated channels for different alert types
2. **On-Call Rotation**: Keep email distribution lists updated
3. **Alert Fatigue**: Use inhibition rules to suppress redundant alerts
4. **Runbooks**: Link all alerts to runbook documentation
5. **Testing**: Regularly test alert delivery with manual triggers
6. **Silence Management**: Document maintenance windows and create silences proactively

## References

- [Prometheus AlertManager Documentation](https://prometheus.io/docs/alerting/latest/alertmanager/)
- [Slack Incoming Webhooks](https://api.slack.com/messaging/webhooks)
- [Email Configuration Guide](https://prometheus.io/docs/alerting/latest/configuration/#email_config)
