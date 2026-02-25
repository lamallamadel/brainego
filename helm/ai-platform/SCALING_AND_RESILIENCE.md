# Kubernetes Scaling and Resilience Configuration

This document describes the Horizontal Pod Autoscaling (HPA), Pod Disruption Budgets (PDB), and anti-affinity configurations implemented for the AI Platform services.

## Overview

The platform implements three key resilience and scaling mechanisms:

1. **Horizontal Pod Autoscaling (HPA)** - Automatically scales MAX Serve inference services based on CPU utilization and custom metrics
2. **Pod Disruption Budgets (PDB)** - Ensures minimum availability during voluntary disruptions (node maintenance, upgrades)
3. **Anti-Affinity Rules** - Distributes pod replicas across different nodes for better fault tolerance

## Horizontal Pod Autoscaling (HPA)

### MAX Serve Services

All three MAX Serve inference services (Llama, Qwen, DeepSeek) are configured with HPA:

#### Metrics Used

1. **CPU Utilization** (Resource Metric)
   - Target: 70% average CPU utilization
   - Triggers scaling when CPU usage exceeds threshold

2. **Inference Queue Depth** (Custom Metric)
   - Target: 10 requests average per pod
   - Requires Prometheus Adapter for custom metrics
   - Metric name: `inference_queue_depth`

#### Scaling Behavior

**Scale Up:**
- Stabilization Window: 60 seconds
- Policies:
  - 100% increase every 30 seconds, OR
  - Add 2 pods every 30 seconds
  - Selects policy that scales faster (Max)

**Scale Down:**
- Stabilization Window: 300 seconds (5 minutes)
- Policies:
  - 50% decrease every 60 seconds, OR
  - Remove 1 pod every 60 seconds
  - Selects policy that scales slower (Min)
- Prevents thrashing and ensures stability

#### Replica Limits

- **Min Replicas**: 1
- **Max Replicas**: 5
- Configurable per service in `values.yaml`

### Configuration

Enable/disable HPA in `values.yaml`:

```yaml
maxServeLlama:
  autoscaling:
    enabled: true
    minReplicas: 1
    maxReplicas: 5
    targetCPUUtilizationPercentage: 70
    scaleUpStabilizationWindowSeconds: 60
    scaleDownStabilizationWindowSeconds: 300
    customMetrics:
      enabled: true
      inferenceQueueDepthThreshold: 10
```

### Files Created

- `helm/ai-platform/templates/max-serve-hpa.yaml` - HPA definitions for all MAX Serve services

## Pod Disruption Budgets (PDB)

PDBs ensure that a minimum number of pods remain available during voluntary disruptions such as:
- Node drains for maintenance
- Cluster upgrades
- Pod evictions

### Services with PDB

All critical services have PDB configured with `minAvailable: 1`:

1. **Inference Services:**
   - max-serve-llama
   - max-serve-qwen
   - max-serve-deepseek

2. **API Services:**
   - agent-router
   - gateway

3. **Stateful Services:**
   - postgres
   - redis
   - qdrant

### Configuration

Enable/disable PDB in `values.yaml`:

```yaml
maxServeLlama:
  podDisruptionBudget:
    enabled: true
    minAvailable: 1
    # OR use maxUnavailable instead
    # maxUnavailable: 1
```

### How It Works

- **minAvailable: 1** - Ensures at least 1 pod is always running
- Kubernetes will block voluntary disruptions that would violate this constraint
- Does NOT protect against involuntary disruptions (node failures, hardware issues)
- Works with multiple replicas for zero-downtime operations

### Files Created

- `helm/ai-platform/templates/pdb.yaml` - PDB definitions for all critical services

## Anti-Affinity Rules

Anti-affinity rules distribute pod replicas across different nodes to improve fault tolerance and availability.

### Configuration Type

**Preferred Anti-Affinity** (Soft constraint):
- Kubernetes will TRY to schedule pods on different nodes
- Will still schedule on same node if no other nodes available
- Prevents scheduling deadlock in small clusters
- Weight: 100 (high priority)

### Topology Key

- `kubernetes.io/hostname` - Distributes across physical/virtual nodes
- Ensures pods are on different compute nodes

### Services with Anti-Affinity

1. **MAX Serve Inference Services:**
   - max-serve-llama
   - max-serve-qwen
   - max-serve-deepseek

2. **API Services:**
   - agent-router
   - gateway

### Configuration

Configure in `values.yaml`:

```yaml
maxServeLlama:
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
            topologyKey: kubernetes.io/hostname
```

### Why Preferred vs Required?

- **Preferred (Soft)**: Used in this implementation
  - Flexible for small clusters
  - Allows deployment even with limited nodes
  - Still provides distribution when possible

- **Required (Hard)**: Alternative option
  - Strict enforcement
  - Can cause deployment failures in small clusters
  - Better for large production clusters

