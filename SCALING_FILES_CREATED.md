# Kubernetes Scaling and Resilience Implementation - Files Created

This document lists all files created or modified to implement HPA, PDB, and anti-affinity rules for the AI Platform.

## Summary

Implemented comprehensive Kubernetes scaling and resilience features:
- **Horizontal Pod Autoscaling (HPA)** for MAX Serve services based on CPU (>70%) and custom `inference_queue_depth` metric (>10)
- **Pod Disruption Budgets (PDB)** with minAvailable=1 for all critical services
- **Anti-Affinity Rules** to distribute replicas across nodes

## New Files Created

### 1. Helm Templates

#### `helm/ai-platform/templates/max-serve-hpa.yaml`
HorizontalPodAutoscaler definitions for all three MAX Serve inference services:
- max-serve-llama-hpa
- max-serve-qwen-hpa
- max-serve-deepseek-hpa

**Features:**
- CPU utilization target: 70%
- Custom metric: inference_queue_depth (target: 10)
- Scale up: 60s stabilization, 100% increase or +2 pods per 30s
- Scale down: 300s stabilization, 50% decrease or -1 pod per 60s
- Min replicas: 1, Max replicas: 5

#### `helm/ai-platform/templates/pdb.yaml`
PodDisruptionBudget definitions for critical services:
- max-serve-llama-pdb
- max-serve-qwen-pdb
- max-serve-deepseek-pdb
- agent-router-pdb
- gateway-pdb
- postgres-pdb
- redis-pdb
- qdrant-pdb

**Features:**
- minAvailable: 1 for all services
- Ensures at least 1 pod remains during voluntary disruptions
- Protects against cluster maintenance, node drains, and upgrades

#### `helm/ai-platform/templates/servicemonitor.yaml`
ServiceMonitor resources for Prometheus metric collection:
- Enables Prometheus to scrape custom metrics from MAX Serve services
- Scrape interval: 30s
- Path: /metrics
- Required for custom metrics HPA

### 2. Documentation Files

#### `helm/ai-platform/SCALING_AND_RESILIENCE.md`
Comprehensive documentation covering:
- HPA configuration and behavior
- PDB setup and protection mechanisms
- Anti-affinity rules and topology
- Custom metrics setup with Prometheus Adapter
- Monitoring and verification commands
- Testing procedures
- Troubleshooting guide
- Production recommendations
- Multi-AZ configurations

#### `helm/ai-platform/SCALING_QUICKSTART.md`
Quick start guide with:
- Prerequisites
- Deployment commands
- Quick verification steps
- Common operations
- Configuration examples
- Troubleshooting quick fixes

#### `SCALING_FILES_CREATED.md`
This file - summary of all changes

## Modified Files

### 1. Helm Values Configuration

#### `helm/ai-platform/values.yaml`

**Changes for MAX Serve Llama (lines 36-60):**
```yaml
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
podDisruptionBudget:
  enabled: true
  minAvailable: 1
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

**Changes for MAX Serve Qwen (lines 136-160):**
- Same autoscaling configuration
- Same PDB configuration
- Anti-affinity targeting max-serve-qwen

**Changes for MAX Serve DeepSeek (lines 236-260):**
- Same autoscaling configuration
- Same PDB configuration
- Anti-affinity targeting max-serve-deepseek

**Changes for Agent Router (lines 335-349):**
```yaml
podDisruptionBudget:
  enabled: true
  minAvailable: 1
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
                  - agent-router
          topologyKey: kubernetes.io/hostname
```

**Changes for Gateway (lines 421-435):**
- Same PDB configuration
- Anti-affinity targeting gateway

**Changes for Postgres (lines 787-789):**
```yaml
podDisruptionBudget:
  enabled: true
  minAvailable: 1
```

**Changes for Redis (lines 739-741):**
```yaml
podDisruptionBudget:
  enabled: true
  minAvailable: 1
```

**Changes for Qdrant (lines 698-700):**
```yaml
podDisruptionBudget:
  enabled: true
  minAvailable: 1
