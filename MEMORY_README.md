# Memory API with Mem0

This document describes the Memory API implementation using Mem0 with Qdrant backend and Redis for key-value storage.

## Overview

The Memory API provides automatic fact extraction from conversations and intelligent memory retrieval with cosine similarity + temporal decay scoring. It's designed to enable AI applications to remember and recall information from past interactions.

### Key Features

- **Automatic Fact Extraction**: Uses Mem0 to automatically extract facts from conversation messages
- **Vector-based Storage**: Stores memories as embeddings in Qdrant for similarity search
- **Key-Value Metadata**: Uses Redis for fast metadata access and caching
- **Temporal Decay Scoring**: Combines cosine similarity with recency bias
- **User-specific Memories**: Supports filtering by user ID for personalized recall
- **Flexible Search**: Metadata filters and configurable result limits

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Memory API Layer                      │
│            (FastAPI endpoints + Pydantic)               │
└──────────────────┬──────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────┐
│              Memory Service                             │
│  - Mem0 integration (fact extraction)                   │
│  - Embedding generation (sentence-transformers)         │
│  - Temporal decay calculation                           │
└────┬─────────────────────────────────────────┬──────────┘
     │                                         │
┌────▼────────────┐                  ┌────────▼─────────┐
│  Qdrant DB      │                  │  Redis Cache     │
│  - Vectors      │                  │  - Metadata      │
│  - Similarity   │                  │  - Timestamps    │
│  - Cosine dist  │                  │  - User IDs      │
└─────────────────┘                  └──────────────────┘
```

## API Endpoints

### POST /memory/add

Add memories from conversation messages with automatic fact extraction.

**Request:**
```json
{
  "messages": [
    {"role": "user", "content": "I love Python programming"},
    {"role": "assistant", "content": "That's great!"}
  ],
  "user_id": "alice",
  "metadata": {
    "topic": "programming",
    "context": "hobby"
  }
}
```

**Response:**
```json
{
  "status": "success",
  "memory_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2024-01-15T10:30:00.000Z",
  "user_id": "alice",
  "facts_extracted": 2
}
```

### POST /memory/search

Search memories with cosine similarity + temporal decay scoring.

**Request:**
```json
{
  "query": "What programming languages does Alice like?",
  "user_id": "alice",
  "limit": 5,
  "filters": {"topic": "programming"},
  "use_temporal_decay": true
}
```

**Response:**
```json
{
  "query": "What programming languages does Alice like?",
  "results": [
    {
      "memory_id": "550e8400-e29b-41d4-a716-446655440000",
      "text": "user: I love Python programming\nassistant: That's great!",
      "score": 0.8542,
      "cosine_score": 0.8912,
      "temporal_score": 0.9134,
      "timestamp": "2024-01-15T10:30:00.000Z",
      "user_id": "alice",
      "metadata": {"topic": "programming"},
      "messages": [...]
    }
  ],
  "limit": 5
}
```

### DELETE /memory/forget/{memory_id}

Delete a memory by ID.

**Response:**
```json
{
  "status": "success",
  "memory_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "Memory deleted successfully"
}
```

### GET /memory/stats

Get memory system statistics.

**Response:**
```json
{
  "collection_name": "memories",
  "qdrant_points": 1234,
  "redis_memories": 1234,
  "vector_dimension": 384,
  "distance_metric": "COSINE"
}
```

## Temporal Decay Scoring

The memory search combines two scoring mechanisms:

1. **Cosine Similarity** (70% weight): Measures semantic similarity between query and stored memories
2. **Temporal Score** (30% weight): Favors more recent memories using exponential decay

### Formula

```
combined_score = 0.7 × cosine_score + 0.3 × temporal_score

where:
  temporal_score = exp(-decay_factor × age_in_days)
  decay_factor = 0.1 (configurable)
```

### Examples

| Age | Temporal Score | Effect |
|-----|----------------|--------|
| 1 day | 0.9048 | Minimal decay |
| 1 week | 0.4966 | Moderate decay |
| 1 month | 0.0498 | Strong decay |
| 3 months | 0.0001 | Near zero |

This ensures recent memories are weighted higher even if slightly less semantically similar.

## Configuration

The Memory Service can be configured via environment variables:

```bash
# Qdrant Configuration
QDRANT_HOST=localhost
QDRANT_PORT=6333

# Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
```

Additional configuration in code:

```python
memory_service = MemoryService(
    qdrant_host="localhost",
    qdrant_port=6333,
    redis_host="localhost",
    redis_port=6379,
    memory_collection="memories",
    embedding_model="sentence-transformers/all-MiniLM-L6-v2",
    temporal_decay_factor=0.1  # Higher = faster decay
)
```

## Usage Examples

### Python Client

See `examples/memory_example.py` for a complete demo:

```python
import httpx

API_URL = "http://localhost:8000"

# Add a memory
messages = [
    {"role": "user", "content": "I'm learning machine learning"},
    {"role": "assistant", "content": "That's exciting!"}
]

