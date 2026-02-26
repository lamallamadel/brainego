# AI Platform Infrastructure with MAX Serve & Llama 3.3

Docker Compose infrastructure for an AI platform with MAX Serve running three GGUF models (Llama 3.3 8B, Qwen2.5-Coder 7B, and DeepSeek-R1-Distill-Qwen-7B), plus Qdrant, Redis, PostgreSQL, and MinIO. Includes an OpenAI-compatible API and comprehensive load-testing tools.

## Features

- 🚀 **MAX Serve (multi-model)** with Llama 3.3 8B, Qwen2.5-Coder 7B, and DeepSeek-R1-Distill-Qwen-7B
- 🔄 **Dynamic Batching** (max_batch_size=32) for optimal throughput
- 🌐 **OpenAI-Compatible API** (`/v1/chat/completions`, `/health`, `/metrics`)
- 📊 **Load Testing** with P50/P95/P99 latency metrics
- 🎯 **Complete AI Stack**: Qdrant, Redis, PostgreSQL, MinIO

## Prerequisites

- Docker Engine 20.10+
- Docker Compose 2.0+
- NVIDIA GPU with CUDA support (recommended)
- nvidia-docker2 or nvidia-container-toolkit
- Python 3.11+ (for local testing)

## Quick Start

### 1. Download the Model

```bash
chmod +x download_model.sh
./download_model.sh
```

This downloads Llama 3.3 8B Instruct Q4_K_M (~4.5 GB) to the `models/` directory.

### 2. Start All Services

```bash
chmod +x init.sh
./init.sh
```

If you want to include the Docker cloud/observability override config, enable it before running init:

```bash
USE_DOCKER_CLOUD_CONFIG=true ./init.sh
```

The initialization script will:
- Validate Docker and GPU availability
- Create necessary directories
- Pull Docker images
- Start all services
- Verify service health

### 3. Test the API

```bash
# Install Python dependencies
pip install -r requirements.txt

# Run basic tests
python test_api.py
```

### 4. Run Load Tests

```bash
# Quick test (100 requests, 10 concurrent)
python load_test.py

# Custom test
python load_test.py --requests 500 --concurrency 20 --scenario all

# Full stress test
python load_test.py --requests 1000 --concurrency 32 --max-tokens 200
```

## Service Endpoints

| Service | Endpoint | Description |
|---------|----------|-------------|
| **API Server** | http://localhost:8000 | OpenAI-compatible API |
| **Chat Completions** | http://localhost:8000/v1/chat/completions | Main chat endpoint |
| **Health Check** | http://localhost:8000/health | Service health status |
| **Metrics** | http://localhost:8000/metrics | Performance metrics |
| **MAX Serve (Llama)** | http://localhost:8080 | General-purpose model endpoint |
| **MAX Serve (Qwen Coder)** | http://localhost:8081 | Coding-specialized endpoint |
| **MAX Serve (DeepSeek R1)** | http://localhost:8082 | Reasoning-specialized endpoint |
| **Qdrant** | http://localhost:6333 | Vector database |
| **Redis** | localhost:6379 | Cache & message broker |
| **PostgreSQL** | localhost:5432 | Relational database |
| **MinIO Console** | http://localhost:9001 | Object storage UI |
| **MinIO API** | http://localhost:9000 | S3-compatible API |

## API Usage

### Chat Completions

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama-3.3-8b-instruct",
    "messages": [
      {"role": "system", "content": "You are a helpful assistant."},
      {"role": "user", "content": "Explain quantum computing in simple terms."}
    ],
    "max_tokens": 200,
    "temperature": 0.7
  }'
```

### Python Example

```python
import requests

response = requests.post(
    "http://localhost:8000/v1/chat/completions",
    json={
        "model": "llama-3.3-8b-instruct",
        "messages": [
            {"role": "user", "content": "Hello! How are you?"}
        ],
        "max_tokens": 100
    }
)

print(response.json()["choices"][0]["message"]["content"])
```

### Streaming Chat Completions

```bash
curl -N -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama-3.3-8b-instruct",
    "messages": [
      {"role": "user", "content": "Write one sentence about local LLM APIs."}
    ],
    "stream": true
  }'