To switch to required anti-affinity:

```yaml
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

## Custom Metrics for HPA

### Prerequisites

To use custom metrics (inference_queue_depth), you need:

1. **Prometheus Operator** - Already included in the Helm chart
2. **Prometheus Adapter** - Needs to be installed separately

### Install Prometheus Adapter

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

helm install prometheus-adapter prometheus-community/prometheus-adapter \
  --namespace ai-platform \
  --set prometheus.url=http://prometheus:9090 \
  --set prometheus.port=9090
```

### Configure Custom Metrics

Create a ConfigMap for Prometheus Adapter rules:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: prometheus-adapter-config
  namespace: ai-platform
data:
  config.yaml: |
    rules:
      - seriesQuery: 'inference_queue_depth{namespace="ai-platform"}'
        resources:
          overrides:
            namespace: {resource: "namespace"}
            pod: {resource: "pod"}
        name:
          matches: "^(.*)$"
          as: "inference_queue_depth"
        metricsQuery: 'avg_over_time(inference_queue_depth{<<.LabelMatchers>>}[2m])'
```

### Expose Metrics from MAX Serve

The MAX Serve deployments are configured with Prometheus annotations:

```yaml
annotations:
  prometheus.io/scrape: "true"
  prometheus.io/port: "8080"
  prometheus.io/path: "/metrics"
```

Ensure your MAX Serve application exposes the `inference_queue_depth` metric at the `/metrics` endpoint.

### Verify Custom Metrics

```bash
# Check if custom metrics are available
kubectl get --raw "/apis/custom.metrics.k8s.io/v1beta1/namespaces/ai-platform/pods/*/inference_queue_depth" | jq .

# Check HPA status
kubectl get hpa -n ai-platform
kubectl describe hpa max-serve-llama-hpa -n ai-platform
```

## Monitoring and Verification

### Check HPA Status

```bash
# List all HPAs
kubectl get hpa -n ai-platform

# Detailed HPA status
kubectl describe hpa max-serve-llama-hpa -n ai-platform

# Watch HPA in real-time
kubectl get hpa -n ai-platform -w
```

### Check PDB Status

```bash
# List all PDBs
kubectl get pdb -n ai-platform

# Detailed PDB status
kubectl describe pdb max-serve-llama-pdb -n ai-platform

# Check current disruptions allowed
kubectl get pdb -n ai-platform -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.disruptionsAllowed}{"\n"}{end}'
```

### Check Pod Distribution (Anti-Affinity)

```bash
# View pod distribution across nodes
kubectl get pods -n ai-platform -o wide

# Show pods grouped by node
kubectl get pods -n ai-platform -o json | jq -r '.items[] | "\(.spec.nodeName)\t\(.metadata.name)"' | sort

# Count pods per node
kubectl get pods -n ai-platform -o json | jq -r '.items[] | .spec.nodeName' | sort | uniq -c
```

### Check Scaling Events

```bash
# View HPA events
kubectl get events -n ai-platform --field-selector involvedObject.kind=HorizontalPodAutoscaler

# View pod scaling events
kubectl get events -n ai-platform --field-selector reason=ScalingReplicaSet

# Continuous event watch
kubectl get events -n ai-platform -w
```

## Testing

### Test HPA Scaling

#### 1. CPU-Based Scaling

Generate CPU load:

```bash
# Get pod name
POD_NAME=$(kubectl get pods -n ai-platform -l app.kubernetes.io/name=max-serve-llama -o jsonpath='{.items[0].metadata.name}')

# Run stress test (if stress tool is available in container)
kubectl exec -n ai-platform $POD_NAME -- stress --cpu 4 --timeout 300s
```

#### 2. Load Test with API Requests

Use the existing load test script:

```bash
# Run load test to trigger queue depth metric
python load_test.py --requests 1000 --concurrency 50
```

Watch the HPA scale:

```bash
kubectl get hpa max-serve-llama-hpa -n ai-platform -w
```

### Test PDB Protection

#### 1. Try to drain a node

```bash
# Cordon node (prevent new pods)
kubectl cordon <node-name>

# Drain node (evict existing pods)
kubectl drain <node-name> --ignore-daemonsets --delete-emptydir-data

# PDB will prevent drain if it would violate minAvailable
# Watch for PDB-related messages in drain output
```

#### 2. Check PDB constraints

```bash
kubectl describe pdb -n ai-platform
# Look for "Allowed disruptions" field
```

### Test Anti-Affinity

#### 1. Scale up replicas

```bash
# Scale MAX Serve Llama to 3 replicas
kubectl scale deployment max-serve-llama -n ai-platform --replicas=3

