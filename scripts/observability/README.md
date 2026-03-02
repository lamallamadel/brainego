# Cost Optimization & Resource Right-Sizing

This directory contains scripts and services for cost optimization and resource management in the AI platform.

## Overview

The cost optimization suite provides:

1. **Resource Usage Analysis** - Analyzes 7-day P95 CPU/memory usage and generates right-sizing recommendations
2. **Vertical Pod Autoscaler (VPA)** - Automatically adjusts resource requests/limits for non-critical services
3. **Qdrant Archival Service** - Moves embeddings older than 90 days to MinIO cold storage
4. **Cost Dashboard** - Grafana dashboard showing spend per workspace based on token metering

## Components

### 1. Resource Usage Analyzer

**File**: `analyze_resource_usage.py`

Queries Prometheus for historical resource usage and generates recommendations for right-sizing pod resource requests.

#### Features

- Queries 7-day P95 CPU and memory usage across all pods
- Compares usage against current resource requests
- Identifies underutilized resources (P95 < 40% of request)
- Identifies overutilized resources (P95 > 85% of request)
- Generates recommendations with 20% safety buffer
- Estimates monthly and annual cost savings

#### Usage

```bash
# Run with default settings
python scripts/observability/analyze_resource_usage.py

# Run with custom Prometheus URL
PROMETHEUS_URL=http://prometheus:9090 python scripts/observability/analyze_resource_usage.py

# Customize lookback period
LOOKBACK_DAYS=14 python scripts/observability/analyze_resource_usage.py

# Specify output file
OUTPUT_FILE=recommendations.json python scripts/observability/analyze_resource_usage.py
```

#### Environment Variables

- `PROMETHEUS_URL` - Prometheus endpoint (default: `http://prometheus:9090`)
- `OUTPUT_FILE` - Output JSON file (default: `resource_recommendations.json`)
- `LOOKBACK_DAYS` - Analysis period in days (default: `7`)

#### Output

Generates a JSON report with:
- Summary statistics
- Per-workload recommendations
- Estimated cost savings
- Current vs. recommended resource requests

Example output:

```json
{
  "generated_at": "2024-03-15T10:30:00Z",
  "lookback_days": 7,
  "summary": {
    "total_workloads_analyzed": 25,
    "recommendations_generated": 12,
    "cost_savings": {
      "total_cpu_cores_saved": 8.5,
      "total_memory_gi_saved": 24.3,
      "estimated_monthly_savings_usd": 352.20,
      "estimated_annual_savings_usd": 4226.40
    }
  },
  "recommendations": [
    {
      "namespace": "ai-platform",
      "workload": "api-server",
      "container": "api-server",
      "current": {
        "cpu_request_cores": 2.0,
        "memory_request_gi": 2.0
      },
      "usage": {
        "cpu_p95_cores": 0.65,
        "memory_p95_gi": 0.8
      },
      "utilization": {
        "cpu_percent": 32.5,
        "memory_percent": 40.0
      },
      "recommendation": {
        "cpu_request_cores": 0.78,
        "memory_request_gi": 0.96
      },
      "action": "reduce_both",
      "potential_savings": {
        "cpu_cores": 1.22,
        "memory_gi": 1.04
      }
    }
  ]
}
```

#### Dependencies

- `requests>=2.31.0` - HTTP client for Prometheus API

### 2. Vertical Pod Autoscaler (VPA)

**File**: `helm/ai-platform/templates/vpa.yaml`

Kubernetes VPA manifests for automatically adjusting resource requests/limits for non-critical services.

#### Enabled Services

- Gateway
- MCPJungle
- Mem0
- Grafana
- Jaeger

#### Configuration

Enable VPA in `helm/ai-platform/values.yaml`:

```yaml
vpa:
  enabled: true
  updateMode: Auto  # Options: Off, Initial, Recreate, Auto
  
  gateway:
    minAllowed:
      cpu: 100m
      memory: 256Mi
    maxAllowed:
      cpu: 2
      memory: 4Gi
```

#### Update Modes

- **Off** - VPA only provides recommendations, doesn't update pods
- **Initial** - VPA updates pods only at creation time
- **Recreate** - VPA updates running pods by evicting and recreating them
- **Auto** - VPA updates pods without eviction (requires VPA admission controller)

### 3. Qdrant Archival Service

**File**: `qdrant_archival_service.py`

Service for archiving old embeddings from Qdrant to MinIO cold storage to reduce active database size.

#### Features

- Identifies embeddings older than configurable threshold (default: 90 days)
- Archives embeddings to MinIO with compression (gzip)
- Optionally deletes archived embeddings from Qdrant
- Supports workspace-based filtering
- Batch processing with configurable batch sizes
- Dry-run mode for testing

#### Usage

##### Manual Execution

