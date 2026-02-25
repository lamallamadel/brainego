# Agent Router - Multi-Model Intelligent Routing

The Agent Router provides intelligent request routing across multiple specialized models with automatic intent classification, fallback chains, and comprehensive Prometheus metrics.

## Overview

The system deploys three specialized models on MAX Serve:

1. **Llama 3.3 8B Instruct** - General purpose conversational model
2. **Qwen 2.5 Coder 7B Instruct** - Specialized for coding and programming tasks
3. **DeepSeek R1 7B** - Advanced reasoning and problem-solving model

Requests are automatically routed to the most appropriate model based on intent classification of the user's message content.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                       API Server (FastAPI)                   │
│                      Port 8000 (API)                         │
│                      Port 8001 (Metrics)                     │
└────────────────────────┬────────────────────────────────────┘
                         │
                ┌────────▼────────┐
                │  Agent Router   │
                │ - Intent Class. │
                │ - Model Select. │
                │ - Fallback      │
                └────────┬────────┘
                         │
         ┌───────────────┼───────────────┐
         │               │               │
┌────────▼────────┐ ┌───▼─────────┐ ┌──▼──────────────┐
│ MAX Serve Llama │ │ MAX Serve   │ │ MAX Serve       │
│ Port: 8080      │ │ Qwen Coder  │ │ DeepSeek R1     │
│ Intent: general │ │ Port: 8081  │ │ Port: 8082      │
│                 │ │ Intent: code│ │ Intent: reason  │
└─────────────────┘ └─────────────┘ └─────────────────┘
```

## Intent Classification

The router analyzes message content and classifies intent into three categories:

### Code Intent
**Triggers:** Keywords like `code`, `programming`, `function`, `debug`, `syntax`, `python`, `javascript`, etc.

**Routes to:** Qwen 2.5 Coder 7B

**Example:**
```python
{
    "messages": [
        {"role": "user", "content": "Write a Python function for binary search"}
    ]
}
# → Routes to Qwen 2.5 Coder 7B
```

### Reasoning Intent
**Triggers:** Keywords like `reasoning`, `analyze`, `math`, `prove`, `calculate`, `logic`, `explain why`, etc.

**Routes to:** DeepSeek R1 7B

**Example:**
```python
{
    "messages": [
        {"role": "user", "content": "Analyze this problem and explain your reasoning step by step"}
    ]
}
# → Routes to DeepSeek R1 7B
```

### General Intent
**Default routing** for conversational queries, Q&A, and general tasks.

**Routes to:** Llama 3.3 8B

**Example:**
```python
{
    "messages": [
        {"role": "user", "content": "What are some healthy breakfast ideas?"}
    ]
}
# → Routes to Llama 3.3 8B
```

## Fallback Chains

If the primary model fails, the router automatically tries fallback models:

- **Qwen Coder** → Llama → DeepSeek R1
- **DeepSeek R1** → Llama → Qwen Coder
- **Llama** → Qwen Coder → DeepSeek R1

Each model is tried with configurable retries and exponential backoff.

## Configuration

Edit `configs/agent-router.yaml` to customize:

```yaml
# Model endpoints
models:
  llama:
    endpoint: "http://max-serve-llama:8080"
    max_tokens: 2048
    temperature: 0.7
  
  qwen-coder:
    endpoint: "http://max-serve-qwen:8081"
    max_tokens: 4096
    temperature: 0.2
  
  deepseek-r1:
    endpoint: "http://max-serve-deepseek:8082"
    max_tokens: 4096
    temperature: 0.3

# Intent classification
intent_classifier:
  code_keywords: [code, programming, function, ...]
  reasoning_keywords: [reasoning, analyze, math, ...]
  thresholds:
    high: 0.7
    medium: 0.4
    low: 0.2

# Routing strategy
routing:
  primary_model:
    code: "qwen-coder"
    reasoning: "deepseek-r1"
    general: "llama"
  
  fallback_chains:
    qwen-coder: ["llama", "deepseek-r1"]
    deepseek-r1: ["llama", "qwen-coder"]
    llama: ["qwen-coder", "deepseek-r1"]