```

The API returns Server-Sent Events in OpenAI-compatible `chat.completion.chunk` format ending with `data: [DONE]`.

### Health Check

```bash
curl http://localhost:8000/health
```

Response:
```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T12:00:00.000000",
  "model": "llama-3.3-8b-instruct",
  "max_serve_status": "healthy"
}
```

## Load Testing

The `load_test.py` script provides comprehensive performance testing with detailed latency metrics.

### Basic Usage

```bash
# Default test (100 requests, 10 concurrent, medium scenario)
python load_test.py

# Custom parameters
python load_test.py \
  --requests 500 \
  --concurrency 20 \
  --max-tokens 150 \
  --scenario medium
```

### Test Scenarios

- **short**: Simple greeting (minimal tokens)
- **medium**: Standard assistant query
- **long**: Complex multi-turn conversation
- **all**: Run all scenarios sequentially

### Metrics Reported

- **Throughput**: Requests per second
- **Success Rate**: Percentage of successful requests
- **Latency Distribution**:
  - Min/Max/Mean/Median
  - **P50** (50th percentile)
  - **P95** (95th percentile)
  - **P99** (99th percentile)
  - Standard deviation
- **Token Usage**: Prompt, completion, and total tokens

### Example Output

```
📊 Request Summary:
  Total Requests:      100
  Successful:          100 (100.0%)
  Failed:              0 (0.0%)
  Duration:            45.23s
  Throughput:          2.21 req/s

⚡ Latency Metrics (milliseconds):
  Min:                 234.56 ms
  Max:                 1823.45 ms
  Mean:                452.34 ms
  Median:              421.12 ms
  P50 (50th percentile): 421.12 ms
  P95 (95th percentile): 876.54 ms
  P99 (99th percentile): 1234.56 ms
  Std Dev:             123.45 ms

🔤 Token Usage:
  Total Prompt Tokens:     12,345
  Total Completion Tokens: 23,456
  Total Tokens:            35,801
  Avg Tokens/Request:      358.0
```

## Configuration

### MAX Serve Configuration

Edit `configs/max-serve-config.yaml`:

```yaml
model:
  name: "llama-3.3-8b-instruct"
  path: "/models/llama-3.3-8b-instruct-q4_k_m.gguf"

batching:
  max_batch_size: 32        # Batch size for concurrent requests
  max_wait_time_ms: 10      # Max wait time for batching
  timeout_ms: 30000         # Request timeout

inference:
  max_tokens: 2048
  temperature: 0.7
  context_length: 8192
```

### Batching Benefits

With `max_batch_size=32`, MAX Serve can process up to 32 requests simultaneously, providing:
- **Higher throughput** for concurrent requests
- **Lower per-request latency** under load
- **Better GPU utilization**

## Architecture

```
┌─────────────────┐
│   Load Tester   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   API Server    │
│  (Port 8000)    │
│ - Chat API      │
│ - Health Check  │
│ - Metrics       │
└────────┬────────┘
         │
         ▼
┌───────────────────────────────────────────┐
│            MAX Serve Backends             │
│  ┌──────────────┬──────────────┬────────┐ │
│  │ Llama 3.3    │ Qwen Coder   │ DeepSeek│ │
│  │ (Port 8080)  │ (Port 8081)  │ (8082)  │ │
│  └──────────────┴──────────────┴────────┘ │
└───────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│         Support Services            │
│  ┌────────┬────────┬────────────┐  │
│  │ Qdrant │ Redis  │ PostgreSQL │  │
│  ├────────┴────────┴────────────┤  │
│  │         MinIO                │  │
│  └──────────────────────────────┘  │
└─────────────────────────────────────┘
```

## Directory Structure

```
.
├── docker-compose.yaml           # Service orchestration
├── Dockerfile.api                # API server container
├── init.sh                       # Initialization script
├── download_model.sh             # Model download script
├── api_server.py                 # OpenAI-compatible API
├── load_test.py                  # Load testing tool
├── test_api.py                   # Basic API tests
├── requirements.txt              # Python dependencies
├── configs/
│   └── max-serve-config.yaml    # MAX Serve configuration
├── models/                       # Model storage (created by init.sh)
│   ├── llama-3.3-8b-instruct-q4_k_m.gguf
│   ├── qwen2.5-coder-7b-instruct-q4_k_m.gguf
│   └── deepseek-r1-distill-qwen-7b-q4_k_m.gguf
├── logs/                         # Application logs
└── init-scripts/
    └── postgres/
        └── init.sql             # Database initialization
