# MAX Serve + Llama 3.3 Quick Reference

## 🚀 Quick Start (3 Commands)

```bash
./download_model.sh          # Download model (~4.5 GB)
./init.sh                    # Start all services
python test_api.py           # Verify installation
```

## 📋 Essential Commands

### Service Management
```bash
# Using Make (recommended)
make start                   # Start all services
make stop                    # Stop all services
make restart                 # Restart services
make logs                    # View all logs
make logs-max               # MAX Serve logs only
make logs-api               # API server logs only
make health                  # Check health status

# Using Docker Compose
docker compose up -d         # Start services
docker compose down          # Stop services
docker compose ps            # Check status
docker compose logs -f       # Follow logs
```

### Testing
```bash
make test                    # Basic API tests
make load-test              # Quick load test (100 req)
make stress-test            # Intensive test (1000 req)
make monitor                # Real-time monitoring

python test_api.py          # Basic tests
python load_test.py         # Custom load test
python monitor.py           # Performance dashboard
```

## 🌐 API Endpoints

### Chat Completions
```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama-3.3-8b-instruct",
    "messages": [
      {"role": "user", "content": "Hello!"}
    ],
    "max_tokens": 100,
    "temperature": 0.7
  }'
```

### Health Check
```bash
curl http://localhost:8000/health
```

### Metrics
```bash
curl http://localhost:8000/metrics
```

## 🐍 Python Examples

### Simple Chat
```python
import requests

response = requests.post(
    "http://localhost:8000/v1/chat/completions",
    json={
        "model": "llama-3.3-8b-instruct",
        "messages": [{"role": "user", "content": "Hi!"}],
        "max_tokens": 100
    }
)

print(response.json()["choices"][0]["message"]["content"])
```

### With System Prompt
```python
response = requests.post(
    "http://localhost:8000/v1/chat/completions",
    json={
        "model": "llama-3.3-8b-instruct",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Explain AI in one sentence."}
        ]
    }
)
```

### Interactive Chat
```bash
python examples/chat_example.py
```

## ⚡ Load Testing

### Quick Test
```bash
python load_test.py \
  --requests 100 \
  --concurrency 10 \
  --scenario medium
```

### Full Test Suite
```bash
python load_test.py \
  --requests 500 \
  --concurrency 20 \
  --scenario all \
  --output results.json
```

### Visualize Results
```bash
python visualize_results.py results.json
```

### Real-time Monitoring
```bash
python monitor.py
# Press Ctrl+C to exit
```

## 📊 Key Metrics

| Metric | Target | Meaning |
|--------|--------|---------|
| P50 | <500ms | Median latency |
| P95 | <1000ms | 95% of requests faster than this |
| P99 | <1500ms | 99% of requests faster than this |
| Throughput | 20-30 req/s | Requests per second |

## ⚙️ Configuration

### MAX Serve Settings
Edit `configs/max-serve-config.yaml`:
```yaml
batching:
  max_batch_size: 32          # Concurrent requests
  max_wait_time_ms: 10        # Batching delay

inference:
  max_tokens: 2048            # Response length
  temperature: 0.7            # Creativity (0-2)
  context_length: 8192        # Context window
```

### Docker Compose
Edit `docker-compose.yaml`:
```yaml
command: >
  max-serve
  --max-batch-size 32
  --max-tokens 2048
  --port 8080
```

### API Request
```python
{
    "model": "llama-3.3-8b-instruct",
    "messages": [...],
    "max_tokens": 100,          # Response length (1-2048)
    "temperature": 0.7,         # Randomness (0.0-2.0)
    "top_p": 0.9,              # Nucleus sampling (0.0-1.0)
    "stop": ["<|eot_id|>"]     # Stop sequences
}
```

## 🔧 Troubleshooting

### GPU Not Working
```bash
nvidia-smi                   # Check GPU
docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi
```

### Service Not Starting
```bash
docker compose logs max-serve    # Check logs
docker compose restart max-serve # Restart service
```

### Port Already in Use
```bash
lsof -i :8000               # Check port 8000
lsof -i :8080               # Check port 8080
```

### Out of Memory
Reduce batch size in `docker-compose.yaml`:
```yaml
--max-batch-size 16         # Reduce from 32
```

### Slow First Request
This is normal! First request loads the model (~30-60s).

## 📁 Important Files

| File | Purpose |
|------|---------|
| `api_server.py` | OpenAI-compatible API |
| `load_test.py` | Load testing tool |
| `monitor.py` | Real-time dashboard |
| `docker-compose.yaml` | Service config |
| `configs/max-serve-config.yaml` | Model settings |
| `README.md` | Full documentation |
| `QUICKSTART.md` | Setup guide |

## 🎯 Common Tasks

### Change Model Parameters
Edit `configs/max-serve-config.yaml` and restart:
```bash
docker compose restart max-serve
```

### Increase Batch Size
Edit `docker-compose.yaml`, change `--max-batch-size`, restart:
```bash
docker compose up -d max-serve
```

### View Logs
```bash
docker compose logs -f max-serve --tail 100
```

### Check GPU Usage
```bash
watch -n 1 nvidia-smi        # Update every second
```

### Reset Everything
```bash
docker compose down -v       # Remove all data
./init.sh                    # Reinitialize
```

## 📞 Service URLs

| Service | URL | Purpose |
|---------|-----|---------|
| API | http://localhost:8000 | Chat API |
| MAX Serve | http://localhost:8080 | Inference |
| Qdrant | http://localhost:6333 | Vector DB |
| Redis | localhost:6379 | Cache |
| PostgreSQL | localhost:5432 | Database |
| MinIO | http://localhost:9001 | Storage UI |

## 🔐 Default Credentials

### PostgreSQL
- **Database**: ai_platform
- **User**: ai_user
- **Password**: ai_password

### MinIO
- **User**: minioadmin
- **Password**: minioadmin123

⚠️ **Change these in production!**

## 💡 Pro Tips

1. **Warm up**: Send a test request after starting to load the model
2. **Batch requests**: Send multiple concurrent requests for better throughput
3. **Monitor GPU**: Use `nvidia-smi -l 1` to watch GPU utilization
4. **Adjust tokens**: Reduce `max_tokens` for faster responses
5. **Connection pooling**: Reuse HTTP connections in production
6. **Log levels**: Set `LOG_LEVEL=DEBUG` for detailed logs

## 🎓 Learn More

- **Full Guide**: `README.md`
- **Quick Setup**: `QUICKSTART.md`
- **Deployment**: `DEPLOYMENT.md`
- **Architecture**: `ARCHITECTURE.md`
- **Examples**: `examples/README.md`

## ✅ Health Check

```bash
# All should return "healthy"
curl http://localhost:8000/health
curl http://localhost:8080/health
docker compose ps
```

## 🚦 Status Indicators

### Service Status
- ✅ **healthy** - Service is working
- ⚠️ **degraded** - Partial functionality
- ❌ **unhealthy** - Service is down

### Performance
- 🟢 **P95 < 1000ms** - Excellent
- 🟡 **P95 < 2000ms** - Good
- 🔴 **P95 > 2000ms** - Needs attention

---

**Need help?** Check the full documentation in `README.md` or `QUICKSTART.md`
