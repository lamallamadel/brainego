# Cost Optimization & Resource Right-Sizing - Files Created

This document lists all files created for the cost optimization and resource right-sizing implementation.

## 📁 Files Created

### Core Scripts

1. **`scripts/observability/analyze_resource_usage.py`**
   - Queries Prometheus for 7-day P95 CPU/memory usage
   - Generates right-sizing recommendations
   - Estimates cost savings
   - Dependencies: `requests>=2.31.0`

2. **`scripts/observability/apply_recommendations.py`**
   - Applies resource recommendations to Helm values
   - Generates Helm values patch files
   - Interactive and batch modes
   - Dependencies: `pyyaml`

3. **`scripts/observability/qdrant_archival_service.py`**
   - Archives Qdrant embeddings older than 90 days
   - Compresses and stores in MinIO cold storage
   - Supports workspace-based filtering
   - Dependencies: `qdrant-client>=1.7.0`, `minio>=7.2.0`

4. **`scripts/observability/cost_optimization_workflow.sh`**
   - End-to-end automation workflow
   - Runs analysis, generates patches, optional archival
   - Bash script for CI/CD integration

### Kubernetes Manifests

5. **`helm/ai-platform/templates/vpa.yaml`**
   - Vertical Pod Autoscaler manifests
   - VPA for: Gateway, MCPJungle, Mem0, Grafana, Jaeger
   - Configurable update modes and resource bounds

6. **`helm/ai-platform/templates/qdrant-archival-cronjob.yaml`**
   - CronJob for automated Qdrant archival
   - Runs weekly by default (configurable)
   - Integrated with MinIO for cold storage

### Configuration

7. **`helm/ai-platform/values.yaml`** (updated)
   - Added VPA configuration section
   - Added Qdrant archival configuration
   - Added API Server resource configuration
   - Added graceful shutdown configuration

### Dashboards

8. **`configs/grafana/dashboards/cost-optimization.json`**
   - Grafana dashboard for cost monitoring
   - Token usage and cost by workspace
   - CPU/Memory allocation by pod
   - Cost distribution and trends
   - Metering event details

### Documentation

9. **`scripts/observability/README.md`**
   - Comprehensive documentation
   - Component descriptions
   - Usage instructions
   - Troubleshooting guide
   - Best practices

10. **`COST_OPTIMIZATION_QUICKSTART.md`**
    - Quick start guide (5 minutes)
    - Step-by-step instructions
    - Common scenarios
    - Best practices

11. **`COST_OPTIMIZATION_FILES_CREATED.md`** (this file)
    - Complete file listing
    - Feature summary
    - Integration points

### Configuration Updates

12. **`.gitignore`** (updated)
    - Ignore cost optimization reports
    - Ignore generated recommendations
    - Ignore Helm patch files

## 🎯 Features Implemented

### 1. Resource Usage Analysis ✅

- Queries Prometheus for historical usage (7 days default)
- Calculates P95 CPU and memory usage per pod
- Compares against current resource requests
- Generates actionable recommendations
- Estimates cost savings (monthly/annual)

**Key Capabilities:**
- Identifies underutilization (P95 < 40% of request)
- Identifies overutilization (P95 > 85% of request)
- Recommends with 20% safety buffer
- Supports custom lookback periods

### 2. Vertical Pod Autoscaler (VPA) ✅

- Kubernetes VPA manifests for non-critical services
- Automatic resource request/limit adjustment
- Configurable update modes (Off, Initial, Recreate, Auto)
- Min/max resource bounds

**Enabled Services:**
- Gateway
- MCPJungle
- Mem0
- Grafana
- Jaeger

### 3. Qdrant Archival Policy ✅

- Moves embeddings older than 90 days to MinIO
- Compresses archives with gzip
- Supports workspace-based filtering
- Batch processing for efficiency
- Dry-run mode for testing
- Archive restoration capability

**Key Features:**
- Configurable age threshold (default: 90 days)
- Configurable batch size (default: 1000 points)
- Weekly CronJob (configurable schedule)
- MinIO cold storage integration

### 4. Cost Dashboard ✅

- Grafana dashboard for cost monitoring
- Real-time and historical views
- Per-workspace cost breakdown
- Token usage tracking
- Resource allocation visualization

