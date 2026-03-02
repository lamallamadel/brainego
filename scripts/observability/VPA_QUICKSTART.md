# VPA Automation Quick Start Guide

## 🚀 Quick Start (5 Minutes)

### Option 1: Automated Workflow Script (Recommended)
```bash
# Dry-run mode (safe, no changes)
./scripts/observability/vpa_automation_workflow.sh

# Review the outputs, then apply for real
./scripts/observability/vpa_automation_workflow.sh --production

# Deploy to cluster
helm upgrade ai-platform helm/ai-platform --set vpa.enabled=true
```

### Option 2: Manual Step-by-Step
```bash
# 1. Analyze resource usage (queries Prometheus)
python scripts/observability/analyze_resource_usage.py

# 2. Generate VPA manifests (dry-run first)
DRY_RUN=true python scripts/observability/apply_vpa_recommendations.py

# 3. Review the summary
cat vpa_application_summary.json

# 4. Apply for real
DRY_RUN=false python scripts/observability/apply_vpa_recommendations.py

# 5. Deploy to cluster
kubectl apply -f manifests/vpa/
# OR
helm upgrade ai-platform helm/ai-platform --set vpa.enabled=true
```

### Option 3: Test with Sample Data (No Prometheus Required)
```bash
# Test the automation with pre-generated sample data
python scripts/observability/test_vpa_automation.py
```

## 📊 What It Does

1. **Analyzes** 7 days of Prometheus metrics (P95 CPU/memory usage)
2. **Generates** right-sizing recommendations
3. **Creates** VPA manifests with smart updateMode:
   - `Auto` for non-critical services (api-server, gateway, mcpjungle)
   - `Initial` for StatefulSets (redis, qdrant, postgres, neo4j, minio)
4. **Validates** changes are within 50% delta (prevents thrashing)
5. **Updates** Grafana cost dashboard with savings metrics

## 🎯 Key Benefits

- **Automated Right-Sizing:** No manual calculation needed
- **Cost Savings:** Typically 20-40% reduction in resource costs
- **Thrashing Prevention:** Validates changes to prevent resource oscillation
- **StatefulSet Safety:** Uses `Initial` mode for databases (no restarts)
- **Grafana Integration:** Visualize savings in Cost Optimization dashboard

## 🔒 Safety Features

- **50% Change Threshold:** Rejects recommendations that change resources by >50%
- **Dry-Run Mode:** Test before applying (enabled by default)
- **Conservative Bounds:** VPA min/max set to ±30% of recommendation
- **StatefulSet Protection:** No automatic restarts for databases

## 📈 Expected Results

**Before VPA:**
```
api-server:  CPU=1.0 cores, Memory=2.0 Gi (45% utilized)
gateway:     CPU=0.5 cores, Memory=1.0 Gi (60% utilized)
mcpjungle:   CPU=2.0 cores, Memory=4.0 Gi (40% utilized)
```

**After VPA:**
```
api-server:  CPU=0.54 cores, Memory=1.44 Gi (80% utilized)
gateway:     CPU=0.36 cores, Memory=0.72 Gi (83% utilized)
mcpjungle:   CPU=0.96 cores, Memory=2.4 Gi (83% utilized)

Total Savings: $137/month, $1,654/year
```

## 🛠️ Configuration

### Environment Variables
```bash
# Prometheus endpoint
export PROMETHEUS_URL=http://prometheus:9090

# Kubernetes namespace
export NAMESPACE=ai-platform

# Enable/disable dry-run
export DRY_RUN=true

# Analysis lookback period
export LOOKBACK_DAYS=7
```

### Helm Values (values.yaml)
```yaml
vpa:
  enabled: true
  
  # Override per-service updateMode
  apiServer:
    updateMode: Auto  # Can be: Off, Initial, Recreate, Auto
    minAllowed:
      cpu: 100m
      memory: 256Mi
    maxAllowed:
      cpu: 2
      memory: 4Gi
```

## 📊 Monitoring

### Check VPA Status
```bash
# List all VPAs
kubectl get vpa -n ai-platform

# View recommendations
kubectl describe vpa api-server-vpa -n ai-platform

# Check pod restarts (watch for thrashing)
kubectl get pods -n ai-platform | awk '{print $1, $4}'
```

### Grafana Dashboard
Navigate to: **Cost Optimization & FinOps**

