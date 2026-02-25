# API Gateway Quick Start

Quick reference for using the API Gateway service.

## Start the Gateway

```bash
# Option 1: Docker Compose
docker compose up -d gateway

# Option 2: Make
make gateway-start

# Option 3: Quick start script
./start_gateway.sh

# Option 4: Direct run
python gateway_service.py
```

Gateway will be available at: `http://localhost:9000`

## API Keys

Default keys (for development only):
- `sk-test-key-123`
- `sk-admin-key-456`
- `sk-dev-key-789`

Add custom keys:
```bash
export API_KEYS="sk-custom-key-1,sk-custom-key-2"
docker compose up -d gateway
```

## Quick Examples

### 1. Health Check (No Auth)
```bash
curl http://localhost:9000/health
```

### 2. Simple Chat
```bash
curl -X POST http://localhost:9000/v1/chat \
  -H "Authorization: Bearer sk-test-key-123" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "Hello!"}
    ],
    "max_tokens": 100,
    "use_memory": false,
    "use_rag": false
  }'
```

### 3. Chat with Memory
```bash
# Store information
curl -X POST http://localhost:9000/v1/chat \
  -H "Authorization: Bearer sk-test-key-123" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "My name is Alice."}
    ],
    "user_id": "alice-001",
    "store_memory": true,
    "use_memory": false,
    "use_rag": false
  }'

# Retrieve information
curl -X POST http://localhost:9000/v1/chat \
  -H "Authorization: Bearer sk-test-key-123" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "What is my name?"}
    ],
    "user_id": "alice-001",
    "use_memory": true
  }'
```

### 4. Full Integration (Memory + RAG)
```bash
curl -X POST http://localhost:9000/v1/chat \
  -H "Authorization: Bearer sk-test-key-123" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "Help me learn about the system."}
    ],
    "user_id": "user-123",
    "use_memory": true,
    "use_rag": true,
    "store_memory": true,
    "rag_k": 3,
    "memory_limit": 5
  }'
```

## Common Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `messages` | array | required | Conversation messages |
| `user_id` | string | null | User identifier |
| `use_memory` | bool | true | Enable memory retrieval |
| `use_rag` | bool | true | Enable RAG retrieval |
| `store_memory` | bool | true | Store conversation |
| `rag_k` | int | 3 | RAG documents to retrieve |
| `memory_limit` | int | 5 | Memories to retrieve |
| `max_tokens` | int | 2048 | Max tokens to generate |
| `temperature` | float | 0.7 | Sampling temperature |

## Testing

```bash
# Run end-to-end tests
python test_gateway.py

# Or with make
make gateway-test

# Run demo
python examples/gateway_demo.py
# Or
make gateway-demo
```

## Monitoring

```bash
# Check metrics
curl http://localhost:9000/metrics \
  -H "Authorization: Bearer sk-test-key-123"

# View logs
docker compose logs -f gateway

# Check service health
curl http://localhost:9000/health
```

## Endpoints

- `GET /` - API information
- `GET /health` - Health check (no auth)
- `GET /metrics` - Performance metrics (auth required)
- `POST /v1/chat` - Unified chat endpoint (auth required)
- `POST /v1/chat/completions` - OpenAI-compatible (auth required)

## Response Example

```json
{
  "id": "unified-abc123",
  "object": "unified.chat.completion",
  "created": 1705317000,
  "model": "llama-3.3-8b-instruct",
  "choices": [{
    "index": 0,
    "message": {
      "role": "assistant",
      "content": "Hello! How can I help you today?"
    },
    "finish_reason": "stop"
  }],
  "usage": {
    "prompt_tokens": 50,
    "completion_tokens": 20,
    "total_tokens": 70
  },
  "context": {
    "memories": [...],
    "rag_documents": [...]
  },
  "metadata": {
    "memory_retrieval_ms": 45.2,
    "rag_retrieval_ms": 78.5,
    "generation_ms": 1234.6,
    "total_latency_ms": 1358.3
  }
}
```

## Performance

**Target:** < 3 seconds end-to-end latency

**Typical breakdown:**
- Memory: 50-100ms
- RAG: 80-150ms
- Generation: 1000-2000ms
- **Total: < 3000ms** ✓

## Troubleshooting

**Can't connect to gateway:**
```bash
# Check if running
docker compose ps gateway

# Check logs
docker compose logs gateway

# Restart
docker compose restart gateway
```

**Authentication fails:**
- Check API key format: `Bearer sk-test-key-123`
- Verify key is valid
- Check Authorization header

**High latency:**
- Reduce `max_tokens`
- Lower `rag_k` and `memory_limit`
- Disable unused features with `use_memory=false` or `use_rag=false`

## More Information

- Full documentation: `GATEWAY_README.md`
- Implementation details: `GATEWAY_IMPLEMENTATION.md`
- Postman collection: `postman_collection.json`
- Interactive docs: http://localhost:9000/docs