response = httpx.post(
    f"{API_URL}/memory/add",
    json={
        "messages": messages,
        "user_id": "alice",
        "metadata": {"topic": "ML"}
    }
)
print(response.json())

# Search memories
response = httpx.post(
    f"{API_URL}/memory/search",
    json={
        "query": "What is Alice learning?",
        "user_id": "alice",
        "limit": 5
    }
)
print(response.json())
```

### cURL Examples

```bash
# Add memory
curl -X POST http://localhost:8000/memory/add \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "I live in San Francisco"},
      {"role": "assistant", "content": "Great city!"}
    ],
    "user_id": "bob"
  }'

# Search memories
curl -X POST http://localhost:8000/memory/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Where does Bob live?",
    "user_id": "bob",
    "limit": 5
  }'

# Delete memory
curl -X DELETE http://localhost:8000/memory/forget/550e8400-e29b-41d4-a716-446655440000

# Get statistics
curl http://localhost:8000/memory/stats
```

## Testing

Run the test suite:

```bash
python test_memory.py
```

Run the example demo:

```bash
python examples/memory_example.py
```

## Implementation Details

### Mem0 Integration

The service integrates Mem0 for automatic fact extraction. When you add a conversation:

1. Mem0 analyzes the conversation messages
2. Extracts key facts and information
3. Creates embeddings for each fact
4. Stores them in Qdrant with metadata

If Mem0 initialization fails (e.g., no OpenAI API key), the service falls back to a simpler mode that stores the entire conversation as a single memory.

### Fallback Mode

The Memory Service has robust fallback mechanisms:

- **Mem0 unavailable**: Direct embedding creation with sentence-transformers
- **Fact extraction fails**: Stores entire conversation as one memory
- **Redis failure**: Continues with Qdrant-only mode (degraded)

### Data Storage

**Qdrant (Vector Store):**
- Memory embeddings (384-dimensional vectors)
- Payload: user_id, text, timestamp, metadata, messages
- Cosine distance metric for similarity search

**Redis (Key-Value Store):**
- Key format: `memory:{memory_id}`
- Stores: user_id, timestamp, messages, metadata, mem0_result
- 30-day TTL on entries

### Dependencies

- `mem0ai==0.0.30`: Core memory framework
- `redis==5.0.1`: Redis client
- `qdrant-client==1.7.0`: Vector database
- `sentence-transformers==2.2.2`: Embedding model
- `numpy==1.24.3`: Numerical operations

## Best Practices

### When to Add Memories

- After each significant user interaction
- When user provides personal information
- After task completion or goal achievement
- During context switches in conversation

### Search Strategies

**Recent context:**
```python
# Use temporal decay for recent events
{"query": "What did we discuss?", "use_temporal_decay": True}
```

**Historical facts:**
```python
# Disable temporal decay for long-term facts
{"query": "What is user's job?", "use_temporal_decay": False}
```

**Filtered search:**
```python
# Use metadata filters for specific topics
{
  "query": "user preferences",
  "filters": {"category": "preferences"},
  "user_id": "alice"
}
```

### Memory Hygiene

- Regularly review and delete outdated memories
- Use appropriate `temporal_decay_factor` for your use case
- Monitor Redis memory usage with `memory/stats`
- Consider implementing retention policies

## Performance

### Benchmarks

- Add memory: ~200-500ms (with Mem0 fact extraction)
- Search (5 results): ~50-100ms
- Delete memory: ~20-30ms
- Stats query: ~10-20ms

### Scaling Considerations

- Qdrant can handle millions of vectors efficiently
- Redis memory usage: ~1-2KB per memory entry
- Consider sharding by user_id for large deployments
- Use Qdrant's filtering to reduce search space

## Troubleshooting

### Common Issues

**Mem0 initialization fails:**
- Check if OpenAI API key is set (if using LLM mode)
- Service will fall back to embedding-only mode
- Check logs for specific error messages

**Redis connection errors:**
- Verify Redis is running: `redis-cli ping`
- Check REDIS_HOST and REDIS_PORT configuration
- Ensure network connectivity to Redis

**Low search quality:**
- Increase `limit` parameter for more results
- Adjust `temporal_decay_factor` (0.05-0.2 range)
- Verify embedding model is loaded correctly
- Check if memories exist for the user_id

**High latency:**
- Check Qdrant collection size
- Consider adding metadata filters to reduce search space
- Monitor Redis memory usage
- Review network latency to services

## Future Enhancements

Potential improvements for future versions:

- [ ] Batch memory operations
- [ ] Memory consolidation/compression
- [ ] Multi-modal memories (images, audio)
- [ ] Memory importance scoring
- [ ] Automatic memory pruning
- [ ] Memory export/import
- [ ] Advanced filtering with Qdrant payload filters
- [ ] Memory update operations
- [ ] Memory relationships/graphs
- [ ] Streaming search results

## References

- [Mem0 Documentation](https://docs.mem0.ai/)
- [Qdrant Documentation](https://qdrant.tech/documentation/)
- [Redis Documentation](https://redis.io/documentation)
- [Sentence Transformers](https://www.sbert.net/)