New panels added:
- VPA Potential Monthly Savings
- VPA-Managed Resource Requests
- VPA CPU Utilization vs Requests
- VPA Memory Utilization vs Requests
- VPA Pod Evictions & Restarts

## ⚠️ Troubleshooting

### Issue: High Pod Restart Rate
```bash
# Check if VPA is causing thrashing
kubectl get events -n ai-platform | grep -i evict

# Solution: Widen min/max bounds or switch to Initial mode
helm upgrade ai-platform helm/ai-platform \
  --set vpa.apiServer.updateMode=Initial
```

### Issue: No Recommendations Generated
```bash
# Verify Prometheus has data
curl http://prometheus:9090/api/v1/query?query=container_cpu_usage_seconds_total

# Check kube-state-metrics is running
kubectl get pods -n kube-system | grep kube-state-metrics

# Increase lookback period
LOOKBACK_DAYS=14 python scripts/observability/analyze_resource_usage.py
```

### Issue: VPA Not Applying Recommendations
```bash
# Check VPA controller is running
kubectl get pods -n kube-system | grep vpa

# Verify VPA CRDs exist
kubectl get crd | grep verticalpodautoscaler

# Check VPA logs
kubectl logs -n kube-system -l app=vpa-recommender
```

## 🔄 Update Modes Explained

### Auto Mode (Recommended for Stateless Services)
- **What:** VPA automatically evicts and recreates pods with new resources
- **When:** Pod resource needs change significantly
- **Pros:** Fully automated, continuously optimized
- **Cons:** Brief downtime during pod restart
- **Use for:** api-server, gateway, mcpjungle, mem0, grafana, jaeger

### Initial Mode (Recommended for StatefulSets)
- **What:** VPA only applies recommendations to new pods (not existing)
- **When:** Pod is first created or manually restarted
- **Pros:** No automatic restarts, safe for databases
- **Cons:** Requires manual restart to apply changes
- **Use for:** redis, qdrant, postgres, neo4j, minio

### Recreate Mode (Not Recommended)
- **What:** VPA recreates pods immediately (no eviction)
- **Pros:** Fast application of changes
- **Cons:** Disruptive, no graceful shutdown
- **Use for:** Never (use Auto instead)

### Off Mode
- **What:** VPA only monitors and recommends (no changes)
- **Pros:** Safe observation mode
- **Cons:** No automation
- **Use for:** Initial VPA testing

## 📅 Recommended Schedule

```bash
# Weekly automated run (cron job)
0 2 * * 0 /path/to/vpa_automation_workflow.sh --production

# Or manually
# Monday: Analyze
# Tuesday: Review + Apply (dry-run)
# Wednesday: Deploy to staging
# Thursday: Monitor staging
# Friday: Deploy to production
```

## 🔗 Related Documentation

- [Full VPA Documentation](./README_VPA.md)
- [Kubernetes VPA Official Docs](https://github.com/kubernetes/autoscaler/tree/master/vertical-pod-autoscaler)
- [Cost Optimization Dashboard](../../configs/grafana/dashboards/cost-optimization.json)

## 💡 Pro Tips

1. **Start Conservative:** Use Initial mode first, monitor for 1 week, then switch to Auto
2. **Monitor Grafana:** Watch CPU/Memory utilization panels to verify VPA effectiveness
3. **Set Alerts:** Alert on pod restart count > 5/hour (thrashing indicator)
4. **Document Changes:** Keep history of VPA config changes in git
5. **Test in Staging:** Always validate VPA settings in non-prod first
6. **Review Weekly:** Run analysis weekly to adapt to workload changes
7. **Avoid Over-Optimization:** Target 60-80% utilization (not 90%+)

## ❓ FAQ

**Q: Will VPA cause downtime?**
A: Only with `Auto` mode. StatefulSets use `Initial` mode (no restarts).

**Q: How often should I run the automation?**
A: Weekly is recommended. Daily for high-variance workloads.

**Q: Can I override VPA recommendations manually?**
A: Yes, edit `helm/ai-platform/values.yaml` and redeploy.

**Q: What if VPA thrashes (constant restarts)?**
A: Widen min/max bounds or switch to `Initial` mode.

**Q: Does VPA work with HPA?**
A: Yes, but avoid targeting the same resource (e.g., CPU). VPA for requests, HPA for replicas.

**Q: What's the typical cost savings?**
A: 20-40% reduction in resource costs for most workloads.

---

**Need Help?** Check [README_VPA.md](./README_VPA.md) for detailed documentation.