# Metrics
metrics:
  enabled: true
  prometheus_port: 8001
```

## Prometheus Metrics

The router exposes comprehensive metrics on port 8001:

### Request Metrics
- `agent_router_requests_total{model, intent, status}` - Total requests per model
- `agent_router_model_requests_total{model}` - Requests to each model
- `agent_router_fallback_requests_total{from_model, to_model}` - Fallback occurrences
- `agent_router_fallback_rate{model}` - Current fallback rate per model

### Latency Metrics
- `agent_router_latency_seconds{model, intent}` - Request latency histogram
- `agent_router_classification_latency_seconds` - Intent classification time

### Intent Metrics
- `agent_router_intent_classification_total{intent, confidence}` - Intent classifications

### Health Metrics
- `agent_router_model_health{model}` - Model health status (1=healthy, 0=unhealthy)
- `agent_router_errors_total{model, error_type}` - Error counts

### View Metrics
```bash
curl http://localhost:8001/metrics
```

## API Endpoints

### Chat Completions (with routing)
```bash
POST /v1/chat/completions
```

Request body includes routing metadata in response:
```json
{
  "choices": [...],
  "usage": {...},
  "x-routing-metadata": {
    "model_id": "qwen-coder",
    "model_name": "qwen2.5-coder-7b-instruct",
    "intent": "code",
    "confidence": 0.85,
    "fallback_used": false,
    "total_time_seconds": 1.234
  }
}
```

### List Models
```bash
GET /v1/models
```

Returns all available models with health status.

### Router Info
```bash
GET /router/info
```

Returns routing configuration and model status:
```json
{
  "models": {...},
  "routing_strategy": {
    "code": "qwen-coder",
    "reasoning": "deepseek-r1",
    "general": "llama"
  },
  "fallback_chains": {...},
  "health_check": {...}
}
```

### Health Check
```bash
GET /health
```

Returns health status of all models:
```json
{
  "status": "healthy",
  "models": {
    "llama": {"status": "healthy", "name": "llama-3.3-8b-instruct"},
    "qwen-coder": {"status": "healthy", "name": "qwen2.5-coder-7b-instruct"},
    "deepseek-r1": {"status": "healthy", "name": "deepseek-r1-distill-qwen-7b"}
  }
}
```

## Setup and Deployment

### 1. Download Models
```bash
chmod +x download_model.sh
./download_model.sh
```

This downloads all three models:
- `llama-3.3-8b-instruct-q4_k_m.gguf` (~4.5 GB)
- `qwen2.5-coder-7b-instruct-q4_k_m.gguf` (~4.5 GB)
- `deepseek-r1-distill-qwen-7b-q4_k_m.gguf` (~4.5 GB)

### 2. Start Services
```bash
docker compose up -d
```

This starts:
- 3 MAX Serve instances (ports 8080, 8081, 8082)
- API Server with Agent Router (port 8000)
- Prometheus metrics endpoint (port 8001)
- Support services (Qdrant, Redis, PostgreSQL, etc.)

### 3. Wait for Models to Load
```bash
docker compose logs -f max-serve-llama
docker compose logs -f max-serve-qwen
docker compose logs -f max-serve-deepseek
```

Model loading typically takes 30-60 seconds per model.

### 4. Test the Router
```bash
python3 examples/test_agent_router.py
```

This runs a comprehensive test suite covering:
- Health checks
- Intent classification
- Model selection
- Fallback behavior
- Prometheus metrics

## Usage Examples

### Python SDK
```python
import httpx

API_URL = "http://localhost:8000"

# Code query (routes to Qwen Coder)
response = httpx.post(
    f"{API_URL}/v1/chat/completions",
    json={
        "messages": [
            {"role": "user", "content": "Write a Python function for quicksort"}
        ],
        "max_tokens": 500
    }
)

result = response.json()
print(f"Model used: {result['x-routing-metadata']['model_name']}")
print(f"Intent: {result['x-routing-metadata']['intent']}")
print(f"Response: {result['choices'][0]['message']['content']}")
```

### cURL
```bash
# Code query
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "Debug this Python code: def sum(a,b) return a+b"}
    ]
  }'

