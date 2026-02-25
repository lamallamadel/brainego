# Quick Start - Agent Router

Get started with the multi-model Agent Router in 5 minutes.

## Prerequisites

- Docker with GPU support
- NVIDIA GPU with 16GB+ VRAM (recommended for running all 3 models)
- Python 3.8+

## Setup (5 minutes)

### 1. Download Models
```bash
chmod +x download_model.sh
./download_model.sh
```

Downloads:
- Llama 3.3 8B Instruct (~4.5 GB)
- Qwen 2.5 Coder 7B (~4.5 GB)
- DeepSeek R1 7B (~4.5 GB)

### 2. Start Services
```bash
docker compose up -d
```

### 3. Wait for Models
```bash
# Check if all models are ready
watch -n 5 'docker compose ps'

# Or check logs
docker compose logs -f max-serve-llama max-serve-qwen max-serve-deepseek
```

Wait until all three MAX Serve instances show "healthy" status (~2-3 minutes).

### 4. Test
```bash
# Quick health check
curl http://localhost:8000/health

# Run comprehensive tests
python3 examples/test_agent_router.py
```

## Usage

### Code Query (→ Qwen Coder)
```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "Write a Python function for binary search"}
    ]
  }'
```

### Reasoning Query (→ DeepSeek R1)
```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "Prove that sqrt(2) is irrational"}
    ]
  }'
```

### General Query (→ Llama 3.3)
```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "What are good recipes for dinner?"}
    ]
  }'
```

## Monitoring

### Check Routing Metadata
Every response includes which model was used:
```json
{
  "x-routing-metadata": {
    "model_id": "qwen-coder",
    "intent": "code",
    "confidence": 0.85,
    "fallback_used": false
  }
}
```

### View Prometheus Metrics
```bash
curl http://localhost:8001/metrics
```

Key metrics:
- `agent_router_requests_total` - Requests per model
- `agent_router_latency_seconds` - Response times
- `agent_router_fallback_requests_total` - Fallback events
- `agent_router_model_health` - Model health (1=healthy)

### Check Model Status
```bash
curl http://localhost:8000/router/info
```

## Common Issues

### Out of Memory
**Problem:** GPU runs out of memory with 3 models

**Solution:** Load models on different GPUs or reduce batch size:
```yaml
# docker-compose.yaml
max-serve-llama:
  environment:
    - CUDA_VISIBLE_DEVICES=0

max-serve-qwen:
  environment:
    - CUDA_VISIBLE_DEVICES=1
```

### Model Unhealthy
**Problem:** Model shows as unhealthy

**Solution:**
```bash
# Restart the model
docker compose restart max-serve-qwen

# Check logs
docker compose logs max-serve-qwen
```

### Wrong Model Selected
**Problem:** Query routes to unexpected model

**Solution:** Check and adjust keywords in `configs/agent-router.yaml`:
```yaml
intent_classifier:
  code_keywords:
    - code
    - programming
    # Add more keywords
```

## Next Steps

- Read [AGENT_ROUTER.md](AGENT_ROUTER.md) for detailed documentation
- Configure routing in `configs/agent-router.yaml`
- Set up Grafana dashboard for metrics visualization
- Integrate with your application using OpenAI SDK

## Support

- Check logs: `docker compose logs -f api-server`
- View metrics: `http://localhost:8001/metrics`
- Test routing: `python3 examples/test_agent_router.py`
