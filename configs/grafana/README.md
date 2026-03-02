# Grafana Dashboards

This directory contains Grafana dashboard definitions for monitoring the AI Platform.

## Directory Structure

```
configs/grafana/
├── dashboards/              # Dashboard JSON definitions
│   ├── platform-overview.json
│   ├── learning-engine.json
│   ├── mcp-activity.json
│   ├── model-routing-overview.json
│   ├── safety-guardrails-overview.json
│   ├── kong-dashboard.json
│   ├── drift-overview.json
│   └── ...
├── provisioning/           # Grafana provisioning configs
│   ├── dashboards/
│   │   └── dashboards.yml
│   └── datasources/
│       └── datasources.yml
└── README.md
```

## Available Dashboards

### 1. Platform Overview (`platform-overview.json`)

**UID**: `platform-overview`  
**Tags**: `platform`, `overview`, `performance`  
**Refresh**: 30s

Provides a high-level view of platform performance and health.

**Metrics Displayed**:
- **Latency P99**: Request latency at 99th percentile (with P95/P50)
  - Source: `http_request_duration_seconds_bucket`
  - Threshold: Yellow at 1s, Red at 1.5s
- **Error Rate**: 5xx error rate by endpoint
  - Source: `http_requests_total{status=~"5.."}`
  - Threshold: Yellow at 1%, Red at 5%
- **GPU Utilization**: GPU usage percentage
  - Source: `DCGM_FI_DEV_GPU_UTIL`
  - Threshold: Yellow at 70%, Orange at 85%, Red at 95%
- **Token Usage Rate**: Token processing rate (prompt + completion)
  - Source: `inference_tokens_total{type="prompt|completion"}`
- **Memory Cache Hit Rate**: Cache efficiency
  - Source: `cache_hits_total / (cache_hits_total + cache_misses_total)`
  - Threshold: Red <50%, Orange 50-70%, Yellow 70-85%, Green >85%
- **GPU Memory Usage**: Memory used/free per GPU
  - Source: `DCGM_FI_DEV_FB_USED`, `DCGM_FI_DEV_FB_FREE`
- **GPU Temperature**: Temperature per GPU
  - Source: `DCGM_FI_DEV_GPU_TEMP`
  - Threshold: Yellow at 70°C, Red at 85°C
- **Requests/sec**: Total HTTP requests per second
- **Inferences/sec**: Inference requests per second
- **Queue Depth**: Current request queue depth
- **Batch Size P99**: 99th percentile batch size

**Use Cases**:
- Quick health check of the platform
- Identifying performance bottlenecks
- Monitoring GPU resource utilization
- Tracking request patterns and latency

---

### 2. Learning Engine (`learning-engine.json`)

**UID**: `learning-engine`  
**Tags**: `learning-engine`, `drift`, `lora`, `training`  
**Refresh**: 1m

Monitors the learning engine, drift detection, and model training.

**Metrics Displayed**:

**Drift Metrics**:
- **KL Divergence**: Kullback-Leibler divergence measuring distribution shift
  - Source: `drift_kl_divergence`
  - Threshold: Yellow at 0.1, Orange at 0.15, Red at 0.2
- **PSI**: Population Stability Index
  - Source: `drift_psi`
  - Threshold: Yellow at 0.1, Orange at 0.2, Red at 0.3
- **Model Accuracy**: Current model accuracy
  - Source: `drift_current_accuracy`, `model_accuracy`
  - Threshold: Red <70%, Orange 70-75%, Yellow 75-80%, Green >80%
- **Drift Metrics Over Time**: Time series of KL Divergence and PSI

**Training Metrics**:
- **Training & Validation Loss**: Loss curves over time
  - Source: `training_loss`, `validation_loss`
- **EWC Lambda**: Elastic Weight Consolidation regularization strength
  - Source: `ewc_lambda`
