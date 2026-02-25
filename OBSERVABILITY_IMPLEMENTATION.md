# Observability Stack Implementation

## Overview

Complete observability stack with Prometheus, OpenTelemetry Collector, Loki, and AlertManager for monitoring the AI Platform.

## Components

### 1. Prometheus (Metrics)
- **Scrape Interval**: 15 seconds
- **Retention**: 90 days
- **Metrics Sources**:
  - Gateway (HTTP requests, latency)
  - MCPJungle Gateway (MCP operations, tracing)
  - API Server (requests, routing)
  - MAX Serve (inference, GPU, batching)
  - Memory Engine (operations, budget)
  - Learning Engine (training, drift)
  - Drift Monitor (drift scores, checks)
  - Infrastructure (Redis, PostgreSQL, Qdrant, GPU)

### 2. OpenTelemetry Collector (Tracing)
- **Distributed Tracing**: Gateway → Router → MAX → MCP → Memory
- **Receivers**:
  - OTLP (gRPC: 4317, HTTP: 4318)
  - Jaeger (14250, 14268, 6831, 6832)
  - Zipkin (9411)
- **Exporters**:
  - Jaeger (traces)
  - Loki (logs)
  - Prometheus (metrics)
- **Features**:
  - Batch processing
  - Memory limiting
  - Span enrichment
  - Resource attributes

### 3. Loki (Logs)
- **Retention**: 90 days (2160 hours)
- **Log Format**: Structured JSON
- **Sources**:
  - All Docker containers via Promtail
  - OpenTelemetry Collector
- **Features**:
  - Label extraction from JSON
  - Automatic retention cleanup
  - Query optimization

### 4. Promtail (Log Collection)
- **Collection**: Docker container logs
- **Pipeline Stages**:
  - JSON parsing
  - Label extraction
  - Timestamp parsing
- **Labels**: level, logger, service-specific fields

### 5. AlertManager (Alerting)
- **Channels**: Slack webhooks
- **Alert Types**:
  - Critical: Immediate notification
  - GPU: GPU-specific channel
  - Drift: Drift detection channel
  - Budget: Budget alerts channel
  - Infrastructure: Service health channel

## Alert Rules

### Latency Alerts (threshold: 2s)
- **HighGatewayLatency**: Gateway P95 latency > 2s
- **HighMCPJungleLatency**: MCPJungle P95 latency > 2s
- **HighMaxServeLatency**: MAX Serve inference P95 latency > 2s
- **HighMemoryEngineLatency**: Memory Engine P95 latency > 2s

### Error Rate Alerts (threshold: 1%)
- **HighErrorRate**: HTTP error rate > 1%
- **HighMaxServeErrorRate**: MAX Serve error rate > 1%
- **HighMCPErrorRate**: MCP error rate > 1%

### GPU Alerts
- **HighGPUUtilization**: GPU utilization > 90% (5min)
- **HighGPUMemory**: GPU memory > 90% (5min)
- **HighGPUTemperature**: GPU temperature > 85°C (5min)

### Drift Alerts
- **DriftDetected**: Drift score > 0.15 (1min)
- **HighDriftScore**: Drift score > 0.25 (1min) - critical

### Budget Alerts
- **BudgetExceeded**: Memory budget exceeded (1min)
- **BudgetWarning**: Memory budget > 80% (5min)

### Service Health Alerts
- **ServiceDown**: Service unavailable (2min)
- **HighRequestQueueDepth**: Queue depth > 100 (5min)

### Database Alerts
- **PostgreSQLPoolExhausted**: Connections > 90 (5min)
- **RedisMemoryHigh**: Redis memory > 90% (5min)

## Custom Metrics

### HTTP Metrics
```python
http_requests_total{method, endpoint, status}
http_request_duration_seconds{method, endpoint}
```

### Inference Metrics
```python
inference_requests_total{model, status}
inference_duration_seconds{model}
inference_tokens_total{model, type}
inference_batch_size{model}
```

### MCP Metrics
```python
mcp_requests_total{server, operation, status}
mcp_operation_duration_seconds{server, operation}
```

### Memory Metrics
```python
memory_operations_total{operation, status}
memory_operation_duration_seconds{operation}
memory_items_total{user_id}
memory_search_results
```

### Budget Metrics
```python
memory_budget_total_bytes{session_id}
memory_budget_used_bytes{session_id}
memory_budget_utilization{session_id}
```

### Drift Metrics
```python
drift_score{model}
drift_checks_total{model, status}
drift_detection_duration_seconds
```

### GPU Metrics
```python
gpu_utilization_percent{gpu_id}
gpu_memory_used_bytes{gpu_id}
gpu_memory_total_bytes{gpu_id}
gpu_temperature_celsius{gpu_id}
```

### Router Metrics
```python
router_decisions_total{model, reason}
router_decision_duration_seconds
```

### Queue Metrics
```python
request_queue_depth{service}
request_queue_wait_seconds{service}
```

### Cache Metrics
```python
cache_hits_total{cache_type}
cache_misses_total{cache_type}
```

## Structured Logging

### JSON Log Format
```json
{
  "timestamp": "2024-01-01T12:00:00.000Z",
  "level": "INFO",
  "logger": "gateway_service",
  "message": "Request processed",
  "service": "gateway",
  "trace_id": "abc123",
  "span_id": "def456",
  "method": "POST",
  "endpoint": "/v1/chat",
  "status_code": 200,
  "duration_ms": 125.5
}
```

### Service-Specific Fields

**MAX Serve**:
```json
{
  "model": "llama-3.3-8b",
  "batch_size": 4,
  "latency_ms": 250.5
}
```

**MCP**:
```json
{
  "mcp_server": "github",
  "mcp_operation": "search_repositories"
}
```

