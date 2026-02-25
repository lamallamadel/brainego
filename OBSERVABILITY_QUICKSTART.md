# Observability Stack - Quick Start Guide

## Prerequisites

- Docker and Docker Compose installed
- NVIDIA GPU with drivers (for GPU metrics)
- Slack workspace (for alert notifications)

## Setup

### 1. Configure Slack Webhook (Optional)

Create a Slack webhook URL:
1. Go to https://api.slack.com/apps
2. Create a new app or select existing
3. Enable "Incoming Webhooks"
4. Create webhook for each channel
5. Copy webhook URL

Set environment variable:
```bash
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
```

### 2. Start Observability Stack

Start all services:
```bash
docker compose up -d
```

Start only observability services:
```bash
docker compose up -d prometheus grafana loki promtail alertmanager otel-collector
```

### 3. Verify Services

Check all services are running:
```bash
docker compose ps
```

Expected services:
- ✅ prometheus
- ✅ grafana
- ✅ loki
- ✅ promtail
- ✅ alertmanager
- ✅ otel-collector
- ✅ jaeger
- ✅ redis-exporter
- ✅ postgres-exporter
- ✅ nvidia-gpu-exporter

### 4. Access Dashboards

**Prometheus**:
```bash
open http://localhost:9090
```

**Grafana** (admin/admin):
```bash
open http://localhost:3000
```

**Jaeger**:
```bash
open http://localhost:16686
```

**AlertManager**:
```bash
open http://localhost:9093
```

## Quick Checks

### 1. Verify Metrics Collection

Check Prometheus targets:
```bash
curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | {job: .labels.job, health: .health}'
```

All targets should show `health: "up"`.

### 2. Verify Logs Collection

Query Loki for recent logs:
```bash
curl -G -s "http://localhost:3100/loki/api/v1/query" \
  --data-urlencode 'query={job="gateway"}' | jq
```

### 3. Verify Traces

Open Jaeger UI and search for traces:
```bash
open http://localhost:16686
```

### 4. Test Alerts

Trigger a test alert by querying a high metric:
```bash
# Check active alerts in Prometheus
curl http://localhost:9090/api/v1/alerts | jq '.data.alerts[] | {alertname: .labels.alertname, state: .state}'
```

## Using Metrics in Your Code

### Python Example

```python
from metrics_exporter import get_metrics_exporter
import time

# Initialize metrics
metrics = get_metrics_exporter('my-service')

# Record HTTP request
start = time.time()
# ... process request ...
duration = time.time() - start
metrics.record_http_request('POST', '/api/endpoint', 200, duration)

# Record custom inference
metrics.record_inference(
    model='llama-3.3-8b',
    status='success',
    duration=0.250,
    prompt_tokens=100,
    completion_tokens=50
)

# Update drift score
metrics.update_drift_score(
    model='llama-3.3-8b',
    score=0.12,
    status='normal',
    duration=5.0
)
```

## Using Structured Logging

### Python Example

```python
from structured_logger import setup_structured_logging, get_structured_logger
import logging

# Setup structured logging for your service
setup_structured_logging('my-service', level=logging.INFO)

# Get logger
logger = get_structured_logger(__name__)

# Log HTTP request
logger.log_request(
    method='POST',
    endpoint='/api/endpoint',
    status_code=200,
    duration_ms=125.5,
    user_id='user123'
)

# Log with extra fields
logger.info("Processing request", 
           request_id="req123",
           user_id="user456")
```

## Common Queries

### Prometheus Queries

**Request rate**:
```promql
rate(http_requests_total[5m])
```

**P95 latency**:
```promql
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))
```

**Error rate**:
```promql
rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m]) * 100
```

**GPU utilization**:
```promql
nvidia_gpu_duty_cycle
```

**Drift score**:
```promql
drift_score
```

### Loki Queries (LogQL)

**Recent errors**:
```logql
{job="gateway"} | json | level="ERROR"
```

**Slow requests (>1s)**:
```logql
{job="gateway"} | json | duration_ms > 1000
```

**MCP operations**:
```logql
{job="mcpjungle-gateway"} | json | mcp_operation!=""
```

**Drift alerts**:
```logql
{job="drift-monitor"} | json | drift_score > 0.15
```

## Grafana Setup

### Add Data Sources

1. Go to Configuration > Data Sources
2. Add Prometheus:
   - URL: `http://prometheus:9090`
   - Save & Test

3. Add Loki:
   - URL: `http://loki:3100`
   - Save & Test

### Import Dashboards

1. Go to Dashboards > Import
2. Upload dashboard JSON from `configs/grafana/dashboards/`
3. Select Prometheus data source
4. Import

## Alert Testing

### Test Latency Alert

Send slow requests to trigger latency alert:
```bash
# Send 100 requests
for i in {1..100}; do
  curl -X POST http://localhost:9002/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d '{"model":"llama-3.3-8b-instruct","messages":[{"role":"user","content":"test"}]}'
done
```

### Test Drift Alert

Update drift score (if you have drift monitor running):
```bash
curl -X POST http://localhost:8004/api/drift/test \
  -H "Content-Type: application/json" \
  -d '{"drift_score": 0.20}'
```

### View Alerts

Check AlertManager:
```bash
open http://localhost:9093/#/alerts
```

## Troubleshooting

### No Metrics Appearing

```bash
# Check Prometheus targets
curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | select(.health != "up")'

# Check service logs
docker compose logs prometheus
docker compose logs <service-name>
```

### No Logs Appearing

```bash
# Check Promtail
docker compose logs promtail

# Test Loki
curl http://localhost:3100/ready

# Check log files
docker compose logs <service-name>
```

### No Traces Appearing

```bash
# Check OTel Collector
curl http://localhost:13133
docker compose logs otel-collector

# Check Jaeger
docker compose logs jaeger
```

### Alerts Not Firing

```bash
# Check AlertManager
curl http://localhost:9093/api/v2/status

# Check alert rules
curl http://localhost:9090/api/v1/rules | jq '.data.groups[].rules[] | select(.type == "alerting")'

# Check Prometheus logs
docker compose logs prometheus
```

## Cleanup

Stop observability stack:
```bash
docker compose stop prometheus grafana loki promtail alertmanager otel-collector
```

Remove volumes (WARNING: deletes all data):
```bash
docker compose down -v
```

## Next Steps

1. ✅ Configure Slack webhooks for alerts
2. ✅ Create custom Grafana dashboards
3. ✅ Set up alert routing rules
4. ✅ Implement custom metrics in your services
5. ✅ Configure log retention policies
6. ✅ Set up backup for metrics and logs

## Resources

- **Prometheus Documentation**: https://prometheus.io/docs/
- **Grafana Documentation**: https://grafana.com/docs/
- **Loki Documentation**: https://grafana.com/docs/loki/
- **OpenTelemetry Documentation**: https://opentelemetry.io/docs/
- **AlertManager Documentation**: https://prometheus.io/docs/alerting/latest/alertmanager/

## Support

For issues or questions:
1. Check service logs: `docker compose logs <service>`
2. Verify configuration files in `configs/`
3. Review alert rules in `configs/prometheus/rules/`
4. Check Prometheus targets: http://localhost:9090/targets