```bash
# Run archival with default settings
python scripts/observability/qdrant_archival_service.py

# Archive specific collection
COLLECTION_NAME=documents python scripts/observability/qdrant_archival_service.py

# Filter by workspace
WORKSPACE_ID=acme python scripts/observability/qdrant_archival_service.py

# Dry run (no deletion)
DRY_RUN=true python scripts/observability/qdrant_archival_service.py

# Custom age threshold
ARCHIVAL_AGE_DAYS=180 python scripts/observability/qdrant_archival_service.py
```

##### Scheduled CronJob (Kubernetes)

Enable archival CronJob in `helm/ai-platform/values.yaml`:

```yaml
qdrantArchival:
  enabled: true
  schedule: "0 2 * * 0"  # Weekly on Sunday at 2 AM
  collectionName: documents
  archivalAgeDays: 90
  batchSize: 1000
  dryRun: false
  minioBucket: qdrant-archive
```

Deploy:

```bash
helm upgrade --install ai-platform ./helm/ai-platform \
  --set qdrantArchival.enabled=true
```

#### Environment Variables

- `QDRANT_HOST` - Qdrant hostname (default: `qdrant`)
- `QDRANT_PORT` - Qdrant port (default: `6333`)
- `MINIO_ENDPOINT` - MinIO endpoint (default: `minio:9000`)
- `MINIO_ACCESS_KEY` - MinIO access key
- `MINIO_SECRET_KEY` - MinIO secret key
- `MINIO_ARCHIVE_BUCKET` - MinIO bucket for archives (default: `qdrant-archive`)
- `ARCHIVAL_AGE_DAYS` - Age threshold in days (default: `90`)
- `BATCH_SIZE` - Batch size for processing (default: `1000`)
- `COLLECTION_NAME` - Qdrant collection name (default: `documents`)
- `WORKSPACE_ID` - Optional workspace filter
- `DRY_RUN` - Dry run mode (default: `false`)

#### Archive Format

Archives are stored as compressed JSON files:

```
{workspace_id}/{collection_name}/archive_{timestamp}_batch_{num}.json.gz
```

Each archive contains:

```json
[
  {
    "id": "uuid",
    "vector": [0.1, 0.2, ...],
    "payload": {
      "text": "...",
      "metadata": {...}
    },
    "archived_at": "2024-03-15T10:30:00Z"
  }
]
```

#### Restoration

To restore archived embeddings:

```python
from scripts.observability.qdrant_archival_service import QdrantArchivalService

service = QdrantArchivalService(...)
service.restore_archive(
    archive_filename="workspace1/documents/archive_20240315_103000_batch_1.json.gz",
    collection_name="documents"
)
```

#### Dependencies

- `qdrant-client>=1.7.0` - Qdrant Python client
- `minio>=7.2.0` - MinIO Python SDK

### 4. Cost Dashboard

**File**: `configs/grafana/dashboards/cost-optimization.json`

Grafana dashboard for visualizing cost metrics and resource usage.

#### Features

- **Monthly Cost Estimate** - Total estimated cost across all workspaces
- **Cost Trend by Workspace** - Hourly cost trends per workspace
- **Token Usage Table** - Detailed token usage and cost per workspace (last 30 days)
- **Cost Distribution** - Pie chart showing cost distribution by workspace
- **CPU/Memory Usage** - Resource usage by pod (compute allocation)
- **Metering Events** - Detailed metering event log (last 7 days)

#### Data Sources

- **Prometheus** - For real-time metrics and resource usage
- **PostgreSQL** - For metering event history and aggregations

#### Metrics Used

- `workspace_metering_total_tokens` - Total tokens consumed per workspace
- `container_cpu_usage_seconds_total` - CPU usage per container
- `container_memory_working_set_bytes` - Memory usage per container
- `kube_pod_container_resource_requests` - Resource requests from kube-state-metrics

#### Cost Calculation

Token-based pricing model:
- **$1 per 1 million tokens** (configurable)
- Estimated monthly cost = `sum(rate(tokens[30d]) * 30) * $0.000001`

#### Access

Dashboard is available at:
```
http://<grafana-url>/d/cost-optimization/cost-optimization-finops
```

Or import from Grafana UI:
1. Navigate to Dashboards → Import
2. Upload `configs/grafana/dashboards/cost-optimization.json`

## Deployment

### Prerequisites

1. Prometheus with kube-state-metrics
2. PostgreSQL with metering schema
3. Grafana
4. MinIO (for archival)
5. VPA admission controller (for VPA feature)

### Installation

1. **Deploy VPA**:

```bash
# Install VPA (if not already installed)
kubectl apply -f https://raw.githubusercontent.com/kubernetes/autoscaler/master/vertical-pod-autoscaler/deploy/vpa-v1-crd-gen.yaml
kubectl apply -f https://raw.githubusercontent.com/kubernetes/autoscaler/master/vertical-pod-autoscaler/deploy/vpa-rbac.yaml

# Enable VPA in platform
helm upgrade --install ai-platform ./helm/ai-platform \
  --set vpa.enabled=true \
  --set vpa.updateMode=Auto
```

2. **Enable Qdrant Archival**:

```bash
helm upgrade --install ai-platform ./helm/ai-platform \
  --set qdrantArchival.enabled=true \
  --set qdrantArchival.archivalAgeDays=90
```

3. **Import Cost Dashboard**:

```bash
# Via Grafana provisioning
kubectl create configmap grafana-dashboard-cost \
  --from-file=configs/grafana/dashboards/cost-optimization.json \
  -n ai-platform

# Or via Grafana UI
```

4. **Run Resource Analysis**:

```bash
# As a Kubernetes Job
kubectl create job resource-analysis \
  --image=ai-platform/api-server:latest \
  --restart=Never \
  -- python scripts/observability/analyze_resource_usage.py

# View results
kubectl logs job/resource-analysis
```

## Best Practices

### Resource Right-Sizing

1. **Run analysis weekly** - Resource usage patterns change over time
2. **Review recommendations carefully** - Don't blindly apply all recommendations
3. **Test in staging first** - Validate recommendations before applying to production
4. **Monitor after changes** - Watch for OOM kills or CPU throttling
5. **Keep safety buffers** - Don't size too aggressively (20% buffer recommended)

### VPA Configuration

1. **Start with updateMode: Off** - Review recommendations before enabling
2. **Use updateMode: Initial** for stateful workloads
3. **Use updateMode: Auto** for stateless services
4. **Set appropriate min/max bounds** - Prevent excessive scaling
5. **Exclude critical services** - Don't VPA your databases or critical API servers

### Qdrant Archival

1. **Start with dry-run** - Test archival without deletion
2. **Archive incrementally** - Start with small age thresholds
3. **Monitor MinIO capacity** - Ensure sufficient storage for archives
4. **Test restoration** - Verify you can restore archives if needed
5. **Document archive location** - Keep inventory of archived data

### Cost Monitoring

1. **Set up alerts** - Alert on cost spikes or anomalies
2. **Review dashboard weekly** - Identify cost optimization opportunities
3. **Track by workspace** - Understand which teams/projects drive costs
4. **Correlate with usage** - Understand cost drivers (tokens, compute, storage)
5. **Set budgets** - Implement budget alerts per workspace

## Troubleshooting

### Resource Analyzer Issues

**Problem**: "Connection refused" to Prometheus

**Solution**: Verify Prometheus URL and ensure Prometheus is accessible

```bash
kubectl port-forward svc/prometheus 9090:9090 -n ai-platform
curl http://localhost:9090/api/v1/query?query=up
```

**Problem**: No metrics found

**Solution**: Ensure kube-state-metrics is running and exporting metrics

```bash
kubectl get pods -n kube-system -l app.kubernetes.io/name=kube-state-metrics
```

### VPA Issues

**Problem**: VPA not updating pods

**Solution**: Check VPA admission controller is running

```bash
kubectl get pods -n kube-system -l app=vpa-admission-controller
kubectl logs -n kube-system -l app=vpa-admission-controller
```

**Problem**: Pods being evicted too frequently

**Solution**: Use updateMode: Initial or increase minReplicas in HPA

### Archival Issues

**Problem**: "Access Denied" from MinIO

**Solution**: Verify MinIO credentials and bucket permissions

```bash
kubectl get secret minio-credentials -n ai-platform -o yaml
```

**Problem**: Archive files too large

**Solution**: Reduce batch size or increase compression

```yaml
qdrantArchival:
  batchSize: 500  # Smaller batches
```

### Dashboard Issues

**Problem**: Dashboard shows no data

**Solution**: Verify data sources are configured

```bash
# Check Prometheus data source
curl -X GET http://grafana:3000/api/datasources -u admin:password

# Check PostgreSQL connection
kubectl exec -it postgres-0 -n ai-platform -- psql -U ai_user -d ai_platform -c "SELECT COUNT(*) FROM workspace_metering_events;"
```

## Cost Optimization Tips

1. **Right-size resources** - Use analyzer recommendations to reduce over-provisioning
2. **Enable VPA** - Let VPA automatically optimize non-critical services
3. **Archive old data** - Move unused embeddings to cheaper storage
4. **Use spot instances** - For non-critical batch workloads
5. **Implement autoscaling** - Scale down during low-traffic periods
6. **Optimize token usage** - Use smaller models when appropriate
7. **Cache aggressively** - Reduce redundant API calls
8. **Batch requests** - Reduce overhead of individual requests
9. **Monitor workspace usage** - Identify and address high-cost workspaces
10. **Set resource quotas** - Prevent runaway costs

## Related Documentation

- [Kubernetes VPA Documentation](https://github.com/kubernetes/autoscaler/tree/master/vertical-pod-autoscaler)
- [Prometheus Query API](https://prometheus.io/docs/prometheus/latest/querying/api/)
- [MinIO Python SDK](https://min.io/docs/minio/linux/developers/python/minio-py.html)
- [Qdrant Python Client](https://qdrant.tech/documentation/quick-start/)
- [Grafana Dashboard Best Practices](https://grafana.com/docs/grafana/latest/dashboards/)