**Dashboard Panels:**
- Estimated Monthly Cost gauge
- Cost Trend by Workspace (time series)
- Token Usage & Cost table (30 days)
- Cost Distribution pie chart
- CPU/Memory Usage by Pod
- Detailed Metering Events

## 🔗 Integration Points

### Prometheus

**Required Metrics:**
- `container_cpu_usage_seconds_total` - CPU usage per container
- `container_memory_working_set_bytes` - Memory usage per container
- `kube_pod_container_resource_requests` - Resource requests (kube-state-metrics)

**Queries:**
- P95 CPU: `quantile_over_time(0.95, rate(container_cpu_usage_seconds_total[5m])[7d:1h])`
- P95 Memory: `quantile_over_time(0.95, container_memory_working_set_bytes[7d:1h])`

### PostgreSQL

**Required Tables:**
- `workspace_metering_events` - Token usage and metering data

**Schema:**
```sql
CREATE TABLE workspace_metering_events (
  id SERIAL PRIMARY KEY,
  event_id VARCHAR(255) UNIQUE NOT NULL,
  workspace_id VARCHAR(255) NOT NULL,
  user_id VARCHAR(255),
  meter_key VARCHAR(128) NOT NULL,
  quantity DOUBLE PRECISION NOT NULL,
  request_id VARCHAR(255),
  metadata JSONB,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

### Qdrant

**Required Fields:**
- `ingested_at` - ISO timestamp in payload
- `workspace_id` - Workspace identifier in payload

**Collections:**
- `documents` (default, configurable)

### MinIO

**Buckets:**
- `qdrant-archive` (default, configurable)

**Archive Format:**
```
{workspace_id}/{collection_name}/archive_{timestamp}_batch_{num}.json.gz
```

### Grafana

**Data Sources:**
- Prometheus (uid: `prometheus`)
- PostgreSQL (uid: `postgres`)

**Dashboard UID:**
- `cost-optimization`

## 📊 Metrics & Calculations

### Cost Model

**Token-based pricing:**
- Base rate: $1 per 1 million tokens
- Formula: `sum(rate(tokens[period]) * period) * $0.000001`

**Compute pricing (estimates):**
- CPU: $30/month per core
- Memory: $4/month per GB

### Utilization Thresholds

| Metric | Underutilized | Optimal | Overutilized |
|--------|--------------|---------|--------------|
| CPU | P95 < 40% | 40% ≤ P95 ≤ 85% | P95 > 85% |
| Memory | P95 < 40% | 40% ≤ P95 ≤ 85% | P95 > 85% |

### Safety Buffers

- CPU: 20% above P95 usage
- Memory: 20% above P95 usage

Example: If P95 CPU = 0.5 cores, recommend 0.6 cores (0.5 * 1.2)

## 🚀 Usage Examples

### Analyze Resource Usage

```bash
# Basic analysis
python scripts/observability/analyze_resource_usage.py

# Custom Prometheus URL
PROMETHEUS_URL=http://prometheus:9090 python scripts/observability/analyze_resource_usage.py

# 14-day lookback
LOOKBACK_DAYS=14 python scripts/observability/analyze_resource_usage.py
```

### Apply Recommendations

```bash
# Generate Helm patch
python scripts/observability/apply_recommendations.py \
  resource_recommendations.json \
  -o helm-values-patch.yaml

# Review summary
python scripts/observability/apply_recommendations.py \
  resource_recommendations.json \
  --summary

# Interactive mode
python scripts/observability/apply_recommendations.py \
  resource_recommendations.json \
  --interactive
```

### Qdrant Archival

```bash
# Dry run (no deletion)
DRY_RUN=true python scripts/observability/qdrant_archival_service.py

# Archive with custom age
ARCHIVAL_AGE_DAYS=180 python scripts/observability/qdrant_archival_service.py

# Filter by workspace
WORKSPACE_ID=acme python scripts/observability/qdrant_archival_service.py
```

### Enable VPA

```bash
# Enable in Helm
helm upgrade ai-platform ./helm/ai-platform \
  --set vpa.enabled=true \
  --set vpa.updateMode=Auto

# Check VPA status
kubectl get vpa -n ai-platform
kubectl describe vpa gateway-vpa -n ai-platform
```

### Enable Archival CronJob

```bash
# Enable in Helm
helm upgrade ai-platform ./helm/ai-platform \
  --set qdrantArchival.enabled=true \
  --set qdrantArchival.archivalAgeDays=90

