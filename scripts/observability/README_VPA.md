# VPA (Vertical Pod Autoscaler) Automation

## Overview

This directory contains automation scripts for Kubernetes Vertical Pod Autoscaler (VPA) management. The system analyzes resource usage from Prometheus, generates right-sizing recommendations, and automatically creates VPA manifests with intelligent updateMode selection.

## Components

### 1. Resource Usage Analyzer (`analyze_resource_usage.py`)

Queries Prometheus for 7-day P95 CPU/memory usage and generates right-sizing recommendations.

**Features:**
- Analyzes P95 resource usage over 7 days
- Identifies over/under-utilized pods
- Calculates potential cost savings
- Outputs recommendations in JSON format

**Usage:**
```bash
# With default settings
python scripts/observability/analyze_resource_usage.py

# With custom settings
PROMETHEUS_URL=http://prometheus:9090 \
OUTPUT_FILE=resource_recommendations.json \
LOOKBACK_DAYS=7 \
python scripts/observability/analyze_resource_usage.py
```

**Output:**
```json
{
  "generated_at": "2025-01-01T00:00:00.000000",
  "lookback_days": 7,
  "summary": {
    "total_workloads_analyzed": 50,
    "recommendations_generated": 15,
    "cost_savings": {
      "total_cpu_cores_saved": 5.2,
      "total_memory_gi_saved": 12.8,
      "estimated_monthly_savings_usd": 207.20,
      "estimated_annual_savings_usd": 2486.40
    }
  },
  "recommendations": [...]
}
```

### 2. VPA Recommendations Applier (`apply_vpa_recommendations.py`)

Reads recommendations from `analyze_resource_usage.py` and generates VPA manifests with intelligent configuration.

**Features:**
- **Smart updateMode Selection:**
  - `Auto` for non-critical services (api-server, gateway, mcpjungle, etc.)
  - `Initial` for StatefulSets (redis, qdrant, postgres, neo4j, minio)
- **Thrashing Prevention:** Validates resource changes are within 50% delta
- **Dry-run Mode:** Test configurations before applying
- **Multi-format Output:**
  - Helm templates with value overrides
  - Raw Kubernetes YAML manifests
  - JSON summary report
- **Grafana Integration:** Updates cost dashboard with savings metrics

**Usage:**
```bash
# Dry-run mode (default - safe to test)
DRY_RUN=true python scripts/observability/apply_vpa_recommendations.py

# Production mode (applies changes)
DRY_RUN=false python scripts/observability/apply_vpa_recommendations.py

# With custom settings
INPUT_FILE=resource_recommendations.json \
OUTPUT_HELM_TEMPLATE=helm/ai-platform/templates/vpa.yaml \
OUTPUT_RAW_DIR=manifests/vpa \
GRAFANA_DASHBOARD=configs/grafana/dashboards/cost-optimization.json \
NAMESPACE=ai-platform \
DRY_RUN=false \
SUMMARY_OUTPUT=vpa_application_summary.json \
python scripts/observability/apply_vpa_recommendations.py
```

## Update Modes

### Auto Mode (Non-Critical Services)
**Services:** api-server, gateway, mcpjungle, mem0, grafana, jaeger, prometheus, alertmanager

VPA automatically applies recommendations by:
1. Evicting pods when resources need adjustment
2. Recreating pods with new resource requests
3. Kubernetes scheduler places new pods on appropriate nodes

**Pros:**
- Fully automated
- Continuously optimized
- Quick response to workload changes

**Cons:**
- Causes pod restarts
- Brief service disruption during eviction

### Initial Mode (StatefulSets)
**Services:** redis, qdrant, postgres, neo4j, minio

VPA only applies recommendations to new pods:
1. Recommendations calculated continuously
2. Applied only when pods are created (not existing ones)
3. No automatic evictions

**Pros:**
- No service disruption
- Safe for stateful workloads
- Data persistence guaranteed

**Cons:**
- Requires manual pod restart to apply changes
- Less responsive to usage changes

## Thrashing Prevention

The system validates resource changes to prevent VPA thrashing:

- **Maximum Change Delta:** 50%
- **Validation:** If recommended change exceeds 50%, it's rejected
- **Safety Bounds:** VPA min/max set to ±30% of recommendation

Example:
```python
# Current CPU: 1.0 cores
# Recommended CPU: 1.8 cores (80% increase)
# Result: REJECTED (exceeds 50% threshold)

# Current CPU: 1.0 cores
# Recommended CPU: 1.4 cores (40% increase)
# Result: ACCEPTED
# VPA bounds: min=0.98 (1.4 * 0.7), max=1.82 (1.4 * 1.3)
```

## Grafana Dashboard Integration

The automation updates the Cost Optimization dashboard with VPA metrics:

### New Panels Added:

1. **VPA Potential Monthly Savings** (Stat)
   - Shows estimated monthly cost savings
   - Updated automatically by apply_vpa_recommendations.py

2. **VPA-Managed Resource Requests** (Table)
   - Current CPU/memory requests for VPA-managed pods
   - Shows effectiveness of right-sizing

3. **VPA CPU Utilization vs Requests** (Timeseries)
   - Tracks CPU utilization relative to requests
   - Target: 60-80% utilization

4. **VPA Memory Utilization vs Requests** (Timeseries)
   - Tracks memory utilization relative to requests
   - Target: 60-80% utilization

5. **VPA Pod Evictions & Restarts** (Table)
   - Monitors VPA-induced pod restarts
   - Alert if restart count is high (thrashing indicator)

## Workflow

