# Cost Optimization & Resource Right-Sizing - Quick Start

This guide helps you quickly set up and use the cost optimization features of the AI platform.

## 🎯 What's Included

1. **Resource Usage Analyzer** - Analyzes 7-day P95 CPU/memory usage and generates right-sizing recommendations
2. **Vertical Pod Autoscaler (VPA)** - Automatically adjusts resource requests/limits for non-critical services
3. **Qdrant Archival Service** - Moves embeddings older than 90 days to MinIO cold storage
4. **Cost Dashboard** - Grafana dashboard showing spend per workspace based on token metering

## 🚀 Quick Start (5 minutes)

### Step 1: Analyze Resource Usage

Run the resource analyzer to identify optimization opportunities:

```bash
# Set Prometheus URL (if not default)
export PROMETHEUS_URL=http://prometheus:9090

# Run analysis
python scripts/observability/analyze_resource_usage.py

# View recommendations
cat resource_recommendations.json
```

**Expected output:**
```
================================================================================
SUMMARY
================================================================================
Total workloads analyzed: 25
Recommendations generated: 12

Cost Savings Potential:
  CPU cores saved: 8.50
  Memory (Gi) saved: 24.30
  Estimated monthly savings: $352.20
  Estimated annual savings: $4226.40
```

### Step 2: Review Recommendations

Generate a summary of recommendations:

```bash
python scripts/observability/apply_recommendations.py \
  resource_recommendations.json \
  --summary
```

### Step 3: Apply Recommendations (Staging First!)

Generate a Helm values patch:

```bash
python scripts/observability/apply_recommendations.py \
  resource_recommendations.json \
  -o helm-values-patch.yaml
```

Test in staging:

```bash
helm upgrade ai-platform ./helm/ai-platform \
  -f helm-values-patch.yaml \
  --dry-run \
  --debug
```

Apply to staging:

```bash
helm upgrade ai-platform ./helm/ai-platform \
  -f helm-values-patch.yaml \
  -n ai-platform-staging
```

### Step 4: Enable Cost Dashboard

The cost dashboard is automatically provisioned if you have Grafana configured. Access it at:

```
http://<grafana-url>/d/cost-optimization/cost-optimization-finops
```

### Step 5: Monitor Results

Watch the Cost Dashboard for 24-48 hours to ensure:
- No OOM kills
- No CPU throttling
- Service performance remains stable
- Cost savings are realized

## 📊 Understanding Recommendations

### Action Types

- **reduce_cpu** - CPU is underutilized (P95 < 40% of request)
- **reduce_memory** - Memory is underutilized (P95 < 40% of request)
- **reduce_both** - Both CPU and memory are underutilized
- **increase_cpu** - CPU is overutilized (P95 > 85% of request)
- **increase_memory** - Memory is overutilized (P95 > 85% of request)
- **increase_both** - Both CPU and memory are overutilized
- **none** - No action recommended (utilization is optimal)

### Thresholds

- **Underutilization**: P95 usage < 40% of request
- **Optimal**: P95 usage between 40% and 85% of request
- **Overutilization**: P95 usage > 85% of request

### Safety Buffers

All recommendations include a 20% safety buffer to prevent resource exhaustion.

## 🔄 Advanced Features

### Vertical Pod Autoscaler (VPA)

Enable VPA to automatically right-size pods:

```bash
# Install VPA (if not already installed)
kubectl apply -f https://raw.githubusercontent.com/kubernetes/autoscaler/master/vertical-pod-autoscaler/deploy/vpa-v1-crd-gen.yaml

# Enable in Helm
helm upgrade ai-platform ./helm/ai-platform \
  --set vpa.enabled=true \
  --set vpa.updateMode=Auto
```

**VPA Update Modes:**
- `Off` - Recommendations only, no updates
- `Initial` - Updates at pod creation only
- `Recreate` - Updates by evicting and recreating pods
- `Auto` - Updates without eviction (requires admission controller)

### Qdrant Archival

Archive old embeddings to cold storage:

```bash
# Enable archival CronJob
helm upgrade ai-platform ./helm/ai-platform \
  --set qdrantArchival.enabled=true \
  --set qdrantArchival.archivalAgeDays=90

# Or run manually
python scripts/observability/qdrant_archival_service.py

# Test with dry-run first
DRY_RUN=true python scripts/observability/qdrant_archival_service.py
```

### Automated Workflow

Run the complete cost optimization workflow:

```bash
# Set environment variables
export PROMETHEUS_URL=http://prometheus:9090
export LOOKBACK_DAYS=7
export RUN_ARCHIVAL=true

# Run workflow
bash scripts/observability/cost_optimization_workflow.sh
```

