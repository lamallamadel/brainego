# API Gateway Service

Unified API Gateway for AI Platform with Memory, RAG, and Inference integration.

## Overview

The API Gateway provides a single entry point for all AI Platform services, featuring:

- **API Key Authentication**: Secure access control with Bearer token authentication
- **Unified Chat Endpoint**: `/v1/chat` integrates Memory + RAG + Inference in a single request
- **OpenAI-Compatible**: Standard `/v1/chat/completions` endpoint for easy integration
- **Performance Monitoring**: Built-in metrics and latency tracking
- **< 3s Latency Target**: Optimized for fast end-to-end response times

## Quick Start

### 1. Start the Gateway Service

```bash
# Using Docker Compose
docker compose up -d gateway

# Or run directly
python gateway_service.py
```

The gateway will be available at `http://localhost:9000`

### 2. Set API Key

Use one of the default API keys or set custom keys via environment variable:

**Default API Keys:**
- `sk-test-key-123` (test-key, standard tier)
- `sk-admin-key-456` (admin-key, admin tier)
- `sk-dev-key-789` (dev-key, developer tier)

**Custom API Keys:**
```bash
export API_KEYS="sk-custom-key-1,sk-custom-key-2"
docker compose up -d gateway
```

### 3. Make Your First Request

```bash
curl -X POST http://localhost:9000/v1/chat \
  -H "Authorization: Bearer sk-test-key-123" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "Hello!"}
    ],
    "max_tokens": 100
  }'
```

## API Endpoints

### Health & Monitoring

#### `GET /health`
Health check for all services (no authentication required).

```bash
curl http://localhost:9000/health
```

Response:
```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:00.000Z",
  "services": {
    "max_serve": "healthy",
    "qdrant": "healthy",
    "redis": "healthy"
  }
}
```

#### `GET /metrics`
Performance metrics (requires authentication).

```bash
curl http://localhost:9000/metrics \
  -H "Authorization: Bearer sk-test-key-123"
```

Response:
```json
{
  "metrics": {
    "request_count": 150,
    "errors": 2,
    "auth_failures": 5,
    "avg_latency_ms": 1234.56,
    "p50_latency_ms": 1100.00,
    "p95_latency_ms": 2500.00,
    "p99_latency_ms": 2900.00
  },
  "timestamp": "2024-01-15T10:30:00.000Z"
}
```

### Chat Completions

#### `POST /v1/chat/completions`
OpenAI-compatible chat completions endpoint.

```bash
curl -X POST http://localhost:9000/v1/chat/completions \
  -H "Authorization: Bearer sk-test-key-123" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama-3.3-8b-instruct",
    "messages": [
      {"role": "system", "content": "You are a helpful assistant."},
      {"role": "user", "content": "What is the capital of France?"}
    ],
    "max_tokens": 100,
    "temperature": 0.7
  }'
```

### Unified Chat (Memory + RAG + Inference)

#### `POST /v1/chat`
Unified endpoint integrating memory, RAG, and inference.

**Features:**
- **Memory Retrieval**: Retrieve relevant user memories
- **RAG Context**: Fetch documents from knowledge base
- **Augmented Generation**: Generate response with full context
- **Memory Storage**: Store conversation for future retrieval

