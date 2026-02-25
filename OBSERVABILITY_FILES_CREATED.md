# Observability Stack - Files Created

## Configuration Files

### Prometheus
- `configs/prometheus/prometheus.yml` - Main Prometheus configuration with 15s scrape interval
- `configs/prometheus/rules/alerts.yml` - Alert rules for latency, errors, GPU, drift, budget

### AlertManager
- `configs/alertmanager/alertmanager.yml` - Alert routing and Slack webhook configuration

### OpenTelemetry Collector
- `configs/otel-collector/otel-collector.yaml` - Distributed tracing configuration (Gateway→Router→MAX→MCP→Memory)

### Loki
- `configs/loki/loki.yaml` - Log aggregation with 90-day retention

### Promtail
- `configs/promtail/promtail.yaml` - Docker log collection and JSON parsing

## Python Modules

### Metrics
- `metrics_exporter.py` - Prometheus metrics exporter with custom metrics:
  - HTTP request metrics
  - Inference metrics (MAX Serve)
  - MCP operation metrics
  - Memory Engine metrics
  - Budget tracking metrics
  - Drift detection metrics
  - GPU metrics
  - Router decision metrics
  - Queue and cache metrics

### Logging
- `structured_logger.py` - Structured JSON logging for Loki:
  - JSON formatter with trace context
  - Service-specific log fields
  - Helper methods for common log types
  - Trace context management

## Docker Compose Updates

### New Services Added to `docker-compose.yaml`:

1. **otel-collector** - OpenTelemetry Collector
   - Ports: 4317 (OTLP gRPC), 4318 (OTLP HTTP), 8888 (metrics)
   - Distributed tracing pipeline

2. **loki** - Log aggregation
   - Port: 3100
   - 90-day retention
   - Structured JSON logs

3. **promtail** - Log collection
   - Port: 9080
   - Docker log scraping
   - JSON parsing pipeline

4. **alertmanager** - Alert routing
   - Port: 9093
   - Slack webhook integration
   - Alert grouping and routing

5. **redis-exporter** - Redis metrics
   - Port: 9121
   - Redis connection metrics

6. **postgres-exporter** - PostgreSQL metrics
   - Port: 9187
   - Database connection and query metrics

7. **nvidia-gpu-exporter** - GPU metrics
   - Port: 9835
   - GPU utilization, memory, temperature

### Updated Services:
- **prometheus** - Updated scrape configs for all services
- **grafana** - Added Loki data source dependency

### New Volumes:
- `loki-data` - Loki log storage
- `alertmanager-data` - AlertManager state

## Documentation

- `OBSERVABILITY_IMPLEMENTATION.md` - Complete implementation guide
  - Component overview
  - Alert rules documentation
  - Custom metrics reference
  - Structured logging guide
  - Usage examples
  - Configuration details

- `OBSERVABILITY_QUICKSTART.md` - Quick start guide
  - Setup instructions
  - Verification steps
  - Code examples
  - Common queries
  - Troubleshooting

- `OBSERVABILITY_FILES_CREATED.md` - This file

## Directory Structure

```
configs/
├── prometheus/
│   ├── prometheus.yml          # Main Prometheus config (15s scrape)
│   └── rules/
│       └── alerts.yml          # Alert rules (latency, error, GPU, drift, budget)
├── alertmanager/
│   └── alertmanager.yml        # AlertManager config with Slack webhooks
├── otel-collector/
│   └── otel-collector.yaml     # OpenTelemetry Collector config
├── loki/
│   └── loki.yaml              # Loki config (90d retention)
└── promtail/
    └── promtail.yaml          # Promtail config (Docker log collection)

# Python modules (project root)
metrics_exporter.py            # Prometheus metrics exporter
structured_logger.py           # Structured JSON logger
```

## Alert Rules Summary

### Latency Alerts (>2s)
- HighGatewayLatency
- HighMCPJungleLatency
- HighMaxServeLatency
- HighMemoryEngineLatency

### Error Rate Alerts (>1%)
- HighErrorRate
- HighMaxServeErrorRate
- HighMCPErrorRate

### GPU Alerts
- HighGPUUtilization (>90%)
- HighGPUMemory (>90%)
- HighGPUTemperature (>85°C)

### Drift Alerts
- DriftDetected (score > 0.15)
- HighDriftScore (score > 0.25)

### Budget Alerts
- BudgetExceeded
- BudgetWarning (>80%)

### Service Health
- ServiceDown
- HighRequestQueueDepth