# Watch pod scheduling
kubectl get pods -n ai-platform -l app.kubernetes.io/name=max-serve-llama -o wide -w
```

#### 2. Verify distribution

```bash
# Check if pods are on different nodes
kubectl get pods -n ai-platform -l app.kubernetes.io/name=max-serve-llama -o custom-columns=NAME:.metadata.name,NODE:.spec.nodeName
```

## Troubleshooting

### HPA Not Scaling

**Issue**: HPA shows "unknown" for metrics

```bash
kubectl describe hpa max-serve-llama-hpa -n ai-platform
```

**Solutions**:
1. Check metrics-server is running: `kubectl get deployment metrics-server -n kube-system`
2. Verify pod resource requests are set (required for CPU-based scaling)
3. For custom metrics, check Prometheus Adapter is running
4. Verify metrics are being scraped: `kubectl get --raw /apis/metrics.k8s.io/v1beta1/nodes`

**Issue**: HPA not using custom metrics

**Solutions**:
1. Verify Prometheus Adapter is installed
2. Check custom metrics are available: `kubectl get --raw /apis/custom.metrics.k8s.io/v1beta1`
3. Verify metric name matches in HPA and Prometheus Adapter config
4. Check Prometheus is scraping metrics from pods

### PDB Blocking Operations

**Issue**: Node drain is blocked by PDB

```bash
kubectl get pdb -n ai-platform
```

**Solutions**:
1. Scale up replicas before draining: `kubectl scale deployment <name> --replicas=<N+1>`
2. Temporarily disable PDB (not recommended): `kubectl delete pdb <pdb-name> -n ai-platform`
3. Adjust PDB settings to use `maxUnavailable` instead of `minAvailable`

### Anti-Affinity Not Working

**Issue**: Multiple pods scheduled on same node

**Solutions**:
1. Check if cluster has enough nodes
2. Verify node resources are sufficient
3. Check node labels match topology key
4. Consider switching from preferred to required anti-affinity (if cluster size allows)
5. Check for node taints that might limit scheduling

## Production Recommendations

### For Production Deployments

1. **HPA Configuration**:
   - Set `minReplicas: 2` or higher for HA
   - Adjust `maxReplicas` based on cluster capacity and expected load
   - Fine-tune stabilization windows based on traffic patterns
   - Monitor custom metrics accuracy

2. **PDB Configuration**:
   - Use `minAvailable: 2` for critical services with 3+ replicas
   - Consider `maxUnavailable: 1` for large replica sets
   - Test PDB during maintenance windows

3. **Anti-Affinity Configuration**:
   - Use required anti-affinity for large production clusters (10+ nodes)
   - Keep preferred anti-affinity for dev/staging environments
   - Consider zone-level anti-affinity for multi-AZ clusters:
     ```yaml
     topologyKey: topology.kubernetes.io/zone
     ```

4. **Resource Management**:
   - Set accurate resource requests/limits
   - Use VPA (Vertical Pod Autoscaler) alongside HPA for optimal sizing
   - Monitor actual resource usage and adjust

5. **Monitoring**:
   - Set up alerts for HPA failures
   - Monitor PDB disruptions allowed
   - Track pod distribution across nodes
   - Alert on custom metrics collection failures

### Multi-AZ Configuration

For multi-availability-zone clusters:

```yaml
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

This configuration:
- Strongly prefers different zones (weight: 100)
- Moderately prefers different nodes within same zone (weight: 50)

## Files Modified/Created

### New Files
- `helm/ai-platform/templates/max-serve-hpa.yaml` - HPA definitions
- `helm/ai-platform/templates/pdb.yaml` - Pod Disruption Budget definitions
- `helm/ai-platform/templates/servicemonitor.yaml` - Prometheus ServiceMonitor for custom metrics
- `helm/ai-platform/SCALING_AND_RESILIENCE.md` - This documentation

### Modified Files
- `helm/ai-platform/values.yaml` - Added autoscaling, PDB, and affinity configurations
- `helm/ai-platform/templates/max-serve-llama-deployment.yaml` - Added affinity and Prometheus annotations
- `helm/ai-platform/templates/max-serve-qwen-deployment.yaml` - Added affinity and Prometheus annotations
- `helm/ai-platform/templates/max-serve-deepseek-deployment.yaml` - Added affinity and Prometheus annotations
- `helm/ai-platform/templates/agent-router-deployment.yaml` - Added affinity
- `helm/ai-platform/templates/gateway-deployment.yaml` - Added affinity

## References

- [Kubernetes HPA Documentation](https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/)
- [Pod Disruption Budgets](https://kubernetes.io/docs/concepts/workloads/pods/disruptions/)
- [Assigning Pods to Nodes - Affinity and Anti-Affinity](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/)
- [Prometheus Adapter](https://github.com/kubernetes-sigs/prometheus-adapter)
- [Custom Metrics for HPA](https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale-walkthrough/#autoscaling-on-multiple-metrics-and-custom-metrics)
