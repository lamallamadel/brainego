# Multi-Region Deployment Quick Start

Fast-track guide to deploying AI Platform across multiple regions.

## 🚀 Quick Deploy (5 Minutes)

### Prerequisites Check

```bash
# Verify tools
kubectl version --client
helm version
python3 --version

# Verify cluster access for each region
kubectl config get-contexts
```

### One-Command Deployment

```bash
# Deploy to all regions at once
chmod +x scripts/deploy/deploy_all_regions.sh
./scripts/deploy/deploy_all_regions.sh
```

### Per-Region Deployment

If you prefer step-by-step control:

```bash
# 1. Deploy primary region (us-west-1)
python3 scripts/deploy/deploy_region.py \
  --region us-west-1 \
  --cluster ai-platform-us-west-1 \
  --values-file helm/ai-platform/values-multi-region.yaml

# 2. Deploy secondary regions
for region in us-east-1 eu-west-1 ap-southeast-1; do
  python3 scripts/deploy/deploy_region.py \
    --region $region \
    --cluster ai-platform-$region \
    --values-file helm/ai-platform/values-multi-region.yaml
done

# 3. Setup replication
python3 scripts/deploy/setup_qdrant_replication.py \
  --regions us-west-1 us-east-1 eu-west-1 ap-southeast-1
```

## 📊 Verify Deployment

### Check Pod Status

```bash
# Check all regions
for region in us-west-1 us-east-1 eu-west-1 ap-southeast-1; do
  echo "=== $region ==="
  kubectl --context=ai-platform-$region get pods -n ai-platform
done
```

### Test Endpoints

```bash
# Health checks
curl https://us-west-1.ai-platform.example.com/health
curl https://us-east-1.ai-platform.example.com/health
curl https://eu-west-1.ai-platform.example.com/health
curl https://ap-southeast-1.ai-platform.example.com/health

# Expected response: {"status":"healthy","region":"us-west-1"}
```

### Check Replication Status

```bash
# PostgreSQL replication
kubectl exec -n ai-platform postgres-0 -- psql -U ai_user -d ai_platform -c \
  "SELECT * FROM replication_status;"

# Qdrant cluster status
kubectl exec -n ai-platform qdrant-0 -- curl http://localhost:6333/cluster
```

## 📈 Access Monitoring

### Grafana Dashboard

```bash
# Port-forward Grafana (any region)
kubectl port-forward -n ai-platform svc/grafana 3000:3000

# Open browser
open http://localhost:3000
# Username: admin, Password: admin (change immediately)

# Navigate to: Dashboards → Cross-Region Latency and Replication Monitoring
```

### Prometheus Metrics

```bash
# Port-forward Prometheus
kubectl port-forward -n ai-platform svc/prometheus 9090:9090

# Open browser
open http://localhost:9090

# Example queries:
# - region_health_status
# - rate(geo_routing_requests_total[5m])
# - pg_replication_lag_seconds
```

## 🔧 Common Operations

### Scale Up Region

```bash
# Scale MAX Serve instances
kubectl scale deployment -n ai-platform max-serve-llama --replicas=5

# Scale Gateway
kubectl scale deployment -n ai-platform gateway --replicas=5
```

### Test Failover

```bash
# Simulate region failure
kubectl scale deployment -n ai-platform gateway --replicas=0

# Watch failover happen in Grafana
# Restore region
kubectl scale deployment -n ai-platform gateway --replicas=3
```

### Check Latency

```bash
# From different regions
for region in us-west-1 us-east-1 eu-west-1 ap-southeast-1; do
  echo "=== Testing from $region ==="
  time curl -s https://$region.ai-platform.example.com/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d '{"messages":[{"role":"user","content":"Hello"}]}' | jq .
done
```

## 🐛 Troubleshooting

### Issue: Pods Not Starting

