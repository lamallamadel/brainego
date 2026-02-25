# Observability Stack

Complete observability solution for the AI Platform with Prometheus, OpenTelemetry, Loki, and AlertManager.

## Features

✅ **Metrics (Prometheus)**
- 15-second scrape interval
- 90-day retention
- Custom metrics for MAX Serve, MCPJungle, Memory Engine
- GPU monitoring
- Infrastructure metrics (Redis, PostgreSQL, Qdrant)

✅ **Distributed Tracing (OpenTelemetry)**
- Full request path: Gateway → Router → MAX → MCP → Memory
- OTLP, Jaeger, and Zipkin support
- Automatic trace context propagation
- Span enrichment and filtering

✅ **Structured Logs (Loki)**
- JSON-formatted logs with trace context
- 90-day retention
- Automatic label extraction
- Real-time log streaming

✅ **Alerting (AlertManager)**
- Slack webhook integration
- Multi-channel routing (critical, GPU, drift, budget, infra)
- Alert grouping and deduplication
- Configurable thresholds

## Quick Start

### 1. Setup

```bash
# Copy environment template
cp .env.observability.example .env.observability

# Edit with your Slack webhook URL
nano .env.observability
```

### 2. Start Services

```bash
# Make scripts executable
chmod +x start_observability.sh test_observability.sh

# Start observability stack
./start_observability.sh
```

### 3. Verify

```bash
# Test all components
./test_observability.sh
```

### 4. Access Dashboards

- **Prometheus**: http://localhost:9090
- **Grafana**: http://localhost:3000 (admin/admin)
- **Jaeger**: http://localhost:16686
- **AlertManager**: http://localhost:9093

## Alert Thresholds

| Alert | Threshold | Duration | Severity |
|-------|-----------|----------|----------|
| Latency > 2s | P95 > 2s | 2 min | Warning |
| Error Rate > 1% | >1% errors | 2 min | Critical |
| GPU > 90% | Utilization >90% | 5 min | Warning |
| Drift Detected | Score >0.15 | 1 min | Warning |
| Budget Exceeded | >100% used | 1 min | Critical |
| Service Down | Health check fails | 2 min | Critical |

## Custom Metrics

### HTTP Metrics
```python
from metrics_exporter import get_metrics_exporter

metrics = get_metrics_exporter('my-service')
metrics.record_http_request('POST', '/api/endpoint', 200, 0.125)
```

### Inference Metrics
```python
metrics.record_inference(
    model='llama-3.3-8b',
    status='success',
    duration=0.250,
    prompt_tokens=100,
    completion_tokens=50
)
```

### MCP Metrics
```python
metrics.record_mcp_operation(
    server='github',
    operation='search',
    status='success',
    duration=0.050
)
```

### Drift Metrics
```python
metrics.update_drift_score(
    model='llama-3.3-8b',
    score=0.18,
    status='warning',
    duration=5.0
)
```

### Budget Metrics
```python
metrics.update_budget(
    session_id='session123',
    total_bytes=1000000,
    used_bytes=750000
)
```

## Structured Logging

### Setup
```python
from structured_logger import setup_structured_logging, get_structured_logger

setup_structured_logging('my-service', level=logging.INFO)
logger = get_structured_logger(__name__)
```

### Usage
```python
# HTTP requests
logger.log_request('POST', '/api/endpoint', 200, 125.5)

# Inference
logger.log_inference('llama-3.3-8b', 250.5, batch_size=4)

# MCP operations
logger.log_mcp_operation('github', 'search', 50.0, status='success')

# Drift detection
logger.log_drift('llama-3.3-8b', 0.18, 0.15)

# Generic with fields
logger.info("Processing request", user_id="user123", request_id="req456")
```

## Trace Context

### Setup OpenTelemetry
```python
from structured_logger import set_trace_context
from opentelemetry import trace

span = trace.get_current_span()
trace_id = format(span.get_span_context().trace_id, '032x')
span_id = format(span.get_span_context().span_id, '016x')

set_trace_context(trace_id, span_id)
```

## Query Examples

### Prometheus (PromQL)

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

### Loki (LogQL)

**Recent errors**:
```logql
{job="gateway"} | json | level="ERROR"
```

**Slow requests**:
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

## Slack Configuration

Create these channels in your Slack workspace:

1. **#ai-platform-alerts** - Default alerts
2. **#ai-platform-critical** - Critical alerts (@channel)
3. **#ai-platform-gpu** - GPU alerts
4. **#ai-platform-drift** - Drift detection
5. **#ai-platform-budget** - Budget alerts
6. **#ai-platform-infra** - Infrastructure alerts

