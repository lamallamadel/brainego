# AI Platform Helm Chart - Quick Reference Index

## Documentation Files

| File | Purpose | Size |
|------|---------|------|
| [README.md](README.md) | Complete chart documentation | 12.8 KB |
| [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) | Step-by-step deployment instructions | 11.0 KB |
| [INDEX.md](INDEX.md) | This file - Quick reference | - |

## Chart Configuration

| File | Purpose | Size |
|------|---------|------|
| [Chart.yaml](Chart.yaml) | Chart metadata (v1.0.0) | 457 bytes |
| [values.yaml](values.yaml) | Default configuration values | 20.6 KB |
| [.helmignore](.helmignore) | Package exclusion patterns | 452 bytes |

## Kubernetes Templates

### Infrastructure (6 files)
- [templates/namespace.yaml](templates/namespace.yaml) - Namespace definition
- [templates/secrets.yaml](templates/secrets.yaml) - 4 secret resources
- [templates/configmaps.yaml](templates/configmaps.yaml) - 5 ConfigMap resources
- [templates/_helpers.tpl](templates/_helpers.tpl) - Template helper functions
- [templates/NOTES.txt](templates/NOTES.txt) - Post-install instructions

### StatefulSets - Data Layer (5 files)
- [templates/qdrant-statefulset.yaml](templates/qdrant-statefulset.yaml) - Qdrant vector database
- [templates/redis-statefulset.yaml](templates/redis-statefulset.yaml) - Redis cache
- [templates/postgres-statefulset.yaml](templates/postgres-statefulset.yaml) - PostgreSQL database
- [templates/neo4j-statefulset.yaml](templates/neo4j-statefulset.yaml) - Neo4j graph database
- [templates/minio-statefulset.yaml](templates/minio-statefulset.yaml) - MinIO object storage

### Deployments - Inference Engines (3 files)
- [templates/max-serve-llama-deployment.yaml](templates/max-serve-llama-deployment.yaml) - Llama 3.3 8B (General)
- [templates/max-serve-qwen-deployment.yaml](templates/max-serve-qwen-deployment.yaml) - Qwen 2.5 Coder (Code)
- [templates/max-serve-deepseek-deployment.yaml](templates/max-serve-deepseek-deployment.yaml) - DeepSeek R1 (Reasoning)

### Deployments - Application Services (5 files)
- [templates/agent-router-deployment.yaml](templates/agent-router-deployment.yaml) - Agent Router API
- [templates/gateway-deployment.yaml](templates/gateway-deployment.yaml) - Gateway Service
- [templates/mcpjungle-deployment.yaml](templates/mcpjungle-deployment.yaml) - MCP Gateway
- [templates/learning-engine-deployment.yaml](templates/learning-engine-deployment.yaml) - Learning Engine
- [templates/mem0-deployment.yaml](templates/mem0-deployment.yaml) - Memory Service

### Deployments - Observability (3 files)
- [templates/prometheus-deployment.yaml](templates/prometheus-deployment.yaml) - Prometheus metrics
- [templates/grafana-deployment.yaml](templates/grafana-deployment.yaml) - Grafana dashboards
- [templates/jaeger-deployment.yaml](templates/jaeger-deployment.yaml) - Jaeger tracing

## Quick Start Commands

### Install
```bash
helm install my-ai-platform ./helm/ai-platform \
  --namespace ai-platform \
  --create-namespace
```

### Verify
```bash
helm status my-ai-platform -n ai-platform
kubectl get pods -n ai-platform
```

### Upgrade
```bash
helm upgrade my-ai-platform ./helm/ai-platform \
  --namespace ai-platform \
  --values custom-values.yaml
```

### Uninstall
```bash
helm uninstall my-ai-platform --namespace ai-platform
```

## Component Overview

### Services Deployed (16)
1. **MAX Serve Llama** (8080) - General purpose LLM
2. **MAX Serve Qwen** (8081) - Code generation
3. **MAX Serve DeepSeek** (8082) - Advanced reasoning
4. **Agent Router** (8000, 8001) - Main API with routing
5. **Gateway** (9002) - External access
6. **MCPJungle** (9100) - MCP orchestration
7. **Learning Engine** (8003) - Fine-tuning service
8. **Mem0** (8006) - Memory management
9. **Qdrant** (6333, 6334) - Vector database
10. **Redis** (6379) - Cache
11. **PostgreSQL** (5432) - Relational DB
12. **Neo4j** (7474, 7687) - Graph database
13. **MinIO** (9000, 9001) - Object storage
14. **Prometheus** (9090) - Metrics
15. **Grafana** (3000) - Dashboards
16. **Jaeger** (16686) - Tracing

