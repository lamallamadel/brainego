# Deployment Guide: MAX Serve with Llama 3.3 8B

This guide covers deploying the MAX Serve infrastructure with Llama 3.3 8B Instruct in various environments.

## Table of Contents

- [Local Development](#local-development)
- [Production Deployment](#production-deployment)
- [Cloud Deployment](#cloud-deployment)
- [Dedicated GPU Host (AFR-5)](#dedicated-gpu-host-afr-5)
- [Configuration](#configuration)
- [Monitoring](#monitoring)
- [Scaling](#scaling)

## Local Development

### Prerequisites

- Ubuntu 20.04+ or similar Linux distribution
- NVIDIA GPU (RTX 3090, 4090, or better recommended)
- Docker Engine 20.10+
- Docker Compose 2.0+
- 16GB+ RAM
- 20GB+ free disk space

### Step-by-Step Setup

1. **Clone and prepare the repository:**
   ```bash
   git clone <repository-url>
   cd <repository-name>
   ```

2. **Download the model:**
   ```bash
   chmod +x download_model.sh
   ./download_model.sh
   ```

3. **Initialize services:**
   ```bash
   chmod +x init.sh
   ./init.sh
   ```

4. **Verify deployment:**
   ```bash
   # Check service health
   curl http://localhost:8000/health
   
   # Run basic tests
   python test_api.py
   ```

## Production Deployment

### Security Hardening

1. **Change default credentials:**
   ```bash
   # Edit .env file
   POSTGRES_PASSWORD=$(openssl rand -base64 32)
   MINIO_ROOT_PASSWORD=$(openssl rand -base64 32)
   ```

2. **Enable SSL/TLS:**
   - Use a reverse proxy (nginx, Caddy, Traefik)
   - Configure SSL certificates (Let's Encrypt)
   - Update docker-compose.yaml with SSL volumes

3. **Network security:**
   ```yaml
   # docker-compose.yaml
   networks:
     ai-platform-net:
       driver: bridge
       internal: true  # Isolate internal services
   ```

4. **Resource limits:**
   ```yaml
   services:
     max-serve:
       deploy:
         resources:
           limits:
             memory: 16G
             cpus: '8'
   ```

### Reverse Proxy Configuration

**Nginx Example:**

```nginx
upstream api_backend {
    server localhost:8000;
    keepalive 32;
}

server {
    listen 443 ssl http2;
    server_name api.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://api_backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Timeout for long-running requests
        proxy_connect_timeout 300s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
    }
}
```

### Environment Variables

Create a `.env.production` file:

```bash
# PostgreSQL
POSTGRES_DB=ai_platform
POSTGRES_USER=ai_user
POSTGRES_PASSWORD=<secure-password>

# MinIO
MINIO_ROOT_USER=<admin-user>
MINIO_ROOT_PASSWORD=<secure-password>

# Redis
REDIS_PASSWORD=<secure-password>

# API Configuration
MAX_SERVE_URL=http://max-serve:8080
LOG_LEVEL=INFO

# Rate Limiting
RATE_LIMIT_REQUESTS=100
RATE_LIMIT_WINDOW=60
```


## Dedicated GPU Host (AFR-5)

For the AFR-5 story (RTX 4090 + 64GB RAM + 500GB NVMe + SSH access), use the dedicated runbook:

- [`GPU_HOST_PROVISIONING.md`](GPU_HOST_PROVISIONING.md)

It includes:
- A requirement-to-command acceptance matrix
- Provisioning and SSH hardening steps
- MAX Serve readiness checks and handover template

## Cloud Deployment

### AWS Deployment

#### EC2 Instance

**Recommended instance types:**
- `g5.xlarge` or `g5.2xlarge` (NVIDIA A10G)
- `p3.2xlarge` (NVIDIA V100)
- `g4dn.xlarge` (NVIDIA T4) - budget option

**Setup script:**

```bash
#!/bin/bash
# AWS EC2 GPU Instance Setup

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker ubuntu

# Install NVIDIA drivers
sudo apt-get update
sudo apt-get install -y nvidia-driver-535

# Install NVIDIA Container Toolkit
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | \
  sudo tee /etc/apt/sources.list.d/nvidia-docker.list
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" \
  -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Reboot to load drivers
sudo reboot
```

#### ECS/EKS Deployment

For containerized orchestration, use Kubernetes manifests or ECS task definitions.

### GCP Deployment

**Recommended:**
- Compute Engine: `n1-standard-8` with NVIDIA T4 or A100
- GKE: GPU node pools

### Azure Deployment

**Recommended:**
- VM: `NC6s_v3` (NVIDIA V100)
- AKS: GPU-enabled node pools

## Configuration

### MAX Serve Tuning

Edit `configs/max-serve-config.yaml`:

```yaml
# For high-throughput scenarios
batching:
  max_batch_size: 64      # Increase if you have more GPU memory
  max_wait_time_ms: 5     # Lower for lower latency
  timeout_ms: 60000       # Increase for long responses

# For low-latency scenarios
batching:
  max_batch_size: 16      # Lower batch size
  max_wait_time_ms: 1     # Minimal wait time
  timeout_ms: 30000

# For memory-constrained environments
performance:
  num_gpu_layers: 32      # Offload fewer layers to GPU
  batch_size: 256         # Reduce batch size
```

### API Server Tuning

Environment variables for `api_server.py`:

```bash
# Increase workers for higher concurrency
UVICORN_WORKERS=8

# Connection pool settings
HTTPX_POOL_CONNECTIONS=100
HTTPX_POOL_MAXSIZE=100
```

## Monitoring

### Prometheus Metrics

Add Prometheus exporter to `docker-compose.yaml`:

```yaml
services:
  prometheus:
    image: prom/prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus-data:/prometheus

  grafana:
    image: grafana/grafana
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
    volumes:
      - grafana-data:/var/lib/grafana
```

### Logging

Configure structured logging:

```python
# In api_server.py
import logging
from pythonjsonlogger import jsonlogger

logHandler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter()
logHandler.setFormatter(formatter)
logger.addHandler(logHandler)
```

### Health Checks

Set up external monitoring:

```bash
# Uptime monitoring
curl -fsS --retry 3 https://hc-ping.com/YOUR-UUID-HERE http://localhost:8000/health

# Or use services like:
# - UptimeRobot
# - Pingdom
# - Datadog
# - New Relic
```

## Scaling

### Horizontal Scaling

1. **Multiple API server replicas:**
   ```yaml
   services:
     api-server:
       deploy:
         replicas: 4
   ```

2. **Load balancer (nginx):**
   ```nginx
   upstream api_servers {
       least_conn;
       server api-server-1:8000;
       server api-server-2:8000;
       server api-server-3:8000;
       server api-server-4:8000;
   }
   ```

3. **Multiple MAX Serve instances:**
   - Deploy separate MAX Serve containers on different GPUs
   - Use GPU device mapping: `CUDA_VISIBLE_DEVICES=0`, `CUDA_VISIBLE_DEVICES=1`

### Vertical Scaling

1. **Increase GPU memory:**
   - Use larger GPUs (A100 40GB/80GB)
   - Increase batch size and concurrent requests

2. **Optimize model:**
   - Use smaller quantization (Q3_K_M for less memory)
   - Reduce context length if not needed

3. **CPU resources:**
   - Increase CPU cores for preprocessing
   - Use faster storage (NVMe SSD)

### Auto-scaling

**Kubernetes HPA example:**

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: api-server-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: api-server
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

## Performance Benchmarks

### Expected Performance

| GPU Model | Batch Size | Throughput (req/s) | P95 Latency (ms) |
|-----------|------------|-------------------|------------------|
| RTX 4090  | 32         | 25-30             | 800-1000         |
| A10G      | 32         | 20-25             | 900-1100         |
| T4        | 16         | 10-15             | 1200-1500        |
| V100      | 32         | 30-35             | 700-900          |
| A100 40GB | 64         | 40-50             | 600-800          |

*Note: Performance varies based on input/output token length and system configuration.*

### Optimization Tips

1. **Warm-up**: Send initial requests to warm up the model
2. **Connection pooling**: Reuse HTTP connections
3. **Batch similar requests**: Group requests with similar token lengths
4. **Monitor GPU utilization**: Aim for 80-95% utilization
5. **Profile bottlenecks**: Use `nvidia-smi` and application metrics

## Troubleshooting

### Common Issues

**Out of Memory:**
```bash
# Reduce batch size
# In docker-compose.yaml
command: >
  max-serve
  --model-path /models/llama-3.3-8b-instruct-q4_k_m.gguf
  --max-batch-size 16  # Reduced from 32
```

**High Latency:**
```bash
# Check GPU utilization
nvidia-smi -l 1

# Monitor queue depth
docker compose logs -f max-serve | grep "queue"

# Increase workers
# Adjust in docker-compose.yaml or configs
```

**Connection Timeouts:**
```bash
# Increase timeout in load_test.py and api_server.py
timeout=600.0  # 10 minutes for very long responses
```

## Backup and Recovery

### Database Backup

```bash
# PostgreSQL
docker compose exec postgres pg_dump -U ai_user ai_platform > backup.sql

# Restore
docker compose exec -T postgres psql -U ai_user ai_platform < backup.sql
```

### Model Backup

```bash
# Backup model to S3
aws s3 cp models/llama-3.3-8b-instruct-q4_k_m.gguf \
  s3://your-bucket/models/

# Or to MinIO
mc cp models/llama-3.3-8b-instruct-q4_k_m.gguf \
  minio/models/
```

## Disaster Recovery

1. **Automated backups**: Schedule daily backups of databases
2. **Model versioning**: Keep previous model versions
3. **Configuration as code**: Store all configs in git
4. **Health monitoring**: Set up alerts for service failures
5. **Failover**: Deploy in multiple availability zones

## Support and Resources

- MAX Serve Documentation: https://docs.modular.com/max/serve
- Llama Model Card: https://huggingface.co/meta-llama/Llama-3.3-8B-Instruct
- Docker Best Practices: https://docs.docker.com/develop/dev-best-practices/
- NVIDIA GPU Cloud: https://www.nvidia.com/en-us/gpu-cloud/
