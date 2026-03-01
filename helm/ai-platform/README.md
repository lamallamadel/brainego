# AI Platform Helm Chart

A comprehensive Kubernetes Helm chart for deploying the AI Platform with MAX Serve, Agent Router, RAG, Memory, Graph services, and full observability stack.

## Overview

This Helm chart deploys a complete AI platform including:

- **Inference Engines**: MAX Serve with Llama 3.3 8B, Qwen 2.5 Coder 7B, and DeepSeek R1 7B
- **API Layer**: Agent Router, Gateway Service, MCPJungle Gateway
- **AI Services**: Learning Engine, MAML Meta-Learning Service, Mem0 Memory Service
- **Data Stores**: Qdrant (vector), Redis (cache), PostgreSQL (relational), Neo4j (graph), MinIO (object storage)
- **Observability**: Prometheus, Grafana, Jaeger

## Prerequisites

- Kubernetes 1.19+
- Helm 3.0+
- GPU nodes with NVIDIA GPU Operator installed (for MAX Serve deployments)
- Storage provisioner for persistent volumes
- At least 128GB total cluster memory
- At least 4 GPUs (1 per MAX Serve model + 1 for Learning Engine)

## Installation

### Quick Start

```bash
# Add the repository (if published)
helm repo add ai-platform https://charts.example.com/ai-platform
helm repo update

# Install with default values
helm install my-ai-platform ai-platform/ai-platform \
  --namespace ai-platform \
  --create-namespace
```

### Install from Local Chart

```bash
# From the repository root
helm install my-ai-platform ./helm/ai-platform \
  --namespace ai-platform \
  --create-namespace
```

### Custom Installation

```bash
# Create custom values file
cat > custom-values.yaml <<EOF
# Disable components you don't need
mcpjungle:
  enabled: false

learningEngine:
  enabled: false

# Use custom storage class
qdrant:
  persistence:
    storageClass: fast-ssd

# Scale Agent Router
agentRouter:
  replicaCount: 3

# Custom secrets
secrets:
  postgres:
    password: <base64-encoded-password>
EOF

# Install with custom values
helm install my-ai-platform ./helm/ai-platform \
  --namespace ai-platform \
  --create-namespace \
  --values custom-values.yaml
```

## Configuration

### Global Settings

| Parameter | Description | Default |
|-----------|-------------|---------|
| `global.namespace` | Global namespace | `ai-platform` |
| `namespace.create` | Create namespace | `true` |
| `namespace.name` | Namespace name | `ai-platform` |

### MAX Serve Models

#### Llama 3.3 8B (General Purpose)

| Parameter | Description | Default |
|-----------|-------------|---------|
| `maxServeLlama.enabled` | Enable Llama deployment | `true` |
| `maxServeLlama.replicaCount` | Number of replicas | `1` |
| `maxServeLlama.service.port` | Service port | `8080` |
| `maxServeLlama.resources.limits.nvidia.com/gpu` | GPU limit | `1` |
| `maxServeLlama.persistence.models.size` | Model storage size | `50Gi` |

#### Qwen 2.5 Coder 7B (Code)

| Parameter | Description | Default |
|-----------|-------------|---------|
| `maxServeQwen.enabled` | Enable Qwen deployment | `true` |
| `maxServeQwen.replicaCount` | Number of replicas | `1` |
| `maxServeQwen.service.port` | Service port | `8081` |
| `maxServeQwen.resources.limits.nvidia.com/gpu` | GPU limit | `1` |

#### DeepSeek R1 7B (Reasoning)

| Parameter | Description | Default |
|-----------|-------------|---------|
| `maxServeDeepseek.enabled` | Enable DeepSeek deployment | `true` |
| `maxServeDeepseek.replicaCount` | Number of replicas | `1` |
| `maxServeDeepseek.service.port` | Service port | `8082` |
| `maxServeDeepseek.resources.limits.nvidia.com/gpu` | GPU limit | `1` |

### Application Services

#### Agent Router

| Parameter | Description | Default |
|-----------|-------------|---------|
| `agentRouter.enabled` | Enable Agent Router | `true` |
| `agentRouter.replicaCount` | Number of replicas | `2` |
| `agentRouter.service.port` | Service port | `8000` |
| `agentRouter.service.metricsPort` | Metrics port | `8001` |