```bash
# Check pod status
kubectl describe pod -n ai-platform <pod-name>

# Check logs
kubectl logs -n ai-platform <pod-name>

# Common fixes:
# - Verify storage class exists
# - Check node resources
# - Verify image pull secrets
```

### Issue: High Replication Lag

```bash
# Check network connectivity
kubectl run -n ai-platform test-pod --image=busybox --rm -it -- \
  ping postgres.us-west-1.ai-platform.svc.cluster.local

# Check PostgreSQL logs
kubectl logs -n ai-platform postgres-0 | grep replication

# Check Qdrant logs
kubectl logs -n ai-platform qdrant-0 | grep cluster
```

### Issue: DNS Not Resolving

```bash
# Test DNS resolution
nslookup us-west-1.ai-platform.example.com
dig +short us-west-1.ai-platform.example.com

# Check health checks (AWS Route53)
aws route53 get-health-check-status --health-check-id <id>

# Check Kong routing
kubectl logs -n ai-platform -l app=kong | grep geo-routing
```

## 📚 Next Steps

1. **Configure Custom Domains**: Update DNS settings in `configs/geo-routing.yaml`
2. **Setup Alerts**: Configure Alertmanager for Prometheus alerts
3. **Enable Backups**: Setup automated backup schedules
4. **Performance Tuning**: Adjust resource limits based on load
5. **Security Hardening**: Enable TLS, configure secrets, setup RBAC

## 🔗 Related Documentation

- [Full Multi-Region Guide](MULTI_REGION_DEPLOYMENT.md)
- [Replication Setup](../init-scripts/postgres-replication-setup.sql)
- [Geo-Routing Config](../configs/geo-routing.yaml)
- [Monitoring Dashboard](../docs/grafana/cross-region-dashboard.json)

## 🆘 Getting Help

- Check logs: `kubectl logs -n ai-platform <pod-name>`
- View events: `kubectl get events -n ai-platform --sort-by='.lastTimestamp'`
- Describe resources: `kubectl describe <resource> -n ai-platform <name>`
- Contact support: team@ai-platform.example.com

## ⚙️ Configuration Quick Reference

### Key Files

| File | Purpose |
|------|---------|
| `helm/ai-platform/values-multi-region.yaml` | Main Helm configuration |
| `configs/geo-routing.yaml` | Geo-routing rules |
| `scripts/deploy/deploy_region.py` | Single region deployment |
| `scripts/deploy/deploy_all_regions.sh` | All regions deployment |
| `docs/grafana/cross-region-dashboard.json` | Monitoring dashboard |

### Important Values

```yaml
# GPU node types (adjust per cloud provider)
maxServeLlama:
  affinity:
    nodeAffinity:
      values:
        - gpu-accelerated      # Generic
        - p3.2xlarge          # AWS
        - n1-standard-4-nvidia-tesla-t4  # GCP

# Storage classes (adjust per cloud provider)
postgres:
  persistence:
    storageClass: "regional-pd-ssd"  # GCP
    # storageClass: "gp3"             # AWS
    # storageClass: "managed-premium" # Azure

# Replication settings
postgres:
  replication:
    enabled: true
    mode: pglogical
    primaryRegion: us-west-1
```

## 🎯 Success Criteria

✅ All pods running in all regions  
✅ Replication lag < 30 seconds  
✅ Cross-region latency < 250ms (P95)  
✅ Health checks passing  
✅ DNS failover configured  
✅ Monitoring dashboards accessible  
✅ Test requests succeed from all regions  

## 💡 Pro Tips

1. **Start with 2 regions** (primary + 1 replica) before expanding
2. **Monitor replication lag** closely during initial sync
3. **Test failover** in staging before production
4. **Use VPC peering** between regions for lower latency
5. **Enable auto-scaling** to handle traffic spikes
6. **Set up alerts** before going live
7. **Document your DNS setup** for disaster recovery

---

**Deployment Time**: ~30 minutes (including replication sync)  
**Maintenance Window**: Not required for initial deployment  
**Rollback Time**: ~5 minutes per region
