# Scaling and Resilience - Quick Start Guide

Quick reference for deploying and managing the HPA, PDB, and anti-affinity configurations.

## Prerequisites

1. **Kubernetes Cluster**: v1.23+
2. **Helm**: v3.8+
3. **Metrics Server**: Required for CPU-based HPA
4. **Prometheus Adapter**: Required for custom metrics HPA (optional)

## Install Metrics Server (if not present)

```bash
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
```

## Deploy the AI Platform with Scaling Features

### 1. Basic Deployment (CPU-based HPA only)

```bash
# Deploy with default settings
helm install ai-platform ./helm/ai-platform \
  --namespace ai-platform \
  --create-namespace

# Verify deployment
kubectl get pods -n ai-platform
kubectl get hpa -n ai-platform
kubectl get pdb -n ai-platform
```

### 2. Deployment with Custom Metrics

First, install Prometheus Adapter:

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

helm install prometheus-adapter prometheus-community/prometheus-adapter \
  --namespace ai-platform \
  --set prometheus.url=http://prometheus:9090 \
  --set prometheus.port=9090
```

Then deploy the platform:

```bash
helm install ai-platform ./helm/ai-platform \
  --namespace ai-platform \
  --create-namespace
```

### 3. Custom Configuration

Create a `custom-values.yaml` file:

```yaml
# Adjust MAX Serve Llama scaling
maxServeLlama:
  replicaCount: 2
  autoscaling:
    enabled: true
    minReplicas: 2
    maxReplicas: 10
    targetCPUUtilizationPercentage: 60
    customMetrics:
      enabled: true
      inferenceQueueDepthThreshold: 15
  podDisruptionBudget:
    enabled: true
    minAvailable: 2

# Adjust Agent Router
agentRouter:
  replicaCount: 3
  podDisruptionBudget:
    enabled: true
    minAvailable: 2
```

Deploy with custom values:

```bash
helm install ai-platform ./helm/ai-platform \
  --namespace ai-platform \
  --create-namespace \
  --values custom-values.yaml
```

## Quick Verification Commands

### Check Everything

```bash
# All resources in namespace
kubectl get all -n ai-platform

# HPAs status
kubectl get hpa -n ai-platform

# PDBs status
kubectl get pdb -n ai-platform

# Pod distribution
kubectl get pods -n ai-platform -o wide
```

### Monitor Scaling in Real-Time

```bash
# Watch HPA
kubectl get hpa -n ai-platform -w

# Watch pods
kubectl get pods -n ai-platform -w

# Watch events
kubectl get events -n ai-platform -w
```

## Quick Testing

### Test HPA Scaling

```bash
# Option 1: Use load test script
python load_test.py --requests 1000 --concurrency 50

# Option 2: Manual scaling (temporary)
kubectl scale deployment max-serve-llama -n ai-platform --replicas=3

# Watch scaling
kubectl get hpa max-serve-llama-hpa -n ai-platform -w
```

### Test Pod Distribution

```bash
# Scale up to see distribution
kubectl scale deployment max-serve-llama -n ai-platform --replicas=3

# Check node distribution
kubectl get pods -n ai-platform -l app.kubernetes.io/name=max-serve-llama \
  -o custom-columns=NAME:.metadata.name,NODE:.spec.nodeName
```

### Test PDB Protection

```bash
# Get node name
NODE_NAME=$(kubectl get nodes -o jsonpath='{.items[0].metadata.name}')

# Try to drain (will respect PDB)
kubectl drain $NODE_NAME --ignore-daemonsets --dry-run=client

# Check PDB status
kubectl get pdb -n ai-platform
```

## Common Operations

### Update Configuration

```bash
# Edit values
vim custom-values.yaml

# Upgrade deployment
helm upgrade ai-platform ./helm/ai-platform \
  --namespace ai-platform \
  --values custom-values.yaml

# Rollback if needed
helm rollback ai-platform -n ai-platform
```

### Temporarily Disable Features

Disable HPA:
```bash
kubectl patch hpa max-serve-llama-hpa -n ai-platform -p '{"spec":{"maxReplicas":1}}'
```

Disable PDB (not recommended):
```bash
kubectl delete pdb max-serve-llama-pdb -n ai-platform
```

### Re-enable Features

```bash
# Re-apply configuration
helm upgrade ai-platform ./helm/ai-platform \
  --namespace ai-platform \
  --values custom-values.yaml
