# AI Platform Infrastructure

Docker Compose infrastructure for AI platform with MAX Serve, Qdrant, Redis, PostgreSQL, and MinIO.

## Prerequisites

- Docker Engine 20.10+
- Docker Compose 2.0+
- NVIDIA GPU with CUDA support (optional, but recommended for MAX Serve)
- nvidia-docker2 or nvidia-container-toolkit (for GPU support)

## Quick Start

1. **Initialize the platform:**
   ```bash
   chmod +x init.sh
   ./init.sh
   ```

   The initialization script will:
   - Validate Docker installation
   - Check GPU availability
   - Create necessary directories
   - Pull Docker images
   - Start all services
   - Verify service health

2. **Access services:**
   - MAX Serve: http://localhost:8080
   - Qdrant: http://localhost:6333
   - Redis: localhost:6379
   - PostgreSQL: localhost:5432
   - MinIO Console: http://localhost:9001
   - MinIO API: http://localhost:9000

## Services

### MAX Serve
High-performance AI model serving with GPU acceleration.
- Port: 8080
- GPU: NVIDIA GPU required for optimal performance
- Volumes: `./models`, `./configs`

### Qdrant
Vector database for embeddings and similarity search.
- HTTP Port: 6333
- gRPC Port: 6334
- Volume: `qdrant-storage`

### Redis
In-memory cache and message broker.
- Port: 6379
- Max Memory: 2GB with LRU eviction
- Volume: `redis-data`

### PostgreSQL
Relational database for structured data.
- Port: 5432
- Database: `ai_platform`
- User: `ai_user`
- Password: `ai_password`
- Volume: `postgres-data`

### MinIO
S3-compatible object storage for models and artifacts.
- API Port: 9000
- Console Port: 9001
- User: `minioadmin`
- Password: `minioadmin123`
- Volume: `minio-data`

## Network

All services are connected via the `ai-platform-net` bridge network, enabling inter-service communication using service names as hostnames.

## Management Commands

```bash
# Start services
docker compose up -d

# Stop services
docker compose down

# View logs
docker compose logs -f [service_name]

# Restart specific service
docker compose restart [service_name]

# Check service status
docker compose ps

# Remove all data (WARNING: destructive)
docker compose down -v
```

## Directory Structure

```
.
├── docker-compose.yaml      # Service definitions
├── init.sh                  # Initialization script
├── .env                     # Environment variables (auto-generated)
├── models/                  # Model storage
├── configs/                 # Configuration files
├── init-scripts/            # Initialization scripts
│   └── postgres/           # PostgreSQL init scripts
└── logs/                   # Application logs
```

## Configuration

### Environment Variables
Edit `.env` file to customize service configuration:
- PostgreSQL credentials
- MinIO credentials
- Redis memory limits
- Project name

### Service Configuration
- MAX Serve: `configs/max-serve.yaml`
- PostgreSQL: `init-scripts/postgres/init.sql`

## GPU Support

The platform requires NVIDIA GPU for MAX Serve. If GPU is not available:
1. The init script will warn you
2. You can continue without GPU (not recommended)
3. MAX Serve may fail or run with degraded performance

To enable GPU support:
```bash
# Install NVIDIA Container Toolkit
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | \
  sudo tee /etc/apt/sources.list.d/nvidia-docker.list

sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker
```

## Troubleshooting

**Service not starting:**
```bash
docker compose logs [service_name]
```

**GPU not detected:**
```bash
nvidia-smi
docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi
```

**Port conflicts:**
Edit `docker-compose.yaml` to change port mappings.

**Reset everything:**
```bash
docker compose down -v
rm -rf models/ logs/ init-scripts/
./init.sh
```

## Security Notes

⚠️ **Default credentials are for development only!**

For production:
1. Change all default passwords in `.env`
2. Use secrets management
3. Enable SSL/TLS for all services
4. Restrict network access
5. Regular security updates