- **Training Duration**: Time taken for last training run
  - Source: `training_duration_seconds`
- **Training Samples**: Number of samples used in training
  - Source: `training_samples_total`

**LoRA Metrics**:
- **LoRA Version History**: Table of all LoRA versions with metadata
  - Source: PostgreSQL `lora_versions` table
  - Shows: version_id, created_at, is_active, deployed_at, metrics_summary, training_config
- **Total LoRA Versions**: Count of created versions
  - Source: `lora_versions_total`
- **Fine-tuning Triggers**: Count of triggered fine-tuning runs
  - Source: `finetuning_triggers_total`
- **Drift Detections**: Number of drift events detected
  - Source: `drift_detected_total`

**Advanced Metrics**:
- **Total Training Runs**: Count of all training runs
  - Source: `training_runs_total`
- **Fisher Matrix Size**: Size of Fisher information matrix
  - Source: `fisher_matrix_size_bytes`
- **Replay Buffer Utilization**: Buffer usage percentage
  - Source: `replay_buffer_size / replay_buffer_capacity`

**Use Cases**:
- Monitoring model drift and triggering retraining
- Tracking training progress and convergence
- Managing LoRA version lifecycle
- Analyzing EWC regularization effectiveness
- Identifying when models need updating

---

### 3. MCP Activity (`mcp-activity.json`)

**UID**: `mcp-activity`  
**Tags**: `mcp`, `tools`, `activity`  
**Refresh**: 30s

Monitors MCP (Model Context Protocol) server activity and performance.

**Metrics Displayed**:

**Activity Metrics**:
- **MCP Calls per Server**: Request rate by server (stacked area)
  - Source: `sum(rate(mcp_requests_total[5m])) by (server)`
- **Total Calls per Server (1h)**: Bar chart of total calls in last hour
  - Source: `sum(increase(mcp_requests_total[1h])) by (server)`
- **MCP Operations Activity**: Request rate by operation type
  - Source: `sum(rate(mcp_requests_total[5m])) by (operation)`

**Latency Metrics**:
- **Tool Latency by Server & Operation**: P50/P95/P99 latency
  - Source: `mcp_operation_duration_seconds_bucket`
  - Threshold: Yellow at 0.5s, Red at 1s
- **Avg Latency (P50)**: Median latency across all operations
- **P95 Latency**: 95th percentile latency
- **P99 Latency**: 99th percentile latency

**Error Metrics**:
- **MCP Errors by Server**: Error rate per server (stacked area)
  - Source: `sum(rate(mcp_requests_total{status=~"error|failed"}[5m])) by (server)`
- **MCP Error Rate by Server**: Percentage error rate
  - Source: Error requests / Total requests
  - Threshold: Yellow at 1%, Red at 5%
- **Overall Error Rate**: Platform-wide MCP error rate

**Summary Stats**:
- **Active MCP Servers**: Count of servers with recent activity
- **Total MCP Calls/sec**: Aggregate request rate
- **MCP Server Distribution (1h)**: Pie chart of calls per server
- **MCP Operation Distribution (1h)**: Pie chart of calls per operation
- **MCP Operations Heatmap**: Time series grid of server x operation

**Use Cases**:
- Monitoring MCP server health and availability
- Identifying slow or failing operations
- Load balancing between MCP servers
- Tracking tool usage patterns
- Detecting anomalous behavior

---

### 4. Model Routing Overview (`model-routing-overview.json`)

**UID**: `model-routing-overview`  
**Tags**: `routing`, `models`, `latency`, `fallback`  
**Refresh**: 30s

Focused dashboard for model selection quality and fallback behavior.

**Metrics Displayed**:
- **Traffic per Routed Model**
  - Source: `agent_router_routed_requests_total{status="success"}`
  - Shows final traffic distribution by model (including fallback destinations)
- **Latency P95 by Intent**
  - Source: `agent_router_latency_seconds_bucket`
  - Shows p95 latency split by intent (`code`, `reasoning`, `general`)