```

## Management Commands

```bash
# Start all services
docker compose up -d

# Start all services with cloud/observability config override
docker compose -f docker-compose.yaml -f docker-compose.observability.yml up -d

# Start specific model services
docker compose up -d max-serve-llama max-serve-qwen max-serve-deepseek

# Stop all services
docker compose down

# View logs
docker compose logs -f max-serve-llama
docker compose logs -f max-serve-qwen
docker compose logs -f max-serve-deepseek
docker compose logs -f api-server

# Restart service
docker compose restart max-serve-llama max-serve-qwen max-serve-deepseek

# Check status
docker compose ps

# Remove all data (WARNING: destructive)
docker compose down -v
```

## Troubleshooting

### GPU Not Detected

```bash
# Check NVIDIA driver
nvidia-smi

# Test Docker GPU access
docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi

# Install NVIDIA Container Toolkit (Ubuntu)
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | \
  sudo tee /etc/apt/sources.list.d/nvidia-docker.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker
```

### MAX Serve Not Starting

```bash
# Check logs
docker compose logs max-serve-llama
docker compose logs max-serve-qwen
docker compose logs max-serve-deepseek

# Verify model file exists
ls -lh models/llama-3.3-8b-instruct-q4_k_m.gguf

# Check GPU availability in container
docker exec max-serve-llama nvidia-smi
docker exec max-serve-qwen nvidia-smi
docker exec max-serve-deepseek nvidia-smi
```

### API Connection Issues

```bash
# Check if API server is running
docker compose ps api-server

# Test MAX Serve directly
curl http://localhost:8080/health

# Test API server
curl http://localhost:8000/health

# Validate merged Docker cloud config
docker compose -f docker-compose.yaml -f docker-compose.observability.yml config >/tmp/brainego-compose-cloud.txt

# Check network connectivity
docker compose exec api-server ping max-serve-llama
docker compose exec api-server ping max-serve-qwen
docker compose exec api-server ping max-serve-deepseek
```

### Performance Optimization

For better performance:

1. **Increase batch size** (if you have more GPU memory):
   ```yaml
   batching:
     max_batch_size: 64  # or higher
   ```

2. **Adjust concurrency** in load tests based on your hardware
3. **Monitor GPU usage**: `watch -n 1 nvidia-smi`
4. **Use SSD** for model storage
5. **Increase system RAM** for larger context windows

## Model Information

**Llama 3.3 8B Instruct (Q4_K_M)**
- **Port**: 8080
- **Use Case**: General-purpose chat and instruction following

**Qwen2.5-Coder 7B Instruct (Q4_K_M)**
- **Port**: 8081
- **Use Case**: Coding, debugging, and developer workflows

**DeepSeek-R1-Distill-Qwen-7B (Q4_K_M)**
- **Port**: 8082
- **Use Case**: Reasoning-heavy and analytical tasks

## Performance Expectations

With NVIDIA GPU (e.g., RTX 3090/4090):
- **Latency**: 200-500ms for typical queries
- **P95 Latency**: <1000ms under load
- **Throughput**: 10-30 requests/second (batch_size=32)
- **Tokens/second**: 40-80 tokens/second per request

## Security Notes

⚠️ **Default credentials are for development only!**

For production:
1. Change all default passwords in `.env`
2. Use secrets management (Docker secrets, Vault)
3. Enable SSL/TLS for all services
4. Restrict network access (firewall, VPN)
5. Implement authentication/authorization
6. Regular security updates
7. Monitor and audit access logs

## License

This infrastructure setup is provided as-is for development and testing purposes.

## Support

For issues and questions:
- MAX Serve: https://docs.modular.com/max/serve
- Llama 3.3: https://huggingface.co/meta-llama
- Docker Compose: https://docs.docker.com/compose

## Contributing

Contributions are welcome! Please ensure:
- Code follows existing patterns
- Documentation is updated
- Tests pass successfully
- Security best practices are followed