### Resource Requirements
- **CPUs**: 40+ cores
- **Memory**: 128Gi+
- **GPUs**: 3-4 NVIDIA
- **Storage**: 650Gi+

## Configuration Highlights

### High Availability
```yaml
agentRouter:
  replicaCount: 2  # HA configuration

gateway:
  replicaCount: 2  # HA configuration
```

### GPU Allocation
```yaml
maxServeLlama:
  resources:
    limits:
      nvidia.com/gpu: 1

learningEngine:
  resources:
    limits:
      nvidia.com/gpu: 1
```

### Storage Configuration
```yaml
qdrant:
  persistence:
    enabled: true
    storageClass: ""  # Use default or specify
    size: 100Gi

postgres:
  persistence:
    enabled: true
    size: 50Gi
```

### Service Types
```yaml
gateway:
  service:
    type: LoadBalancer  # External access

agentRouter:
  service:
    type: ClusterIP  # Internal only
```

## Common Customizations

### Disable Optional Services
```yaml
# In custom-values.yaml
mcpjungle:
  enabled: false

learningEngine:
  enabled: false

jaeger:
  enabled: false
```

### Scale Services
```yaml
agentRouter:
  replicaCount: 5

gateway:
  replicaCount: 3
```

### Update Secrets
```yaml
secrets:
  postgres:
    password: <base64-encoded>
  neo4j:
    password: <base64-encoded>
  minio:
    accessKey: <base64-encoded>
    secretKey: <base64-encoded>
  grafana:
    password: <base64-encoded>
```

### Custom Storage Classes
```yaml
qdrant:
  persistence:
    storageClass: "fast-ssd"

postgres:
  persistence:
    storageClass: "standard"
```

## Troubleshooting Quick Reference

### Check Pod Status
```bash
kubectl get pods -n ai-platform
kubectl describe pod <pod-name> -n ai-platform
```

### View Logs
```bash
kubectl logs -f deployment/agent-router -n ai-platform
kubectl logs -f deployment/max-serve-llama -n ai-platform
```

### Check Storage
```bash
kubectl get pvc -n ai-platform
kubectl get pv
```

### Test Connectivity
```bash
kubectl run -it --rm debug \
  --image=curlimages/curl \
  --restart=Never \
  -n ai-platform \
  -- curl http://agent-router:8000/health
```

### Check GPU Allocation
```bash
kubectl describe nodes | grep -A 10 "nvidia.com/gpu"
```

## External References

- **Repository Root**: ../..
- **Architecture**: ../../AGENTS.md
- **API Documentation**: ../../QUICKSTART.md
- **Implementation Summary**: ../../HELM_CHART_SUMMARY.md
- **Files Created**: ../../HELM_CHART_FILES_CREATED.md

## File Tree

```
helm/ai-platform/
├── Chart.yaml
├── values.yaml
├── README.md
├── DEPLOYMENT_GUIDE.md
├── INDEX.md
├── .helmignore
└── templates/
    ├── _helpers.tpl
    ├── NOTES.txt
    ├── namespace.yaml
    ├── secrets.yaml
    ├── configmaps.yaml
    ├── qdrant-statefulset.yaml
    ├── redis-statefulset.yaml
    ├── postgres-statefulset.yaml
    ├── neo4j-statefulset.yaml
    ├── minio-statefulset.yaml
    ├── max-serve-llama-deployment.yaml
    ├── max-serve-qwen-deployment.yaml
    ├── max-serve-deepseek-deployment.yaml
    ├── agent-router-deployment.yaml
    ├── gateway-deployment.yaml
    ├── mcpjungle-deployment.yaml
    ├── learning-engine-deployment.yaml
    ├── mem0-deployment.yaml
    ├── prometheus-deployment.yaml
    ├── grafana-deployment.yaml
    └── jaeger-deployment.yaml
```

## Support & Contact

For issues or questions:
- Read the [README.md](README.md) for detailed documentation
- Follow the [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) for step-by-step instructions
- Check values.yaml for all configuration options
- Review ../../AGENTS.md for architecture details

---

**Chart Version**: 1.0.0  
**App Version**: 2.0.0  
**Last Updated**: 2025