- **Fallback Rate by Primary Model**
  - Source: `agent_router_fallback_rate`
  - Gauge/time-series trend of fallback rate per initially-selected model
- **Global Fallback Ratio (5m)**
  - Source: Routed requests with `fallback_used="true"` over all successful routed requests
- **Failed Routing Decisions (1h)**
  - Source: `agent_router_routed_requests_total{status="failed"}`

**Use Cases**:
- Tune intent-to-model routing policies
- Spot unstable primary models with increasing fallback ratios
- Compare routing latency profiles by intent

---

### 5. Safety & Guardrail Monitoring (`safety-guardrails-overview.json`)

**UID**: `safety-guardrails-overview`  
**Tags**: `safety`, `guardrails`, `jailbreak`, `security`  
**Refresh**: 30s

Tracks safety policy enforcement volume, block rates, and jailbreak robustness trends across deployments.

**Metrics Displayed**:
- **Blocked Requests (range total)**
  - Source: `guardrail_requests_total{decision="blocked"}`
  - Uses `increase()` over selected time range
- **Current Blocked Rate (5m)**
  - Source: blocked vs all from `guardrail_requests_total`
  - Formula: `sum(rate(blocked)) / sum(rate(all))`
- **Safety Policies Triggered by Category**
  - Source: `guardrail_policy_triggers_total` (or legacy `guardrail_policy_trigger_total`)
  - Grouped by `policy_category`
- **Blocked Request Ratio Over Time**
  - Source: `guardrail_requests_total`
  - Time-series for ongoing guardrail pressure
- **Jailbreak Robustness Evolution by Deployment**
  - Source: `jailbreak_robustness_score{deployment=...}`
  - Multi-deployment trend chart via `deployment` variable
- **Latest Jailbreak Robustness by Deployment**
  - Source: `jailbreak_robustness_score`
  - Bar gauge snapshot for quick release comparison

**Use Cases**:
- Detect sudden increases in blocked prompts after model releases
- Identify the dominant safety policy categories being triggered
- Compare jailbreak resilience between active deployments
- Support release gates based on robustness score trends

---

## Datasources

### Prometheus
- **URL**: `http://prometheus:9090`
- **Type**: `prometheus`
- **Use**: Time-series metrics for platform monitoring

### PostgreSQL
- **URL**: `postgres:5432`
- **Database**: `ai_platform`
- **Type**: `postgres`
- **Use**: Structured data for drift metrics and LoRA versions

## Provisioning

Dashboards are automatically provisioned to Grafana via the configuration in `provisioning/dashboards/dashboards.yml`:

```yaml
apiVersion: 1
providers:
  - name: 'Drift Monitoring'
    orgId: 1
    folder: ''
    type: file
    disableDeletion: false
    updateIntervalSeconds: 10
    allowUiUpdates: true
    options:
      path: /var/lib/grafana/dashboards
      foldersFromFilesStructure: true
```

## Metrics Reference

### Platform Metrics
| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `http_requests_total` | Counter | method, endpoint, status | Total HTTP requests |
| `http_request_duration_seconds` | Histogram | method, endpoint | Request latency |
| `inference_requests_total` | Counter | model, status | Inference requests |
| `inference_tokens_total` | Counter | model, type | Tokens processed |
| `cache_hits_total` | Counter | cache_type | Cache hits |
| `cache_misses_total` | Counter | cache_type | Cache misses |
| `request_queue_depth` | Gauge | service | Queue depth |
| `inference_batch_size` | Histogram | model | Batch sizes |

### GPU Metrics (DCGM)
| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `DCGM_FI_DEV_GPU_UTIL` | Gauge | gpu | GPU utilization % |
| `DCGM_FI_DEV_FB_USED` | Gauge | gpu | GPU memory used (bytes) |
| `DCGM_FI_DEV_FB_FREE` | Gauge | gpu | GPU memory free (bytes) |
| `DCGM_FI_DEV_GPU_TEMP` | Gauge | gpu | GPU temperature (°C) |