### Automated Workflow (Recommended)
```bash
# 1. Analyze resource usage (run weekly)
python scripts/observability/analyze_resource_usage.py

# 2. Generate VPA manifests (dry-run first)
DRY_RUN=true python scripts/observability/apply_vpa_recommendations.py

# 3. Review summary report
cat vpa_application_summary.json

# 4. Apply if satisfied
DRY_RUN=false python scripts/observability/apply_vpa_recommendations.py

# 5. Deploy via Helm
helm upgrade ai-platform helm/ai-platform \
  --set vpa.enabled=true \
  --namespace ai-platform

# 6. Monitor in Grafana
# Navigate to: Cost Optimization & FinOps dashboard
```

### Manual Workflow
```bash
# 1. Generate recommendations
python scripts/observability/analyze_resource_usage.py

# 2. Generate VPA manifests
python scripts/observability/apply_vpa_recommendations.py

# 3. Apply directly with kubectl
kubectl apply -f manifests/vpa/

# 4. Monitor VPA status
kubectl get vpa -n ai-platform
kubectl describe vpa <name>-vpa -n ai-platform
```

## Monitoring

### Check VPA Status
```bash
# List all VPAs
kubectl get vpa -n ai-platform

# Describe specific VPA
kubectl describe vpa gateway-vpa -n ai-platform

# View VPA recommendations
kubectl get vpa -n ai-platform -o json | jq '.items[] | {name: .metadata.name, mode: .spec.updatePolicy.updateMode, recommendation: .status.recommendation}'
```

### Monitor Pod Restarts
```bash
# Check restart counts
kubectl get pods -n ai-platform -o wide | awk '{print $1, $4}'

# Watch for VPA-induced restarts
kubectl get events -n ai-platform --sort-by='.lastTimestamp' | grep -i evict
```

### Grafana Alerts
Configure alerts in Cost Optimization dashboard:
- **High Restart Count:** Alert if pod restarts > 5 in 1 hour
- **Low Utilization:** Alert if utilization < 40% for 24 hours
- **High Utilization:** Alert if utilization > 90% for 1 hour

## Configuration

### Helm Values (values.yaml)
```yaml
vpa:
  enabled: true  # Enable/disable VPA globally
  
  # Per-service configuration
  apiServer:
    updateMode: Auto  # Override default
    minAllowed:
      cpu: 100m
      memory: 256Mi
    maxAllowed:
      cpu: 2
      memory: 4Gi
  
  # StatefulSet example
  redis:
    updateMode: Initial  # Safe for stateful workloads
    minAllowed:
      cpu: 100m
      memory: 256Mi
    maxAllowed:
      cpu: 2
      memory: 4Gi
```

### Environment Variables

**analyze_resource_usage.py:**
- `PROMETHEUS_URL`: Prometheus endpoint (default: http://prometheus:9090)
- `OUTPUT_FILE`: Output JSON file (default: resource_recommendations.json)
- `LOOKBACK_DAYS`: Analysis window in days (default: 7)

**apply_vpa_recommendations.py:**
- `INPUT_FILE`: Input recommendations JSON (default: resource_recommendations.json)
- `OUTPUT_HELM_TEMPLATE`: Helm template path (default: helm/ai-platform/templates/vpa.yaml)
- `OUTPUT_RAW_DIR`: Raw manifests directory (default: manifests/vpa)
- `GRAFANA_DASHBOARD`: Dashboard JSON path (default: configs/grafana/dashboards/cost-optimization.json)
- `NAMESPACE`: Kubernetes namespace (default: ai-platform)
- `DRY_RUN`: Test mode flag (default: false)
- `SUMMARY_OUTPUT`: Summary report path (default: vpa_application_summary.json)

## Cost Savings Calculation

The system estimates cost savings using cloud provider averages:
- **CPU:** $30/month per core
- **Memory:** $4/month per GB

Example:
```
Savings: 5.2 CPU cores + 12.8 Gi memory
Monthly: (5.2 * $30) + (12.8 * $4) = $156 + $51.20 = $207.20
Annual: $207.20 * 12 = $2,486.40
```

## Troubleshooting

### VPA Not Applying Recommendations
```bash
# Check VPA controller logs
kubectl logs -n kube-system -l app=vpa-recommender

# Verify VPA CRDs installed
kubectl get crd | grep verticalpodautoscaler

# Check VPA status
kubectl describe vpa <name>-vpa -n ai-platform
```

### High Pod Restart Rate (Thrashing)
```bash
# Check restart counts
kubectl get pods -n ai-platform | grep -v "0/0"

# View VPA events
kubectl get events -n ai-platform | grep -i vpa

# Adjust VPA bounds in values.yaml
# Increase minAllowed/maxAllowed ranges
# Or switch to updateMode: Initial
```

### Recommendations Not Generated
```bash
# Verify Prometheus metrics available
curl http://prometheus:9090/api/v1/query?query=container_cpu_usage_seconds_total

# Check kube-state-metrics
kubectl get pods -n kube-system | grep kube-state-metrics

# Run analyzer with debug logging
python -m pdb scripts/observability/analyze_resource_usage.py
```

## Best Practices

1. **Start with Dry-Run:** Always test with `DRY_RUN=true` first
2. **Monitor for 1 Week:** Let VPA collect data before trusting recommendations
3. **Use Initial Mode for StatefulSets:** Prevent data loss from restarts
4. **Set Conservative Bounds:** Start with wider min/max ranges
5. **Monitor Grafana Dashboard:** Watch for thrashing indicators
6. **Review Weekly:** Run analysis regularly to adapt to workload changes
7. **Document Changes:** Keep history of VPA configuration changes
8. **Test in Staging:** Validate VPA settings in non-production first

## References

- [Kubernetes VPA Documentation](https://github.com/kubernetes/autoscaler/tree/master/vertical-pod-autoscaler)
- [VPA Best Practices](https://cloud.google.com/kubernetes-engine/docs/concepts/verticalpodautoscaler)
- [Resource Management in Kubernetes](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/)