Get webhook URL from: https://api.slack.com/apps

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Applications                         │
│  (Gateway, MAX Serve, MCPJungle, Memory, etc.)         │
└───────────┬─────────────────┬─────────────────┬─────────┘
            │                 │                 │
            ▼                 ▼                 ▼
    ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
    │  Prometheus  │  │ OpenTelemetry│  │   Promtail   │
    │  (Metrics)   │  │  Collector   │  │ (Log Agent)  │
    └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
           │                 │                  │
           │                 ▼                  │
           │         ┌──────────────┐           │
           │         │    Jaeger    │           │
           │         │   (Traces)   │           │
           │         └──────────────┘           │
           │                                    │
           ▼                                    ▼
    ┌──────────────┐                   ┌──────────────┐
    │ AlertManager │                   │     Loki     │
    │   (Alerts)   │                   │    (Logs)    │
    └──────┬───────┘                   └──────┬───────┘
           │                                   │
           ▼                                   │
    ┌──────────────┐                          │
    │    Slack     │                          │
    │  (Webhooks)  │                          │
    └──────────────┘                          │
                                               │
                    ┌──────────────────────────┘
                    │
                    ▼
            ┌──────────────┐
            │   Grafana    │
            │ (Dashboards) │
            └──────────────┘
```

## Data Flow

### Metrics Flow
```
Service → /metrics endpoint → Prometheus → AlertManager → Slack
                                    ↓
                                 Grafana
```

### Traces Flow
```
Service → OTLP → OpenTelemetry Collector → Jaeger
                                    ↓
                                 Grafana
```

### Logs Flow
```
Service → stdout (JSON) → Docker → Promtail → Loki → Grafana
```

## Ports

| Service | Port | Purpose |
|---------|------|---------|
| Prometheus | 9090 | Metrics & UI |
| Grafana | 3000 | Dashboards |
| Loki | 3100 | Log ingestion |
| Promtail | 9080 | Log collection |
| AlertManager | 9093 | Alert management |
| OTel Collector | 4317 | OTLP gRPC |
| OTel Collector | 4318 | OTLP HTTP |
| OTel Collector | 8888 | Metrics |
| OTel Collector | 13133 | Health |
| Jaeger | 16686 | UI |
| Redis Exporter | 9121 | Metrics |
| PostgreSQL Exporter | 9187 | Metrics |
| GPU Exporter | 9835 | Metrics |

## Retention

- **Prometheus**: 90 days
- **Loki**: 90 days (2160 hours)
- **Jaeger**: Persistent (Badger storage)
- **AlertManager**: Active alerts only

## Troubleshooting

### Metrics not appearing
```bash
# Check Prometheus targets
curl http://localhost:9090/api/v1/targets | jq

# Check service health
docker compose ps

# View Prometheus logs
docker compose logs prometheus
```

### Logs not appearing
```bash
# Check Loki
curl http://localhost:3100/ready

# Check Promtail
docker compose logs promtail

# Test log query
curl -G "http://localhost:3100/loki/api/v1/query" \
  --data-urlencode 'query={job="gateway"}'
```

### Traces not appearing
```bash
# Check OTel Collector
curl http://localhost:13133

# View collector logs
docker compose logs otel-collector

# Check Jaeger
open http://localhost:16686
```

### Alerts not firing
```bash
# Check AlertManager
curl http://localhost:9093/api/v2/status

# Check alert rules
curl http://localhost:9090/api/v1/rules | jq

# View AlertManager logs
docker compose logs alertmanager
```

## Performance

### Prometheus
- Scrape interval: 15s (configurable)
- Memory usage: ~500MB (depends on cardinality)
- Disk usage: ~1GB per day

### Loki
- Ingestion rate: 16 MB/s
- Memory usage: ~512MB
- Disk usage: ~2GB per day

### OpenTelemetry Collector
- Batch size: 1024 spans
- Memory limit: 512 MiB
- CPU: ~0.5 core

## Security

⚠️ **Production Recommendations**:

1. Change Grafana admin password
2. Enable authentication on Prometheus
3. Use TLS for all services
4. Restrict network access
5. Rotate Slack webhooks regularly
6. Implement RBAC in Grafana

## Integration Example

See `examples/observability_integration_example.py` for complete integration example.

## Documentation

- [Implementation Guide](OBSERVABILITY_IMPLEMENTATION.md)
- [Quick Start](OBSERVABILITY_QUICKSTART.md)
- [Files Created](OBSERVABILITY_FILES_CREATED.md)

## Support

For issues:
1. Check service logs: `docker compose logs <service>`
2. Verify configs in `configs/`
3. Test connectivity: `./test_observability.sh`
4. Review Prometheus targets: http://localhost:9090/targets

## License

Same as the main project.