# Check CronJob
kubectl get cronjob qdrant-archival -n ai-platform
kubectl get jobs -n ai-platform -l app.kubernetes.io/name=qdrant-archival
```

## 📦 Dependencies

### Python Packages

Required packages (add to `requirements-test.txt`):

```
requests>=2.31.0          # For Prometheus API
pyyaml>=6.0              # For Helm values
qdrant-client>=1.7.0     # For Qdrant archival
minio>=7.2.0             # For MinIO cold storage
```

### Kubernetes Components

- **kube-state-metrics** - For resource request metrics
- **Prometheus** - For metrics collection
- **VPA admission controller** - For VPA Auto mode
- **MinIO** - For cold storage

## 🔐 Security Considerations

### Secrets Required

1. **MinIO credentials** - `minio-credentials` secret
   ```yaml
   apiVersion: v1
   kind: Secret
   metadata:
     name: minio-credentials
   data:
     accessKey: <base64>
     secretKey: <base64>
   ```

2. **PostgreSQL credentials** - `postgres-credentials` secret

3. **Grafana credentials** - `grafana-credentials` secret

### RBAC Requirements

- Read access to Prometheus API
- Read access to Qdrant collections
- Read/write access to MinIO bucket
- Read access to kube-state-metrics

## 🧪 Testing

### Unit Tests (to be created)

```bash
# Test resource analyzer
pytest tests/unit/test_resource_analyzer.py

# Test archival service
pytest tests/unit/test_qdrant_archival.py

# Test recommendation applier
pytest tests/unit/test_apply_recommendations.py
```

### Integration Tests (to be created)

```bash
# Test end-to-end workflow
pytest tests/integration/test_cost_optimization_workflow.py
```

### Manual Testing

1. **Resource Analyzer**
   - Verify Prometheus connection
   - Validate P95 calculations
   - Check recommendation logic
   - Verify cost estimates

2. **VPA**
   - Deploy test workload
   - Enable VPA
   - Verify recommendations
   - Check pod updates

3. **Archival**
   - Run dry-run mode
   - Verify archive creation
   - Test restoration
   - Check MinIO storage

4. **Dashboard**
   - Verify data sources
   - Check panel queries
   - Validate calculations
   - Test filters

## 📈 Expected Outcomes

### Cost Savings

**Conservative estimates:**
- 20-30% reduction in overprovisioned resources
- 5-10% improvement in cluster utilization
- 15-25% reduction in storage costs (with archival)

**Example savings (for 50-pod cluster):**
- CPU: 10-15 cores saved → $300-450/month
- Memory: 30-50 GB saved → $120-200/month
- Storage: 50-100 GB archived → $10-20/month
- **Total: $430-670/month ($5,160-8,040/year)**

### Performance Improvements

- Reduced cluster resource contention
- Faster pod scheduling
- Improved resource allocation
- Better workload placement

### Operational Benefits

- Automated resource optimization
- Proactive cost monitoring
- Historical cost analysis
- Per-workspace accountability

## 🎓 Learning Resources

### Internal Documentation

- `scripts/observability/README.md` - Full documentation
- `COST_OPTIMIZATION_QUICKSTART.md` - Quick start guide
- Dashboard inline documentation

### External Resources

- [Kubernetes VPA](https://github.com/kubernetes/autoscaler/tree/master/vertical-pod-autoscaler)
- [Prometheus Query API](https://prometheus.io/docs/prometheus/latest/querying/api/)
- [MinIO Python SDK](https://min.io/docs/minio/linux/developers/python/minio-py.html)
- [Qdrant Python Client](https://qdrant.tech/documentation/quick-start/)
- [Grafana Dashboards](https://grafana.com/docs/grafana/latest/dashboards/)

## 🔄 Maintenance

### Weekly Tasks

- [ ] Review cost dashboard
- [ ] Check for cost anomalies
- [ ] Verify VPA recommendations

### Monthly Tasks

- [ ] Run resource analyzer
- [ ] Review and apply recommendations
- [ ] Audit archived data
- [ ] Update documentation

### Quarterly Tasks

- [ ] Review VPA policies
- [ ] Adjust archival thresholds
- [ ] Update cost models
- [ ] Train team on new features

---

**Created**: 2024-03-15  
**Version**: 1.0.0  
**Status**: ✅ Complete