**Request:**
```bash
curl -X POST http://localhost:9000/v1/chat \
  -H "Authorization: Bearer sk-test-key-123" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama-3.3-8b-instruct",
    "messages": [
      {"role": "user", "content": "What do you know about me?"}
    ],
    "user_id": "alice-001",
    "use_memory": true,
    "use_rag": true,
    "store_memory": true,
    "rag_k": 3,
    "memory_limit": 5,
    "max_tokens": 200,
    "temperature": 0.7
  }'
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | string | "llama-3.3-8b-instruct" | Model to use |
| `messages` | array | required | Conversation messages |
| `user_id` | string | null | User identifier for personalized memory |
| `use_memory` | boolean | true | Enable memory retrieval |
| `use_rag` | boolean | true | Enable RAG context retrieval |
| `store_memory` | boolean | true | Store conversation in memory |
| `rag_k` | integer | 3 | Number of RAG documents to retrieve (1-10) |
| `memory_limit` | integer | 5 | Number of memories to retrieve (1-20) |
| `max_tokens` | integer | 2048 | Maximum tokens to generate |
| `temperature` | float | 0.7 | Sampling temperature (0.0-2.0) |
| `top_p` | float | 0.9 | Nucleus sampling (0.0-1.0) |

**Response:**
```json
{
  "id": "unified-abc123...",
  "object": "unified.chat.completion",
  "created": 1705317000,
  "model": "llama-3.3-8b-instruct",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Based on our previous conversations..."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 250,
    "completion_tokens": 120,
    "total_tokens": 370
  },
  "context": {
    "memories": [
      {
        "text": "User's favorite color is blue",
        "score": 0.92,
        "timestamp": "2024-01-15T09:00:00Z"
      }
    ],
    "rag_documents": [
      {
        "text": "Documentation about...",
        "score": 0.87,
        "metadata": {"source": "docs"}
      }
    ]
  },
  "metadata": {
    "memory_retrieval_ms": 45.2,
    "rag_retrieval_ms": 78.5,
    "generation_ms": 1234.6,
    "total_latency_ms": 1358.3,
    "memories_retrieved": 3,
    "rag_documents_retrieved": 3,
    "memory_stored": true,
    "memory_id": "mem-xyz789..."
  }
}
```

## Authentication

All endpoints except `/health` and `/` require authentication using Bearer tokens.

### Adding Authorization Header

**cURL:**
```bash
curl -H "Authorization: Bearer sk-test-key-123" ...
```

**Python (requests):**
```python
import requests

headers = {
    "Authorization": "Bearer sk-test-key-123",
    "Content-Type": "application/json"
}

response = requests.post(
    "http://localhost:9000/v1/chat",
    headers=headers,
    json={...}
)
```

**JavaScript (fetch):**
```javascript
const response = await fetch('http://localhost:9000/v1/chat', {
  method: 'POST',
  headers: {
    'Authorization': 'Bearer sk-test-key-123',
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({...})
});
```

### Error Responses

**401 Unauthorized**: Invalid or expired API key
```json
{
  "detail": "Invalid API key",
  "type": "authentication_error"
}
```

**403 Forbidden**: Missing authentication
```json
{
  "detail": "Not authenticated"
}
```

## Testing

### Python Test Suite

Run comprehensive end-to-end tests:

```bash
python test_gateway.py
```

Tests include:
- Health check
- Authentication (valid, invalid, missing)
- Chat completions
- Unified chat (basic, memory, RAG, full integration)
- Performance targets (<3s latency)

### Postman Collection

Import the Postman collection for interactive testing:

```bash
# Import postman_collection.json into Postman
```

The collection includes:
- Pre-configured requests for all endpoints
- Authentication examples
- Conversation scenarios
- Performance tests with assertions
- Environment variables for easy configuration

### Manual Testing

**Test 1: Basic Chat (No Memory/RAG)**
```bash
curl -X POST http://localhost:9000/v1/chat \
  -H "Authorization: Bearer sk-test-key-123" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Hello!"}],
    "use_memory": false,
    "use_rag": false,
    "max_tokens": 50
  }'
```

**Test 2: Store Memory**
```bash
curl -X POST http://localhost:9000/v1/chat \
  -H "Authorization: Bearer sk-test-key-123" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "My name is Alice."}],
    "user_id": "alice-001",
    "store_memory": true,
    "use_memory": false,
    "use_rag": false
  }'
```

**Test 3: Retrieve Memory**
```bash
curl -X POST http://localhost:9000/v1/chat \
  -H "Authorization: Bearer sk-test-key-123" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "What is my name?"}],
    "user_id": "alice-001",
    "use_memory": true,
    "use_rag": false
  }'
```

## Performance

### Latency Target

The unified chat endpoint targets **< 3 seconds** end-to-end latency:

- Memory retrieval: ~50-100ms
- RAG retrieval: ~80-150ms
- Generation: ~1000-2000ms
- Total: < 3000ms

### Optimization Tips

1. **Limit Context Size**: Use smaller `rag_k` and `memory_limit` values for faster retrieval
2. **Adjust Max Tokens**: Lower `max_tokens` for faster generation
3. **Disable Unused Features**: Set `use_memory=false` or `use_rag=false` if not needed
4. **Concurrent Requests**: Gateway supports concurrent requests with batching

### Monitoring Performance

Check metrics endpoint for latency statistics:

```bash
curl http://localhost:9000/metrics \
  -H "Authorization: Bearer sk-test-key-123"