#### Gateway

| Parameter | Description | Default |
|-----------|-------------|---------|
| `gateway.enabled` | Enable Gateway | `true` |
| `gateway.replicaCount` | Number of replicas | `2` |
| `gateway.service.type` | Service type | `LoadBalancer` |
| `gateway.service.port` | Service port | `9002` |

#### Learning Engine

| Parameter | Description | Default |
|-----------|-------------|---------|
| `learningEngine.enabled` | Enable Learning Engine | `true` |
| `learningEngine.replicaCount` | Number of replicas | `1` |
| `learningEngine.service.port` | Service port | `8003` |
| `learningEngine.resources.limits.nvidia.com/gpu` | GPU limit | `1` |
| `learningEngine.persistence.loraAdapters.size` | LoRA adapter storage | `20Gi` |

#### MAML Meta-Learning Service

| Parameter | Description | Default |
|-----------|-------------|---------|
| `mamlService.enabled` | Enable MAML service deployment | `true` |
| `mamlService.service.port` | Service port | `8005` |
| `mamlCronJob.enabled` | Enable monthly meta-training CronJob | `true` |
| `mamlCronJob.schedule` | Cron schedule for monthly run | `"0 2 1 * *"` |

### Data Stores

#### Qdrant (Vector Database)

| Parameter | Description | Default |
|-----------|-------------|---------|
| `qdrant.enabled` | Enable Qdrant | `true` |
| `qdrant.replicaCount` | Number of replicas | `1` |
| `qdrant.service.port` | HTTP port | `6333` |
| `qdrant.service.grpcPort` | gRPC port | `6334` |
| `qdrant.persistence.size` | Storage size | `100Gi` |

#### Redis (Cache)

| Parameter | Description | Default |
|-----------|-------------|---------|
| `redis.enabled` | Enable Redis | `true` |
| `redis.replicaCount` | Number of replicas | `1` |
| `redis.service.port` | Service port | `6379` |
| `redis.persistence.size` | Storage size | `10Gi` |

#### PostgreSQL (Relational)

| Parameter | Description | Default |
|-----------|-------------|---------|
| `postgres.enabled` | Enable PostgreSQL | `true` |
| `postgres.replicaCount` | Number of replicas | `1` |
| `postgres.service.port` | Service port | `5432` |
| `postgres.persistence.size` | Storage size | `50Gi` |

#### Neo4j (Graph)

| Parameter | Description | Default |
|-----------|-------------|---------|
| `neo4j.enabled` | Enable Neo4j | `true` |
| `neo4j.replicaCount` | Number of replicas | `1` |
| `neo4j.service.httpPort` | HTTP port | `7474` |
| `neo4j.service.boltPort` | Bolt port | `7687` |
| `neo4j.persistence.data.size` | Data storage size | `50Gi` |

### Monitoring

#### Prometheus

| Parameter | Description | Default |
|-----------|-------------|---------|
| `prometheus.enabled` | Enable Prometheus | `true` |
| `prometheus.service.port` | Service port | `9090` |
| `prometheus.persistence.data.size` | Storage size | `50Gi` |

#### Grafana

| Parameter | Description | Default |
|-----------|-------------|---------|
| `grafana.enabled` | Enable Grafana | `true` |
| `grafana.service.type` | Service type | `LoadBalancer` |
| `grafana.service.port` | Service port | `3000` |
| `grafana.persistence.data.size` | Storage size | `10Gi` |

#### Jaeger

| Parameter | Description | Default |
|-----------|-------------|---------|
| `jaeger.enabled` | Enable Jaeger | `true` |
| `jaeger.service.queryPort` | Query UI port | `16686` |
| `jaeger.service.otlpGrpcPort` | OTLP gRPC port | `4317` |

### Secrets

All secrets use base64 encoding. Update these in production:

| Parameter | Description | Default (encoded) |
|-----------|-------------|-------------------|
| `secrets.postgres.password` | PostgreSQL password | `ai_password` |
| `secrets.neo4j.password` | Neo4j password | `neo4j_password` |
| `secrets.minio.accessKey` | MinIO access key | `minioadmin` |
| `secrets.minio.secretKey` | MinIO secret key | `minioadmin123` |
| `secrets.grafana.password` | Grafana admin password | `admin` |

## Usage

