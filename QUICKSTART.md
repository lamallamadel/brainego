# Quick Start Guide

Get up and running with MAX Serve and Llama 3.3 8B in minutes.

## 🚀 5-Minute Setup

### Step 1: Download the Model (One-time)

```bash
chmod +x download_model.sh
./download_model.sh
```

**Time**: ~10-15 minutes (depending on internet speed)
**Size**: ~4.5 GB

### Step 2: Start Services

```bash
chmod +x init.sh
./init.sh
```

**Time**: ~2-3 minutes (first run includes image pulls)

### Step 3: Verify Installation

```bash
# Install Python dependencies
pip install -r requirements.txt

# Test the API
python test_api.py
```

**Expected Output:**
```
Testing /health endpoint...
Status: 200
Response: {
  "status": "healthy",
  "model": "llama-3.3-8b-instruct",
  "max_serve_status": "healthy"
}

Testing /v1/chat/completions endpoint...
Status: 200
Latency: 456.78ms
Message: The capital of France is Paris.
```

## 🎯 Quick Commands

```bash
# Using Make (recommended)
make help           # Show all commands
make install        # Install Python dependencies
make download       # Download model
make start          # Start all services
make test           # Run basic tests
make load-test      # Run load tests
make monitor        # Real-time monitoring
make stop           # Stop services

# Using Docker Compose directly
docker compose up -d              # Start services
docker compose down               # Stop services
docker compose logs -f max-serve  # View logs
docker compose ps                 # Check status
```

## 📡 Test Your First Request

### Command Line (curl)

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama-3.3-8b-instruct",
    "messages": [{"role": "user", "content": "Hello!"}],
    "max_tokens": 100
  }'
```

### Python

```python
import requests

response = requests.post(
    "http://localhost:8000/v1/chat/completions",
    json={
        "model": "llama-3.3-8b-instruct",
        "messages": [{"role": "user", "content": "Hello!"}],
        "max_tokens": 100
    }
)

print(response.json()["choices"][0]["message"]["content"])
```

### Interactive Chat

```bash
python examples/chat_example.py
```

## 🔍 Performance Testing

### Quick Load Test (100 requests)

```bash
python load_test.py --requests 100 --concurrency 10
```

### Comprehensive Test (All Scenarios)

```bash
python load_test.py --requests 500 --concurrency 20 --scenario all
```

### Real-time Monitoring

```bash
python monitor.py
```

## 📊 What to Expect

### Performance Metrics (NVIDIA RTX 4090)

| Metric | Value |
|--------|-------|
| P50 Latency | ~400ms |
| P95 Latency | ~800ms |
| P99 Latency | ~1200ms |
| Throughput | 20-30 req/s |
| Max Batch Size | 32 concurrent requests |

*Your performance may vary based on hardware and configuration.*

## 🔧 Common Issues & Fixes

### Issue: GPU Not Detected

```bash
# Check GPU status
nvidia-smi

# Test Docker GPU access
docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi
```

**Fix**: Install NVIDIA Container Toolkit
```bash
# Ubuntu/Debian
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | \
  sudo tee /etc/apt/sources.list.d/nvidia-docker.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker
```

### Issue: Port Already in Use

```bash
# Check what's using the port
lsof -i :8000
lsof -i :8080

# Kill the process or change ports in docker-compose.yaml
```

### Issue: Out of Memory

**Fix**: Reduce batch size in `docker-compose.yaml`
```yaml
command: >
  max-serve
  --max-batch-size 16  # Reduce from 32
```

### Issue: Slow First Request

This is normal! The first request loads the model into GPU memory.
- First request: 30-60 seconds
- Subsequent requests: <1 second

## 📚 Next Steps

1. **Explore Examples**: Check `examples/` directory
   - Interactive chat
   - Batch processing
   - Advanced usage patterns

2. **Read Documentation**:
   - `README.md` - Comprehensive guide
   - `DEPLOYMENT.md` - Production deployment
   - `AGENTS.md` - Architecture & tech stack

3. **Customize Configuration**:
   - `configs/max-serve-config.yaml` - Model settings
   - `docker-compose.yaml` - Service configuration
   - `.env` - Environment variables

4. **Monitor Performance**:
   ```bash
   python monitor.py
   ```

5. **Run Load Tests**:
   ```bash
   python load_test.py --help
   ```

## 🎓 Learn More

### Key Concepts

**Batching**: MAX Serve processes multiple requests simultaneously (batch_size=32)
- Higher throughput under load
- Better GPU utilization
- Lower per-request cost

**Quantization**: Q4_K_M uses 4-bit quantization
- 70% smaller than full precision
- Minimal quality loss
- Faster inference

**Context Length**: 8,192 tokens
- ~6,000 words of context
- Suitable for most conversations

### API Endpoints

| Endpoint | Purpose |
|----------|---------|
| `/v1/chat/completions` | Main chat API (OpenAI-compatible) |
| `/health` | Service health check |
| `/metrics` | Performance metrics |
| `/v1/models` | List available models |

### Configuration Parameters

**Request Parameters**:
- `max_tokens`: Maximum response length (1-2048)
- `temperature`: Creativity (0.0-2.0, default: 0.7)
- `top_p`: Nucleus sampling (0.0-1.0, default: 0.9)

**Performance Tuning**:
- `max_batch_size`: Concurrent request capacity
- `max_wait_time_ms`: Batching delay
- `context_length`: Maximum conversation length

## 💡 Tips

1. **Warm-up**: Send a test request after starting to load the model
2. **Batch Requests**: Send multiple requests concurrently for best throughput
3. **Monitor GPU**: Use `nvidia-smi` to watch GPU utilization
4. **Adjust Tokens**: Reduce `max_tokens` for faster responses
5. **Connection Pooling**: Reuse HTTP connections in production

## 🆘 Getting Help

**Check logs**:
```bash
docker compose logs -f max-serve    # Model serving
docker compose logs -f api-server   # API server
```

**Check status**:
```bash
docker compose ps                   # All services
curl http://localhost:8000/health   # API health
curl http://localhost:8080/health   # MAX Serve health
```

**Restart services**:
```bash
docker compose restart max-serve
docker compose restart api-server
```

**Reset everything**:
```bash
docker compose down -v
./init.sh
```

## ✅ Verification Checklist

- [ ] Model downloaded successfully
- [ ] All services running (`docker compose ps`)
- [ ] GPU detected (`nvidia-smi`)
- [ ] Health check passes (`curl http://localhost:8000/health`)
- [ ] Test request successful (`python test_api.py`)
- [ ] Load test completes (`python load_test.py`)

## 🎉 You're Ready!

Your MAX Serve deployment with Llama 3.3 8B is ready for use. Start building!

```bash
# Start chatting
python examples/chat_example.py

# Or integrate into your application
# See examples/ for code samples
```

**Happy building! 🚀**
