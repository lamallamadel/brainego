# AI Platform Helm Chart - Deployment Guide

## Quick Reference

### Chart Structure

```
helm/ai-platform/
├── Chart.yaml                    # Chart metadata
├── values.yaml                   # Default configuration values
├── README.md                     # Comprehensive documentation
├── DEPLOYMENT_GUIDE.md          # This file
├── .helmignore                  # Files to ignore in package
└── templates/
    ├── _helpers.tpl             # Template helpers
    ├── NOTES.txt               # Post-install notes
    ├── namespace.yaml          # Namespace definition
    ├── secrets.yaml            # Secret resources
    ├── configmaps.yaml         # ConfigMap resources
    │
    ├── StatefulSets (Data Layer)
    ├── qdrant-statefulset.yaml      # Vector database
    ├── redis-statefulset.yaml       # Cache
    ├── postgres-statefulset.yaml    # Relational DB
    ├── neo4j-statefulset.yaml       # Graph database
    ├── minio-statefulset.yaml       # Object storage
    │
    ├── Deployments (Inference)
    ├── max-serve-llama-deployment.yaml     # Llama 3.3 8B
    ├── max-serve-qwen-deployment.yaml      # Qwen 2.5 Coder
    ├── max-serve-deepseek-deployment.yaml  # DeepSeek R1
    │
    ├── Deployments (Application)
    ├── agent-router-deployment.yaml   # Main API server
    ├── gateway-deployment.yaml        # Gateway service
    ├── mcpjungle-deployment.yaml      # MCP Gateway
    ├── learning-engine-deployment.yaml # Training service
    ├── mem0-deployment.yaml           # Memory service
    │
    └── Deployments (Observability)
        ├── prometheus-deployment.yaml  # Metrics
        ├── grafana-deployment.yaml     # Dashboards
        └── jaeger-deployment.yaml      # Tracing
```

## Pre-Installation Checklist

### Infrastructure Requirements

- [ ] Kubernetes cluster 1.19+ running
- [ ] kubectl configured and connected
- [ ] Helm 3.0+ installed
- [ ] NVIDIA GPU Operator installed (for GPU workloads)
- [ ] Storage provisioner configured
- [ ] Minimum 128GB cluster memory available
- [ ] Minimum 4 GPUs available (or adjust replica counts)

### Storage Requirements

| Component | Storage Size | Type | Required |
|-----------|--------------|------|----------|
| Qdrant | 100Gi | RWO | Yes |
| Redis | 10Gi | RWO | Yes |
| PostgreSQL | 50Gi | RWO | Yes |
| Neo4j | 50Gi + 5Gi + 10Gi + 1Gi | RWO | Yes |
| MinIO | 100Gi | RWO | Yes |
| MAX Serve (per model) | 50Gi + 1Gi + 10Gi | RWO | Yes |
| Learning Engine | 50Gi + 20Gi + 10Gi | RWO | Optional |
| Prometheus | 50Gi | RWO | Optional |
| Grafana | 10Gi | RWO | Optional |
| Jaeger | 10Gi | RWO | Optional |

**Total Minimum Storage**: ~650Gi

### GPU Requirements

| Component | GPUs | Required |
|-----------|------|----------|
| MAX Serve Llama | 1 | Yes |
| MAX Serve Qwen | 1 | Yes |
| MAX Serve DeepSeek | 1 | Yes |
| Learning Engine | 1 | Optional |

**Total GPUs**: 3-4

## Installation Steps

### Step 1: Prepare Configuration

```bash
# Create namespace
kubectl create namespace ai-platform

# Create custom values file
cat > my-values.yaml <<EOF
# Example: Minimal deployment without optional services
mcpjungle:
  enabled: false

learningEngine:
  enabled: false

jaeger:
  enabled: false

# Use specific storage class
qdrant:
  persistence:
    storageClass: "fast-ssd"

postgres:
  persistence:
    storageClass: "standard"

# Update secrets (base64 encoded)
secrets:
  postgres:
    password: $(echo -n "your-secure-password" | base64)
  neo4j:
    password: $(echo -n "your-secure-password" | base64)
  minio:
    accessKey: $(echo -n "your-access-key" | base64)
    secretKey: $(echo -n "your-secret-key" | base64)
  grafana:
    password: $(echo -n "your-grafana-password" | base64)
EOF
```

