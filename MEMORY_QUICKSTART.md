# Memory API Quick Start

Get started with the Memory API in 5 minutes.

## Prerequisites

- Docker and Docker Compose
- Python 3.9+
- Running services (Qdrant, Redis, API server)

## 1. Start Services

```bash
# Start all services
docker compose up -d

# Check status
docker compose ps
```

## 2. Verify Installation

```bash
# Check health
curl http://localhost:8000/health

# Check memory stats
curl http://localhost:8000/memory/stats
```

## 3. Add Your First Memory

```bash
curl -X POST http://localhost:8000/memory/add \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "My favorite color is blue"},
      {"role": "assistant", "content": "That'\''s a nice color!"}
    ],
    "user_id": "demo_user"
  }'
```

**Response:**
```json
{
  "status": "success",
  "memory_id": "abc123...",
  "timestamp": "2024-01-15T10:00:00Z",
  "user_id": "demo_user",
  "facts_extracted": 1
}
```

## 4. Search Memories

```bash
curl -X POST http://localhost:8000/memory/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is the user'\''s favorite color?",
    "user_id": "demo_user",
    "limit": 5
  }'
```

**Response:**
```json
{
  "query": "What is the user's favorite color?",
  "results": [
    {
      "memory_id": "abc123...",
      "text": "user: My favorite color is blue\nassistant: That's a nice color!",
      "score": 0.8542,
      "cosine_score": 0.8912,
      "temporal_score": 0.9134,
      "timestamp": "2024-01-15T10:00:00Z"
    }
  ],
  "limit": 5
}
```

## 5. Python Example

```python
import httpx

API_URL = "http://localhost:8000"

# Add memory
response = httpx.post(
    f"{API_URL}/memory/add",
    json={
        "messages": [
            {"role": "user", "content": "I'm learning Python"},
            {"role": "assistant", "content": "Great choice!"}
        ],
        "user_id": "alice"
    }
)
print("Added:", response.json())

# Search memory
response = httpx.post(
    f"{API_URL}/memory/search",
    json={
        "query": "What is Alice learning?",
        "user_id": "alice",
        "limit": 3
    }
)
print("Found:", response.json())
```

## 6. Run Complete Demo

```bash
python examples/memory_example.py
```

## Common Use Cases

### Personal Assistant

```python
# Store user preferences
httpx.post(f"{API_URL}/memory/add", json={
    "messages": [
        {"role": "user", "content": "I prefer emails in the morning"},
        {"role": "assistant", "content": "Noted!"}
    ],
    "user_id": "user123",
    "metadata": {"category": "preferences"}
})

# Recall preferences
httpx.post(f"{API_URL}/memory/search", json={
    "query": "When does the user want emails?",
    "user_id": "user123",
    "filters": {"category": "preferences"}
})
```

### Conversation History

```python
# Store conversation
httpx.post(f"{API_URL}/memory/add", json={
    "messages": [
        {"role": "user", "content": "Let's plan a meeting for tomorrow"},
        {"role": "assistant", "content": "What time works for you?"},
        {"role": "user", "content": "2 PM would be great"}
    ],
    "user_id": "user123",
    "metadata": {"type": "scheduling"}
})

# Recall recent discussions
httpx.post(f"{API_URL}/memory/search", json={
    "query": "What meeting did we plan?",
    "user_id": "user123",
    "use_temporal_decay": True  # Favor recent memories
})
```

### Knowledge Base

```python
# Store facts
httpx.post(f"{API_URL}/memory/add", json={
    "messages": [
        {"role": "user", "content": "The capital of France is Paris"}
    ],
    "metadata": {"type": "fact", "topic": "geography"}
})

# Query facts
httpx.post(f"{API_URL}/memory/search", json={
    "query": "What is the capital of France?",
    "use_temporal_decay": False  # Facts don't decay
})
```

## Next Steps

- Read the [full documentation](MEMORY_README.md)
- Explore [example code](examples/memory_example.py)
- Run [tests](test_memory.py)
- Configure [temporal decay](configs/mem0-config.yaml)

## Troubleshooting

**Services not starting:**
```bash
# Check logs
docker compose logs api-server
docker compose logs qdrant
docker compose logs redis

# Restart services
docker compose restart
```

**Connection errors:**
```bash
# Verify services are running
docker compose ps

# Test connectivity
curl http://localhost:8000/health
redis-cli ping
curl http://localhost:6333/health
```

**Low quality results:**
- Add more context to your queries
- Use metadata filters to narrow search
- Adjust temporal decay settings
- Ensure memories exist for the user_id

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/memory/add` | POST | Add conversation memories |
| `/memory/search` | POST | Search memories with scoring |
| `/memory/forget/{id}` | DELETE | Delete specific memory |
| `/memory/stats` | GET | Get system statistics |

For detailed API documentation, see [MEMORY_README.md](MEMORY_README.md).