### Accessing Services

#### Agent Router API

```bash
# Port forward
kubectl port-forward -n ai-platform svc/agent-router 8000:8000

# Test
curl http://localhost:8000/health
```

#### Gateway Service

```bash
# If LoadBalancer
kubectl get svc gateway -n ai-platform

# If ClusterIP
kubectl port-forward -n ai-platform svc/gateway 9002:9002
```

#### Grafana Dashboards

```bash
# Get admin password (default: admin)
kubectl get secret grafana-credentials -n ai-platform -o jsonpath='{.data.password}' | base64 -d

# Access Grafana
kubectl port-forward -n ai-platform svc/grafana 3000:3000
```

#### Jaeger Tracing

```bash
kubectl port-forward -n ai-platform svc/jaeger 16686:16686
# Open http://localhost:16686
```

### Scaling

```bash
# Scale Agent Router
helm upgrade my-ai-platform ./helm/ai-platform \
  --namespace ai-platform \
  --set agentRouter.replicaCount=5

# Scale Gateway
helm upgrade my-ai-platform ./helm/ai-platform \
  --namespace ai-platform \
  --set gateway.replicaCount=3
```

### Updating Configuration

```bash
# Update values
helm upgrade my-ai-platform ./helm/ai-platform \
  --namespace ai-platform \
  --values custom-values.yaml
```

## Uninstallation

```bash
# Uninstall release
helm uninstall my-ai-platform --namespace ai-platform

# Delete namespace (if you want to remove everything)
kubectl delete namespace ai-platform
```

## Troubleshooting

### Check Pod Status

```bash
kubectl get pods -n ai-platform
kubectl describe pod <pod-name> -n ai-platform
```

### View Logs

```bash
# Agent Router
kubectl logs -f deployment/agent-router -n ai-platform

# MAX Serve Llama
kubectl logs -f deployment/max-serve-llama -n ai-platform

# All pods
kubectl logs -f -l app.kubernetes.io/component=inference -n ai-platform
```

### Check GPU Allocation

```bash
kubectl describe nodes | grep -A 5 "nvidia.com/gpu"
```

### Storage Issues

```bash
# Check PVCs
kubectl get pvc -n ai-platform

# Check PVs
kubectl get pv

# Describe PVC
kubectl describe pvc <pvc-name> -n ai-platform
```

### Service Connectivity

```bash
# Test from a pod
kubectl run -it --rm debug --image=curlimages/curl --restart=Never -n ai-platform -- sh

# Inside the pod
curl http://agent-router:8000/health
curl http://max-serve-llama:8080/health
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     Load Balancer                       │
│                   (Gateway Service)                     │
└──────────────────┬──────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────┐
│              Agent Router (2 replicas)                  │
│         OpenAI-compatible API + Routing                 │
└──────────────────┬──────────────────────────────────────┘
                   │
         ┌─────────┴─────────┬─────────────┐
         │                   │             │
┌────────▼────────┐  ┌───────▼──────┐  ┌──▼──────────┐
│ MAX Serve       │  │ MAX Serve    │  │ MAX Serve   │
│ Llama 3.3 8B    │  │ Qwen 2.5 7B  │  │ DeepSeek R1 │
│ (General)       │  │ (Code)       │  │ (Reasoning) │
└─────────────────┘  └──────────────┘  └─────────────┘
         │                   │             │
         └─────────┬─────────┴─────────────┘
                   │
         ┌─────────┴─────────┐
         │                   │
┌────────▼────────┐  ┌───────▼──────────┐
│  Data Stores    │  │  AI Services     │
│  - Qdrant       │  │  - Learning Eng. │
│  - Redis        │  │  - Mem0          │
│  - PostgreSQL   │  │  - MCPJungle     │
│  - Neo4j        │  └──────────────────┘
│  - MinIO        │
└─────────────────┘
         │
┌────────▼────────────────────────────────────────────────┐
│              Observability Stack                        │
│  - Prometheus (Metrics)                                 │
│  - Grafana (Dashboards)                                 │
│  - Jaeger (Distributed Tracing)                         │
└─────────────────────────────────────────────────────────┘
```

## Support

For issues and questions:
- GitHub Issues: https://github.com/your-org/ai-platform/issues
- Documentation: See AGENTS.md in the repository

## License

[Your License Here]