```

### 2. Helm Deployment Templates

#### `helm/ai-platform/templates/max-serve-llama-deployment.yaml`

**Changes (lines 40-52):**
- Added Prometheus scraping annotations for custom metrics
- Added affinity configuration support

```yaml
annotations:
  prometheus.io/scrape: "true"
  prometheus.io/port: "{{ .Values.maxServeLlama.service.targetPort }}"
  prometheus.io/path: "/metrics"
spec:
  # ... existing imagePullSecrets ...
  {{- if .Values.maxServeLlama.affinity }}
  affinity:
    {{- toYaml .Values.maxServeLlama.affinity | nindent 8 }}
  {{- end }}
```

#### `helm/ai-platform/templates/max-serve-qwen-deployment.yaml`

**Changes (lines 40-52):**
- Same changes as max-serve-llama
- Prometheus annotations
- Affinity support

#### `helm/ai-platform/templates/max-serve-deepseek-deployment.yaml`

**Changes (lines 40-52):**
- Same changes as max-serve-llama
- Prometheus annotations
- Affinity support

#### `helm/ai-platform/templates/agent-router-deployment.yaml`

**Changes (lines 49-52):**
- Added affinity configuration support

```yaml
{{- if .Values.agentRouter.affinity }}
affinity:
  {{- toYaml .Values.agentRouter.affinity | nindent 8 }}
{{- end }}
```

#### `helm/ai-platform/templates/gateway-deployment.yaml`

**Changes (lines 45-48):**
- Added affinity configuration support

```yaml
{{- if .Values.gateway.affinity }}
affinity:
  {{- toYaml .Values.gateway.affinity | nindent 8 }}
{{- end }}
```

## Configuration Details

### HPA Configuration

All MAX Serve services (Llama, Qwen, DeepSeek) have identical HPA configuration:

| Parameter | Value | Description |
|-----------|-------|-------------|
| enabled | true | Enable HPA |
| minReplicas | 1 | Minimum pod count |
| maxReplicas | 5 | Maximum pod count |
| targetCPUUtilizationPercentage | 70 | CPU threshold for scaling |
| scaleUpStabilizationWindowSeconds | 60 | Wait time before scaling up |
| scaleDownStabilizationWindowSeconds | 300 | Wait time before scaling down |
| customMetrics.enabled | true | Enable custom metrics |
| customMetrics.inferenceQueueDepthThreshold | 10 | Queue depth threshold |

### PDB Configuration

All critical services have PDB with:

| Parameter | Value | Description |
|-----------|-------|-------------|
| enabled | true | Enable PDB |
| minAvailable | 1 | Minimum pods that must be available |

**Services with PDB:**
- max-serve-llama
- max-serve-qwen
- max-serve-deepseek
- agent-router
- gateway
- postgres
- redis
- qdrant

### Anti-Affinity Configuration

Services with pod anti-affinity:

| Service | Type | Weight | Topology Key |
|---------|------|--------|--------------|
| max-serve-llama | Preferred | 100 | kubernetes.io/hostname |
| max-serve-qwen | Preferred | 100 | kubernetes.io/hostname |
| max-serve-deepseek | Preferred | 100 | kubernetes.io/hostname |
| agent-router | Preferred | 100 | kubernetes.io/hostname |
| gateway | Preferred | 100 | kubernetes.io/hostname |

**Type: Preferred** - Soft constraint, allows scheduling on same node if necessary

## Key Features Implemented

### 1. Horizontal Pod Autoscaling (HPA)

✅ **CPU-Based Scaling**
- Monitors CPU utilization across pod replicas
- Target: 70% average utilization
- Automatically scales when threshold exceeded

✅ **Custom Metrics Scaling**
- Monitors inference queue depth
- Target: 10 requests per pod average
- Requires Prometheus Adapter

✅ **Intelligent Scaling Behavior**
- Fast scale-up: 60s stabilization, aggressive policies
- Slow scale-down: 300s stabilization, conservative policies
- Prevents thrashing and ensures stability

✅ **Per-Service Configuration**
- Independent scaling for each MAX Serve model
- Configurable thresholds and limits
- Easy to enable/disable per service

### 2. Pod Disruption Budgets (PDB)

✅ **High Availability Protection**
- Ensures minimum availability during maintenance
- Protects against voluntary disruptions
- Supports cluster upgrades without downtime

✅ **Critical Services Coverage**
- All inference services protected
- All API gateways protected
- All stateful services protected

✅ **Flexible Configuration**
- Supports minAvailable or maxUnavailable
- Easy to adjust per service needs
- Can be enabled/disabled per service

### 3. Anti-Affinity Rules

✅ **Node Distribution**
- Spreads replicas across different nodes
- Improves fault tolerance
- Better resource utilization

✅ **Preferred (Soft) Constraints**
- Works with small clusters
- No scheduling deadlock risk
- Still provides distribution when possible

✅ **Service Isolation**
- Each service manages its own affinity
- No interference between different services
- Easy to customize per service

## Deployment Instructions

### Prerequisites

```bash
# Install metrics-server (if not present)
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml

# (Optional) Install Prometheus Adapter for custom metrics
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm install prometheus-adapter prometheus-community/prometheus-adapter \
  --namespace ai-platform \
  --set prometheus.url=http://prometheus:9090
```

### Deploy

```bash
# Deploy with default configuration
helm install ai-platform ./helm/ai-platform \
  --namespace ai-platform \
  --create-namespace

# Verify deployment
kubectl get hpa -n ai-platform
kubectl get pdb -n ai-platform
kubectl get pods -n ai-platform -o wide
```

### Verify

```bash
# Check HPA status
kubectl get hpa -n ai-platform
kubectl describe hpa max-serve-llama-hpa -n ai-platform

# Check PDB status
kubectl get pdb -n ai-platform
kubectl describe pdb max-serve-llama-pdb -n ai-platform

# Check pod distribution
kubectl get pods -n ai-platform -o wide
```

## Testing Recommendations

### 1. Test HPA Scaling

```bash
# Generate load
python load_test.py --requests 1000 --concurrency 50

# Watch scaling
kubectl get hpa max-serve-llama-hpa -n ai-platform -w
```

### 2. Test PDB Protection

```bash
# Try to drain a node
kubectl drain <node-name> --ignore-daemonsets --dry-run=client

# Verify PDB is respected
kubectl get pdb -n ai-platform
```

### 3. Test Anti-Affinity

```bash
# Scale up to multiple replicas
kubectl scale deployment max-serve-llama -n ai-platform --replicas=3

# Check distribution across nodes
kubectl get pods -n ai-platform -l app.kubernetes.io/name=max-serve-llama -o wide
```

## Monitoring

### Key Metrics to Monitor

1. **HPA Metrics**
   - Current/Target CPU utilization
   - Current/Target custom metrics
   - Current replica count
   - Scaling events

2. **PDB Status**
   - Disruptions allowed
   - Current available replicas
   - Expected available replicas

3. **Pod Distribution**
   - Pods per node
   - Node resource utilization
   - Scheduling failures

### Monitoring Commands

```bash
# HPA status
kubectl get hpa -n ai-platform -w

# PDB status
kubectl get pdb -n ai-platform -o custom-columns=NAME:.metadata.name,ALLOWED:.status.disruptionsAllowed

# Pod distribution
kubectl get pods -n ai-platform -o wide

# Events
kubectl get events -n ai-platform -w
```

## Production Considerations

### For Production Deployments

1. **Increase minReplicas**: Set to 2+ for HA
2. **Adjust maxReplicas**: Based on cluster capacity and expected load
3. **Fine-tune thresholds**: Monitor and adjust based on actual usage
4. **Use required anti-affinity**: For large clusters with 10+ nodes
5. **Implement multi-AZ**: Use zone-level topology for better distribution
6. **Set up alerts**: Monitor HPA, PDB, and scaling events
7. **Test during maintenance**: Verify PDB protection works as expected

### Example Production Configuration

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
```

## References

- [Kubernetes HPA Documentation](https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/)
- [Pod Disruption Budgets](https://kubernetes.io/docs/concepts/workloads/pods/disruptions/)
- [Affinity and Anti-Affinity](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/)
- [Prometheus Adapter](https://github.com/kubernetes-sigs/prometheus-adapter)

## Support

For detailed documentation, see:
- `helm/ai-platform/SCALING_AND_RESILIENCE.md` - Complete technical documentation
- `helm/ai-platform/SCALING_QUICKSTART.md` - Quick start guide