### Database Alerts
- PostgreSQLPoolExhausted
- RedisMemoryHigh

### Tracing Alerts
- HighTraceErrorRate

## Slack Channels Required

Configure these channels in your Slack workspace:
1. `#ai-platform-alerts` - Default alerts
2. `#ai-platform-critical` - Critical alerts
3. `#ai-platform-gpu` - GPU alerts
4. `#ai-platform-drift` - Drift alerts
5. `#ai-platform-budget` - Budget alerts
6. `#ai-platform-infra` - Infrastructure alerts

## Metrics Exposed

### Services with /metrics Endpoint
All services should expose Prometheus metrics:
- Gateway (9002)
- MCPJungle Gateway (9100)
- API Server (8000)
- MAX Serve Llama (8080)
- MAX Serve Qwen (8081)
- MAX Serve DeepSeek (8082)
- Memory Service (8001)
- Learning Engine (8003)
- Drift Monitor (8004)
- Data Collection (8002)
- MAML Service (8005)
- Qdrant (6333)
- Redis Exporter (9121)
- PostgreSQL Exporter (9187)
- GPU Exporter (9835)
- OpenTelemetry Collector (8888)
- Loki (3100)

## Trace Flow

Distributed tracing follows this path:

```
Client
  ↓
Gateway (trace starts)
  ↓
Router (span: routing decision)
  ↓
MAX Serve (span: inference)
  ↓
MCP Server (span: tool execution)
  ↓
Memory Engine (span: memory retrieval)
```

Each span includes:
- Service name
- Operation name
- Duration
- Status
- Attributes (model, user_id, etc.)

## Log Flow

Logs follow this pipeline:

```
Application (JSON logs)
  ↓
Docker stdout/stderr
  ↓
Promtail (scrapes container logs)
  ↓
JSON parsing & label extraction
  ↓
Loki (stores with labels)
  ↓
Grafana (query & visualization)
```

## Port Reference

| Service | Port | Purpose |
|---------|------|---------|
| Prometheus | 9090 | Metrics & UI |
| Grafana | 3000 | Dashboards |
| Loki | 3100 | Log ingestion |
| Promtail | 9080 | Log collection status |
| AlertManager | 9093 | Alert management |
| OTel Collector | 4317 | OTLP gRPC |
| OTel Collector | 4318 | OTLP HTTP |
| OTel Collector | 8888 | Collector metrics |
| OTel Collector | 13133 | Health check |
| Jaeger | 16686 | Tracing UI |
| Redis Exporter | 9121 | Redis metrics |
| PostgreSQL Exporter | 9187 | PostgreSQL metrics |
| GPU Exporter | 9835 | GPU metrics |

## Environment Variables

Required environment variables:

```bash
# Slack webhook for alerts (required for AlertManager)
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL

# OpenTelemetry (already configured in services)
OTLP_ENDPOINT=http://otel-collector:4317
JAEGER_ENDPOINT=jaeger:6831
ENABLE_TELEMETRY=true
```

## Integration Points

### Services Should Integrate:

1. **Metrics**: Import `metrics_exporter.py` and record metrics
2. **Logging**: Use `structured_logger.py` for JSON logs
3. **Tracing**: Configure OpenTelemetry with OTLP endpoint
4. **Health Checks**: Expose `/health` endpoint
5. **Metrics Endpoint**: Expose `/metrics` endpoint

### Example Integration:

```python
from metrics_exporter import get_metrics_exporter
from structured_logger import setup_structured_logging, get_structured_logger

# Setup
setup_structured_logging('my-service')
metrics = get_metrics_exporter('my-service')
logger = get_structured_logger(__name__)

# Use in request handler
start = time.time()
# ... process request ...
duration = time.time() - start

# Record metrics
metrics.record_http_request('POST', '/api/endpoint', 200, duration)

# Log
logger.log_request('POST', '/api/endpoint', 200, duration * 1000)
```

## Data Retention

- **Prometheus**: 90 days
- **Loki**: 90 days (2160 hours)
- **Jaeger**: Persistent (managed by Badger storage)
- **AlertManager**: Active alerts only (no historical data)

## Next Steps

To complete the integration:

1. Add `/metrics` endpoint to all services
2. Import and use `metrics_exporter.py` in services
3. Replace logging with `structured_logger.py`
4. Configure Slack webhooks for alerts
5. Create custom Grafana dashboards
6. Test alert firing with sample data
7. Configure backup for Prometheus and Loki data