```

Response includes:
- Average latency
- P50/P95/P99 latencies
- Request count
- Error rate

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     Client Layer                        │
│  (HTTP/REST, Bearer Token Authentication)              │
└──────────────────┬──────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────┐
│              API Gateway (FastAPI)                      │
│  - Authentication & Authorization                       │
│  - Request Routing                                      │
│  - Performance Monitoring                               │
│  Port: 9000                                             │
└──┬──────────────┬──────────────┬───────────────────────┘
   │              │              │
   │              │              │
┌──▼──────┐  ┌───▼──────┐  ┌───▼──────────┐
│ MAX     │  │ Memory   │  │ RAG          │
│ Serve   │  │ Service  │  │ Service      │
│ :8080   │  │ (Mem0)   │  │ (Qdrant)     │
└─────────┘  └──────────┘  └──────────────┘
```

### Request Flow

1. **Client** sends request with Bearer token
2. **Gateway** validates API key
3. **Parallel Retrieval**: Memory and RAG contexts fetched concurrently
4. **Augmented Prompt**: Context integrated into system message
5. **Generation**: MAX Serve generates response
6. **Memory Storage**: Conversation stored (if enabled)
7. **Response**: Complete response with context and metadata returned

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_SERVE_URL` | http://localhost:8080 | MAX Serve endpoint |
| `QDRANT_HOST` | localhost | Qdrant host |
| `QDRANT_PORT` | 6333 | Qdrant port |
| `QDRANT_COLLECTION` | documents | Default collection name |
| `REDIS_HOST` | localhost | Redis host |
| `REDIS_PORT` | 6379 | Redis port |
| `REDIS_DB` | 0 | Redis database number |
| `API_KEYS` | (empty) | Comma-separated additional API keys |

### Docker Compose

```yaml
gateway:
  build:
    context: .
    dockerfile: Dockerfile.gateway
  container_name: gateway
  ports:
    - "9000:9000"
  environment:
    - MAX_SERVE_URL=http://max-serve:8080
    - QDRANT_HOST=qdrant
    - QDRANT_PORT=6333
    - REDIS_HOST=redis
    - REDIS_PORT=6379
    - API_KEYS=${API_KEYS:-}
  depends_on:
    - max-serve
    - qdrant
    - redis
```

## Security Best Practices

1. **Change Default API Keys**: Never use default keys in production
2. **Use HTTPS**: Deploy behind reverse proxy with TLS
3. **Rotate Keys**: Regularly rotate API keys
4. **Rate Limiting**: Implement rate limiting per API key
5. **Monitor Access**: Track authentication failures in metrics
6. **Secure Storage**: Store API keys in environment variables or secrets manager

## Troubleshooting

### Gateway Won't Start

Check service dependencies:
```bash
docker compose ps
curl http://localhost:8080/health  # MAX Serve
curl http://localhost:6333/health  # Qdrant
redis-cli ping                      # Redis
```

### Authentication Fails

Verify API key format:
```bash
# Correct format
Authorization: Bearer sk-test-key-123

# Common mistakes
Authorization: sk-test-key-123        # Missing "Bearer"
Authorization: Bearer sk-test-key-123  # Extra space
```

### High Latency

Check component latencies in response metadata:
```json
{
  "metadata": {
    "memory_retrieval_ms": 45.2,    // Should be <100ms
    "rag_retrieval_ms": 78.5,       // Should be <200ms
    "generation_ms": 2234.6,        // Depends on max_tokens
    "total_latency_ms": 2358.3      // Target: <3000ms
  }
}
```

If generation is slow:
- Reduce `max_tokens`
- Check MAX Serve batch utilization
- Verify GPU is available

### Memory/RAG Not Working

Verify services are initialized:
```bash
# Check Qdrant collections
curl http://localhost:6333/collections

# Check Redis
redis-cli keys "memory:*"
```

## Examples

See `test_gateway.py` and `postman_collection.json` for comprehensive examples.

## API Reference

Full API documentation available at:
- Interactive docs: http://localhost:9000/docs
- OpenAPI spec: http://localhost:9000/openapi.json

## License

See main project LICENSE file.