### Drift Metrics
| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `drift_kl_divergence` | Gauge | model | KL divergence score |
| `drift_psi` | Gauge | model | PSI score |
| `drift_current_accuracy` | Gauge | model | Current accuracy |
| `drift_detected_total` | Counter | severity | Drift detections |
| `finetuning_triggers_total` | Counter | trigger_type | Fine-tuning triggers |

### Learning Engine Metrics
| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `training_loss` | Gauge | model, version_id | Training loss |
| `validation_loss` | Gauge | model, version_id | Validation loss |
| `training_duration_seconds` | Gauge | model, version_id | Training duration |
| `training_samples_total` | Gauge | model, version_id | Training samples count |
| `ewc_lambda` | Gauge | model, version_id | EWC lambda value |
| `lora_versions_total` | Gauge | model | Total LoRA versions |
| `training_runs_total` | Counter | model, status | Training runs |
| `fisher_matrix_size_bytes` | Gauge | model | Fisher matrix size |
| `replay_buffer_size` | Gauge | model | Replay buffer size |
| `replay_buffer_capacity` | Gauge | model | Replay buffer capacity |

### MCP Metrics
| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `mcp_requests_total` | Counter | server, operation, status | MCP requests |
| `mcp_operation_duration_seconds` | Histogram | server, operation | MCP operation latency |

### Safety & Guardrail Metrics
| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `guardrail_requests_total` | Counter | decision, policy_category, deployment | Total requests evaluated by safety guardrails |
| `guardrail_policy_triggers_total` | Counter | policy_category, deployment | Count of triggered safety policy categories |
| `jailbreak_robustness_score` | Gauge | deployment, model_version | Normalized jailbreak robustness score (0-1) |

## Importing Dashboards

### Via Grafana UI
1. Navigate to Dashboards → Import
2. Upload the JSON file or paste the JSON content
3. Select the datasource (Prometheus or PostgreSQL)
4. Click Import

### Via Provisioning (Recommended)
1. Place dashboard JSON files in `configs/grafana/dashboards/`
2. Ensure `provisioning/dashboards/dashboards.yml` is configured
3. Restart Grafana or wait for auto-reload (10s interval)

## Customization

All dashboards support:
- **Time Range Selection**: Default ranges vary by dashboard
- **Auto-refresh**: Configurable refresh intervals
- **Variables**: Can be extended with template variables
- **Annotations**: Support for marking events
- **Alerts**: Can be configured on panels (Grafana Alerting required)

## Best Practices

1. **Monitor Regularly**: Set up alerts on critical metrics
2. **Adjust Thresholds**: Tune thresholds based on your SLAs
3. **Use Time Windows**: Adjust time ranges for different analysis needs
4. **Export/Import**: Keep dashboard definitions in version control
5. **Document Changes**: Update this README when adding new metrics

## Troubleshooting

### Dashboard Not Loading
- Check datasource connectivity (Prometheus/PostgreSQL)
- Verify metrics are being exported by services
- Check Grafana logs: `docker logs grafana`

### Missing Data Points
- Ensure metric exporters are running
- Verify scrape interval in Prometheus config
- Check if labels match query expressions

### Performance Issues
- Reduce time range or increase refresh interval
- Optimize PromQL queries (use recording rules)
- Consider using query result caching

## Additional Resources

- [Grafana Documentation](https://grafana.com/docs/)
- [Prometheus Query Language](https://prometheus.io/docs/prometheus/latest/querying/basics/)
- [DCGM Exporter Metrics](https://github.com/NVIDIA/dcgm-exporter)
- Platform Architecture: `../../ARCHITECTURE.md`
- Observability Guide: `../../OBSERVABILITY_README.md`