### Step 2: Validate Chart

```bash
# Lint the chart
helm lint ./helm/ai-platform

# Dry-run installation
helm install my-ai-platform ./helm/ai-platform \
  --namespace ai-platform \
  --dry-run \
  --debug \
  --values my-values.yaml
```

### Step 3: Install Chart

```bash
# Install with custom values
helm install my-ai-platform ./helm/ai-platform \
  --namespace ai-platform \
  --values my-values.yaml \
  --timeout 15m \
  --wait

# Or install with inline values
helm install my-ai-platform ./helm/ai-platform \
  --namespace ai-platform \
  --set agentRouter.replicaCount=3 \
  --set gateway.service.type=LoadBalancer \
  --timeout 15m \
  --wait
```

### Step 4: Verify Installation

```bash
# Check all pods are running
kubectl get pods -n ai-platform

# Check services
kubectl get svc -n ai-platform

# Check persistent volume claims
kubectl get pvc -n ai-platform

# View installation notes
helm status my-ai-platform -n ai-platform
```

## Post-Installation Configuration

### 1. Load Models into MAX Serve

```bash
# Copy model files to persistent volumes
# Option A: Direct copy to PVC
kubectl run -it --rm model-loader \
  --image=busybox \
  --namespace=ai-platform \
  --overrides='
{
  "apiVersion": "v1",
  "spec": {
    "containers": [{
      "name": "model-loader",
      "image": "busybox",
      "stdin": true,
      "tty": true,
      "volumeMounts": [{
        "name": "models",
        "mountPath": "/models"
      }]
    }],
    "volumes": [{
      "name": "models",
      "persistentVolumeClaim": {
        "claimName": "max-serve-llama-models"
      }
    }]
  }
}' -- sh

# Inside the pod, download or copy models
# wget -O /models/llama-3.3-8b-instruct-q4_k_m.gguf <URL>
```

### 2. Configure Prometheus Targets

```bash
# Edit Prometheus ConfigMap if needed
kubectl edit configmap prometheus-config -n ai-platform

# Reload Prometheus
kubectl rollout restart deployment/prometheus -n ai-platform
```

### 3. Import Grafana Dashboards

```bash
# Access Grafana
kubectl port-forward -n ai-platform svc/grafana 3000:3000

# Login with admin credentials
# Import dashboards from configs/grafana/dashboards/
```

### 4. Test API Endpoints

```bash
# Port forward Agent Router
kubectl port-forward -n ai-platform svc/agent-router 8000:8000

# Test health endpoint
curl http://localhost:8000/health

# Test chat completion
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama-3.3-8b-instruct",
    "messages": [{"role": "user", "content": "Hello!"}],
    "max_tokens": 100
  }'
```

## Upgrading

### Upgrade Chart

```bash
# Update values
helm upgrade my-ai-platform ./helm/ai-platform \
  --namespace ai-platform \
  --values my-values.yaml \
  --timeout 15m \
  --wait

# Roll back if needed
helm rollback my-ai-platform -n ai-platform
```

### Scaling Services

```bash
# Scale Agent Router
helm upgrade my-ai-platform ./helm/ai-platform \
  --namespace ai-platform \
  --reuse-values \
  --set agentRouter.replicaCount=5

# Scale Gateway
helm upgrade my-ai-platform ./helm/ai-platform \
  --namespace ai-platform \
  --reuse-values \
  --set gateway.replicaCount=3
```

## Production Checklist

### Security

- [ ] Update all default passwords in secrets
- [ ] Use strong passwords (generated, not default)
- [ ] Enable TLS for all external services
- [ ] Configure RBAC and service accounts
- [ ] Set up network policies
- [ ] Enable pod security policies/standards
- [ ] Configure secrets management (e.g., Vault)
- [ ] Set up API authentication and authorization