```

## Monitoring

### HPA Metrics

```bash
# Current metrics
kubectl get hpa -n ai-platform

# Detailed view
kubectl describe hpa max-serve-llama-hpa -n ai-platform

# Custom metrics (if enabled)
kubectl get --raw "/apis/custom.metrics.k8s.io/v1beta1/namespaces/ai-platform/pods/*/inference_queue_depth" | jq .
```

### PDB Status

```bash
# All PDBs
kubectl get pdb -n ai-platform

# Allowed disruptions
kubectl get pdb -n ai-platform -o custom-columns=NAME:.metadata.name,ALLOWED:.status.disruptionsAllowed

# Details
kubectl describe pdb max-serve-llama-pdb -n ai-platform
```

### Pod Distribution

```bash
# Pods per node
kubectl get pods -n ai-platform -o json | \
  jq -r '.items[] | "\(.spec.nodeName)\t\(.metadata.name)"' | \
  sort | column -t

# Count per node
kubectl get pods -n ai-platform -o json | \
  jq -r '.items[] | .spec.nodeName' | \
  sort | uniq -c
```

## Troubleshooting Quick Fixes

### HPA shows "unknown" metrics

```bash
# Check metrics-server
kubectl get deployment metrics-server -n kube-system

# Check pod resources
kubectl describe deployment max-serve-llama -n ai-platform | grep -A 5 "Requests:"
```

### Pods not distributing across nodes

```bash
# Check node count
kubectl get nodes

# Check node resources
kubectl top nodes

# Check affinity rules
kubectl get deployment max-serve-llama -n ai-platform -o yaml | grep -A 20 affinity
```

### PDB blocking operations

```bash
# Scale up first
kubectl scale deployment max-serve-llama -n ai-platform --replicas=3

# Then try operation again
```

## Configuration Examples

### Production HA Setup

```yaml
maxServeLlama:
  replicaCount: 3
  autoscaling:
    enabled: true
    minReplicas: 3
    maxReplicas: 10
    targetCPUUtilizationPercentage: 70
  podDisruptionBudget:
    enabled: true
    minAvailable: 2
  affinity:
    podAntiAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
        - labelSelector:
            matchExpressions:
              - key: app.kubernetes.io/name
                operator: In
                values:
                  - max-serve-llama
          topologyKey: kubernetes.io/hostname
```

### Dev/Test Setup

```yaml
maxServeLlama:
  replicaCount: 1
  autoscaling:
    enabled: true
    minReplicas: 1
    maxReplicas: 3
    targetCPUUtilizationPercentage: 80
  podDisruptionBudget:
    enabled: false
```

### Multi-AZ Setup

```yaml
maxServeLlama:
  replicaCount: 3
  autoscaling:
    enabled: true
    minReplicas: 3
    maxReplicas: 15
  podDisruptionBudget:
    enabled: true
    minAvailable: 2
  affinity:
    podAntiAffinity:
      preferredDuringSchedulingIgnoredDuringExecution:
        - weight: 100
          podAffinityTerm:
            labelSelector:
              matchExpressions:
                - key: app.kubernetes.io/name
                  operator: In
                  values:
                    - max-serve-llama
            topologyKey: topology.kubernetes.io/zone
        - weight: 50
          podAffinityTerm:
            labelSelector:
              matchExpressions:
                - key: app.kubernetes.io/name
                  operator: In
                  values:
                    - max-serve-llama
            topologyKey: kubernetes.io/hostname
```

## Cleanup

```bash
# Remove deployment
helm uninstall ai-platform -n ai-platform

# Remove namespace
kubectl delete namespace ai-platform

# Remove Prometheus Adapter (if installed)
helm uninstall prometheus-adapter -n ai-platform
```

## Next Steps

For detailed information, see:
- [SCALING_AND_RESILIENCE.md](./SCALING_AND_RESILIENCE.md) - Complete documentation
- [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md) - Full deployment guide
- [README.md](./README.md) - General information

## Support

For issues or questions:
1. Check `kubectl get events -n ai-platform`
2. Check `kubectl logs -n ai-platform <pod-name>`
3. Review the detailed documentation in `SCALING_AND_RESILIENCE.md`