This will:
1. Analyze resource usage
2. Generate recommendations
3. Create Helm values patch
4. Run Qdrant archival (if enabled)
5. Generate summary report

## 📈 Cost Dashboard Metrics

The Grafana dashboard shows:

### Key Metrics

- **Estimated Monthly Cost** - Total estimated cost across all workspaces
- **Cost Trend by Workspace** - Hourly cost trends per workspace
- **Token Usage Table** - Detailed usage and cost per workspace (30 days)
- **Cost Distribution** - Pie chart by workspace
- **CPU/Memory Usage** - Resource usage by pod
- **Metering Events** - Detailed event log (7 days)

### Data Sources

- **Prometheus** - Real-time metrics and resource usage
- **PostgreSQL** - Metering event history

### Cost Model

Token-based pricing: **$1 per 1 million tokens**

```
Monthly Cost = sum(rate(tokens[30d]) * 30) * $0.000001
```

## 🔍 Troubleshooting

### "Connection refused" to Prometheus

Port-forward to Prometheus:

```bash
kubectl port-forward svc/prometheus 9090:9090 -n ai-platform
export PROMETHEUS_URL=http://localhost:9090
```

### No metrics found

Ensure kube-state-metrics is running:

```bash
kubectl get pods -n kube-system -l app.kubernetes.io/name=kube-state-metrics
```

### VPA not updating pods

Check VPA admission controller:

```bash
kubectl get pods -n kube-system -l app=vpa-admission-controller
kubectl logs -n kube-system -l app=vpa-admission-controller
```

### Dashboard shows no data

Verify data sources:

```bash
# Check Prometheus
curl http://grafana:3000/api/datasources -u admin:password

# Check PostgreSQL
kubectl exec -it postgres-0 -n ai-platform -- \
  psql -U ai_user -d ai_platform -c \
  "SELECT COUNT(*) FROM workspace_metering_events;"
```

## 💡 Best Practices

### Resource Right-Sizing

1. ✅ Run analysis weekly
2. ✅ Review recommendations carefully
3. ✅ Test in staging first
4. ✅ Monitor after changes (24-48 hours)
5. ✅ Keep 20% safety buffers

### VPA Configuration

1. ✅ Start with `updateMode: Off` (recommendations only)
2. ✅ Use `updateMode: Initial` for stateful workloads
3. ✅ Use `updateMode: Auto` for stateless services
4. ✅ Set appropriate min/max bounds
5. ❌ Don't VPA critical services (databases, core API)

### Qdrant Archival

1. ✅ Start with dry-run mode
2. ✅ Archive incrementally (start with small age thresholds)
3. ✅ Monitor MinIO capacity
4. ✅ Test restoration before enabling
5. ✅ Document archive locations

### Cost Monitoring

1. ✅ Set up cost spike alerts
2. ✅ Review dashboard weekly
3. ✅ Track by workspace
4. ✅ Correlate with usage patterns
5. ✅ Set workspace budgets

## 🎓 Next Steps

### Week 1: Baseline

- Run resource analyzer
- Review recommendations
- Set up cost dashboard
- Document current costs

### Week 2: Test

- Apply top 5 recommendations in staging
- Monitor for 1 week
- Validate no regressions
- Measure actual savings

### Week 3: Production

- Apply tested recommendations to production
- Enable VPA for non-critical services
- Set up archival CronJob
- Configure cost alerts

### Week 4+: Continuous Optimization

- Review cost dashboard weekly
- Re-run analyzer monthly
- Adjust VPA limits as needed
- Monitor archival efficiency

## 📚 Related Documentation

- [Full Documentation](scripts/observability/README.md) - Comprehensive guide
- [Prometheus Query API](https://prometheus.io/docs/prometheus/latest/querying/api/)
- [VPA Documentation](https://github.com/kubernetes/autoscaler/tree/master/vertical-pod-autoscaler)
- [MinIO Python SDK](https://min.io/docs/minio/linux/developers/python/minio-py.html)
- [Grafana Dashboards](https://grafana.com/docs/grafana/latest/dashboards/)

## 🆘 Support

For issues or questions:

1. Check [Troubleshooting](#-troubleshooting) section
2. Review logs: `kubectl logs <pod-name> -n ai-platform`
3. Consult [Full Documentation](scripts/observability/README.md)
4. File an issue with:
   - Error messages
   - Recommendation output
   - Prometheus/Grafana screenshots

---

**Last Updated**: 2024-03-15  
**Version**: 1.0.0