# Reasoning query
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "Prove that the sum of two even numbers is even"}
    ]
  }'

# General query
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "What is the capital of France?"}
    ]
  }'
```

### OpenAI SDK (Compatible)
```python
from openai import OpenAI

client = OpenAI(
    api_key="dummy",  # Not required
    base_url="http://localhost:8000/v1"
)

response = client.chat.completions.create(
    model="auto",
    messages=[
        {"role": "user", "content": "Implement a binary tree in Java"}
    ]
)

print(response.choices[0].message.content)
```

## Monitoring

### Prometheus Metrics Dashboard
```bash
# View raw metrics
curl http://localhost:8001/metrics

# Key metrics to monitor:
# - agent_router_requests_total
# - agent_router_latency_seconds
# - agent_router_fallback_requests_total
# - agent_router_model_health
```

### Grafana Dashboard
Import `configs/grafana-agent-router-dashboard.json` for a pre-built dashboard showing:
- Request rate per model
- P50/P95/P99 latencies
- Fallback rates
- Intent distribution
- Model health status

### Logs
```bash
# API Server logs
docker compose logs -f api-server

# Model logs
docker compose logs -f max-serve-llama max-serve-qwen max-serve-deepseek
```

## Performance Tuning

### Adjust Batching
Edit docker-compose.yaml for each MAX Serve instance:
```yaml
command: >
  max-serve
  --max-batch-size 32    # Concurrent requests
  --max-waiting-time 10  # Batch window (ms)
```

### Adjust Timeouts
Edit `configs/agent-router.yaml`:
```yaml
routing:
  timeouts:
    request: 300        # Request timeout (seconds)
    health_check: 5     # Health check timeout
  
  retry:
    max_attempts: 2
    backoff_factor: 1.5
```

### GPU Memory Optimization
For limited GPU memory, load models sequentially:
```yaml
# docker-compose.yaml
environment:
  - CUDA_VISIBLE_DEVICES=0  # Share GPU across models
```

## Troubleshooting

### Model Not Healthy
```bash
# Check model logs
docker compose logs max-serve-qwen

# Restart model
docker compose restart max-serve-qwen

# Check model health
curl http://localhost:8081/health
```

### Fallback Chain Exhausted
All models are unavailable. Check:
1. GPU memory (`nvidia-smi`)
2. Model health endpoints
3. MAX Serve container logs
4. Network connectivity

### High Latency
Monitor Prometheus metrics:
```bash
curl http://localhost:8001/metrics | grep latency
```

Consider:
- Increasing `max-batch-size`
- Reducing `max-waiting-time`
- Adding more GPU memory
- Using smaller models

## Extending the Router

### Add New Intent
Edit `configs/agent-router.yaml`:
```yaml
intent_classifier:
  new_intent_keywords:
    - keyword1
    - keyword2

routing:
  primary_model:
    new_intent: "model_id"
```

Update `agent_router.py` to add the intent enum.

### Add New Model
1. Add model entry in `configs/agent-router.yaml`
2. Add MAX Serve instance in `docker-compose.yaml`
3. Download model file
4. Restart services

### Custom Classification Logic
Subclass `IntentClassifier` in `agent_router.py` and implement custom `classify()` method using ML models, embeddings, or LLM-based classification.

## Best Practices

1. **Monitor fallback rates** - High fallback indicates model health issues
2. **Set appropriate timeouts** - Balance latency vs. success rate
3. **Use health checks** - Enable background health monitoring
4. **Monitor Prometheus metrics** - Track performance trends
5. **Test intent classification** - Verify queries route to expected models
6. **Configure GPU memory** - Ensure sufficient memory for all models
7. **Use batching** - Maximize throughput for concurrent requests

## References

- [Llama 3.3 Documentation](https://huggingface.co/meta-llama/Llama-3.3-8B-Instruct)
- [Qwen 2.5 Coder](https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct)
- [DeepSeek R1](https://huggingface.co/deepseek-ai/DeepSeek-R1-Distill-Qwen-7B)
- [Prometheus Metrics](https://prometheus.io/docs/introduction/overview/)
- [MAX Serve Documentation](https://docs.modular.com/max/serve)