**Memory Engine**:
```json
{
  "user_id": "user123",
  "session_id": "session456",
  "operation": "search"
}
```

**Drift Monitor**:
```json
{
  "drift_score": 0.18,
  "threshold": 0.15
}
```

## Usage

### Using Metrics Exporter
```python
from metrics_exporter import get_metrics_exporter

# Get exporter
metrics = get_metrics_exporter('gateway')

# Record HTTP request
metrics.record_http_request('POST', '/v1/chat', 200, 0.125)

# Record inference
metrics.record_inference('llama-3.3-8b', 'success', 0.250, 
                        prompt_tokens=100, completion_tokens=50)

# Record MCP operation
metrics.record_mcp_operation('github', 'search', 'success', 0.050)

# Update drift score
metrics.update_drift_score('llama-3.3-8b', 0.18, 'warning', 5.0)

# Update budget
metrics.update_budget('session123', 1000000, 750000)
```

### Using Structured Logger
```python
from structured_logger import setup_structured_logging, get_structured_logger

# Setup logging for service
setup_structured_logging('gateway', level=logging.INFO)

# Get logger
logger = get_structured_logger(__name__)

# Log request
logger.log_request('POST', '/v1/chat', 200, 125.5, 
                  user_id='user123', request_id='req456')

# Log inference
logger.log_inference('llama-3.3-8b', 250.5, batch_size=4)

# Log MCP operation
logger.log_mcp_operation('github', 'search', 50.0, status='success')

# Log drift
logger.log_drift('llama-3.3-8b', 0.18, 0.15)
```

### Setting Trace Context
```python
from structured_logger import set_trace_context
from opentelemetry import trace

# Get trace context
span = trace.get_current_span()
trace_id = format(span.get_span_context().trace_id, '032x')
span_id = format(span.get_span_context().span_id, '016x')

# Set for logging
set_trace_context(trace_id, span_id)
```

## Configuration

### Environment Variables
```bash
# Slack webhook for alerts
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL

# OpenTelemetry endpoints (already configured in services)
OTLP_ENDPOINT=http://otel-collector:4317
JAEGER_ENDPOINT=jaeger:6831
```

### Slack Channels
Configure these channels in your Slack workspace:
- `#ai-platform-alerts` - Default alerts
- `#ai-platform-critical` - Critical alerts (@channel mentions)
- `#ai-platform-gpu` - GPU alerts
- `#ai-platform-drift` - Drift detection alerts
- `#ai-platform-budget` - Budget alerts
- `#ai-platform-infra` - Infrastructure alerts

## Accessing Dashboards

### Prometheus
- **URL**: http://localhost:9090
- **Features**: Query metrics, view targets, check alerts

### Grafana
- **URL**: http://localhost:3000
- **Credentials**: admin/admin
- **Data Sources**: Prometheus, Loki, PostgreSQL
- **Dashboards**: Pre-configured dashboards in `/configs/grafana/dashboards/`

### Jaeger
- **URL**: http://localhost:16686
- **Features**: Distributed tracing, service graph, trace comparison

### AlertManager
- **URL**: http://localhost:9093
- **Features**: View active alerts, silence alerts, configure receivers

### Loki (via Grafana)
- **Access**: Grafana > Explore > Loki
- **Features**: Log search, filtering, aggregation

## Ports Reference

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
| OTel Collector | 13133 | Health check |
| Jaeger | 16686 | UI |
| Jaeger | 14250 | gRPC |
| Redis Exporter | 9121 | Metrics |
| PostgreSQL Exporter | 9187 | Metrics |
| GPU Exporter | 9835 | Metrics |

## Data Retention

- **Prometheus**: 90 days
- **Loki**: 90 days (2160 hours)
- **Jaeger**: Persistent storage with Badger
- **AlertManager**: Active alerts only

## Performance Tuning

### Prometheus
- Scrape interval: 15s (configurable per job)
- Batch size: Default
- Memory: Adjusts based on retention and cardinality

### OpenTelemetry Collector
- Batch timeout: 10s
- Batch size: 1024 spans
- Memory limit: 512 MiB

### Loki
- Ingestion rate: 16 MB/s
- Streams per user: 10,000
- Query parallelism: 32

## Troubleshooting

### Metrics Not Appearing
1. Check service health: `docker compose ps`
2. Verify Prometheus targets: http://localhost:9090/targets
3. Check service `/metrics` endpoint
4. Review Prometheus logs: `docker compose logs prometheus`

### Logs Not Appearing
1. Check Loki health: http://localhost:3100/ready
2. Verify Promtail is running: `docker compose ps promtail`
3. Check Promtail logs: `docker compose logs promtail`
4. Test log query in Grafana Explore

### Traces Not Appearing
1. Check OTel Collector health: http://localhost:13133
2. Verify Jaeger is running: http://localhost:16686
3. Check OTel Collector logs: `docker compose logs otel-collector`
4. Verify services have OTLP endpoint configured

### Alerts Not Firing
1. Check AlertManager health: http://localhost:9093
2. Verify alert rules loaded: http://localhost:9090/alerts
3. Check Slack webhook URL is configured
4. Review AlertManager logs: `docker compose logs alertmanager`

## Security Considerations

- Change Grafana admin password in production
- Secure Prometheus with authentication
- Use TLS for external access
- Restrict network access to observability stack
- Rotate Slack webhook URLs periodically
- Implement RBAC for Grafana dashboards

## Next Steps

1. Configure Slack webhooks for alert notifications
2. Create custom Grafana dashboards for your use cases
3. Set up alert routing rules based on severity
4. Configure log retention policies based on compliance
5. Implement custom metrics for business KPIs
6. Set up backup for Prometheus and Loki data