### High Availability

- [ ] Deploy Agent Router with at least 2 replicas
- [ ] Deploy Gateway with at least 2 replicas
- [ ] Configure pod anti-affinity rules
- [ ] Set up horizontal pod autoscaling
- [ ] Configure resource limits and requests
- [ ] Set up liveness and readiness probes
- [ ] Configure PodDisruptionBudgets

### Monitoring & Observability

- [ ] Configure Prometheus retention
- [ ] Set up Grafana alerting
- [ ] Configure log aggregation (e.g., ELK, Loki)
- [ ] Enable Jaeger distributed tracing
- [ ] Set up uptime monitoring
- [ ] Configure metric dashboards
- [ ] Set up alert notifications (Slack, PagerDuty)

### Backup & Recovery

- [ ] Configure database backups (PostgreSQL, Neo4j)
- [ ] Set up vector store backups (Qdrant)
- [ ] Configure object storage backups (MinIO)
- [ ] Test restore procedures
- [ ] Document recovery procedures
- [ ] Set up automated backup schedules

### Performance

- [ ] Use SSD storage classes for databases
- [ ] Configure appropriate resource limits
- [ ] Enable GPU sharing if needed
- [ ] Set up caching strategies
- [ ] Configure connection pooling
- [ ] Monitor and optimize query performance
- [ ] Set up CDN for static assets (if applicable)

## Troubleshooting

### Common Issues

#### Pods in Pending State

```bash
# Check events
kubectl describe pod <pod-name> -n ai-platform

# Common causes:
# - Insufficient GPU resources
# - PVC binding issues
# - Resource quota exceeded
# - Node selector not matching

# Check GPU allocation
kubectl describe nodes | grep -A 10 "nvidia.com/gpu"

# Check PVC status
kubectl get pvc -n ai-platform
```

#### Service Not Accessible

```bash
# Check service
kubectl get svc -n ai-platform

# Check endpoints
kubectl get endpoints <service-name> -n ai-platform

# Test from within cluster
kubectl run -it --rm debug --image=curlimages/curl --restart=Never -n ai-platform -- \
  curl http://agent-router:8000/health
```

#### MAX Serve Model Loading Failures

```bash
# Check logs
kubectl logs deployment/max-serve-llama -n ai-platform

# Verify model file exists
kubectl exec -it deployment/max-serve-llama -n ai-platform -- ls -lh /models/

# Check GPU availability
kubectl exec -it deployment/max-serve-llama -n ai-platform -- nvidia-smi
```

#### Database Connection Issues

```bash
# Check PostgreSQL logs
kubectl logs statefulset/postgres -n ai-platform

# Test connection
kubectl run -it --rm psql-client --image=postgres:15-alpine --restart=Never -n ai-platform -- \
  psql -h postgres -U ai_user -d ai_platform -c "SELECT 1"

# Check secrets
kubectl get secret postgres-credentials -n ai-platform -o yaml
```

## Uninstallation

### Complete Removal

```bash
# Uninstall Helm release
helm uninstall my-ai-platform --namespace ai-platform

# Delete PVCs (optional - will delete data!)
kubectl delete pvc --all -n ai-platform

# Delete namespace
kubectl delete namespace ai-platform
```

### Retain Data

```bash
# Uninstall but keep PVCs
helm uninstall my-ai-platform --namespace ai-platform

# PVCs remain for re-installation
kubectl get pvc -n ai-platform
```

## Support & Resources

- **Documentation**: See README.md in this directory
- **Architecture**: See AGENTS.md in repository root
- **Issues**: GitHub Issues
- **Helm Chart Repository**: https://charts.example.com/ai-platform

## Version History

- **1.0.0** (Initial Release)
  - Complete AI platform deployment
  - MAX Serve with 3 models
  - Full observability stack
  - Comprehensive data layer
  - Production-ready configurations
