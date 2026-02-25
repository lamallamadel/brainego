# Memory API Reference

Complete API reference for the Memory service endpoints.

## Base URL

```
http://localhost:8000
```

## Endpoints

### POST /memory/add

Add memories from conversation messages with automatic fact extraction.

**URL:** `/memory/add`  
**Method:** `POST`  
**Content-Type:** `application/json`

#### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `messages` | `array` | Yes | List of conversation messages |
| `messages[].role` | `string` | Yes | Role: "user", "assistant", or "system" |
| `messages[].content` | `string` | Yes | Message content |
| `user_id` | `string` | No | User identifier (default: "default_user") |
| `metadata` | `object` | No | Custom metadata dictionary |

#### Response

**Status Code:** `200 OK`

```json
{
  "status": "success",
  "memory_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2024-01-15T10:30:00.123456+00:00",
  "user_id": "alice",
  "facts_extracted": 2
}
```

| Field | Type | Description |
|-------|------|-------------|
| `status` | `string` | "success" or "error" |
| `memory_id` | `string` | UUID of created memory |
| `timestamp` | `string` | ISO 8601 timestamp |
| `user_id` | `string` | User identifier used |
| `facts_extracted` | `integer` | Number of facts extracted |

#### Example

```bash
curl -X POST http://localhost:8000/memory/add \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "I work as a software engineer in San Francisco"},
      {"role": "assistant", "content": "That sounds interesting!"}
    ],
    "user_id": "alice",
    "metadata": {
      "topic": "work",
      "importance": "high"
    }
  }'
```

#### Error Responses

**400 Bad Request** - Invalid request format
```json
{
  "detail": "Messages list cannot be empty"
}
```

**500 Internal Server Error** - Server error
```json
{
  "detail": "Memory add error: <error message>"
}
```

---

### POST /memory/search

Search memories with cosine similarity + temporal decay scoring.

**URL:** `/memory/search`  
**Method:** `POST`  
**Content-Type:** `application/json`

#### Request Body

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `query` | `string` | Yes | - | Search query text |
| `user_id` | `string` | No | `null` | Filter by user ID |
| `limit` | `integer` | No | `10` | Max results (1-100) |
| `filters` | `object` | No | `null` | Metadata filters |
| `use_temporal_decay` | `boolean` | No | `true` | Apply temporal decay |

#### Response

**Status Code:** `200 OK`

```json
{
  "query": "What does Alice do?",
  "results": [
    {
      "memory_id": "550e8400-e29b-41d4-a716-446655440000",
      "text": "user: I work as a software engineer in San Francisco\nassistant: That sounds interesting!",
      "score": 0.8542,
      "cosine_score": 0.8912,
      "temporal_score": 0.9134,
      "timestamp": "2024-01-15T10:30:00.123456+00:00",
      "user_id": "alice",
      "metadata": {
        "topic": "work",
        "importance": "high"
      },
      "messages": [
        {"role": "user", "content": "I work as a software engineer in San Francisco"},
        {"role": "assistant", "content": "That sounds interesting!"}
      ]
    }
  ],
  "limit": 10
}
```

| Field | Type | Description |
|-------|------|-------------|
| `query` | `string` | Original search query |
| `results` | `array` | List of matching memories |
| `results[].memory_id` | `string` | Memory UUID |
| `results[].text` | `string` | Memory text content |
| `results[].score` | `float` | Combined score (0-1) |
| `results[].cosine_score` | `float` | Cosine similarity (0-1) |
| `results[].temporal_score` | `float` | Temporal decay score (0-1) |
| `results[].timestamp` | `string` | ISO 8601 timestamp |
| `results[].user_id` | `string` | User identifier |
| `results[].metadata` | `object` | Custom metadata |
| `results[].messages` | `array` | Original messages |
| `limit` | `integer` | Limit used |

#### Scoring Formula

```
combined_score = 0.7 × cosine_score + 0.3 × temporal_score

where:
  cosine_score = cosine_similarity(query_embedding, memory_embedding)
  temporal_score = exp(-0.1 × age_in_days)
```

#### Example - Basic Search

```bash
curl -X POST http://localhost:8000/memory/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Where does Alice work?",
    "user_id": "alice",
    "limit": 5
  }'
```

#### Example - Filtered Search

```bash
curl -X POST http://localhost:8000/memory/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "work information",
    "user_id": "alice",
    "limit": 10,
    "filters": {
      "topic": "work"
    },
    "use_temporal_decay": false
  }'
```

#### Error Responses

**400 Bad Request** - Invalid parameters
```json
{
  "detail": "Limit must be between 1 and 100"
}
```

**500 Internal Server Error** - Server error
```json
{
  "detail": "Memory search error: <error message>"
}
```

---

### DELETE /memory/forget/{memory_id}

Delete a memory by ID.

**URL:** `/memory/forget/{memory_id}`  
**Method:** `DELETE`

#### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `memory_id` | `string` | Yes | UUID of memory to delete |

#### Response

**Status Code:** `200 OK`

```json
{
  "status": "success",
  "memory_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "Memory deleted successfully"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `status` | `string` | "success" |
| `memory_id` | `string` | Deleted memory UUID |
| `message` | `string` | Confirmation message |

#### Example

```bash
curl -X DELETE http://localhost:8000/memory/forget/550e8400-e29b-41d4-a716-446655440000
```

#### Error Responses

**404 Not Found** - Memory not found
```json
{
  "detail": "Memory not found"
}
```

**500 Internal Server Error** - Server error
```json
{
  "detail": "Memory delete error: <error message>"
}
```

---

### GET /memory/stats

Get memory system statistics.

**URL:** `/memory/stats`  
**Method:** `GET`

#### Response

**Status Code:** `200 OK`

```json
{
  "collection_name": "memories",
  "qdrant_points": 1234,
  "redis_memories": 1234,
  "vector_dimension": 384,
  "distance_metric": "COSINE"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `collection_name` | `string` | Qdrant collection name |
| `qdrant_points` | `integer` | Number of vectors in Qdrant |
| `redis_memories` | `integer` | Number of memories in Redis |
| `vector_dimension` | `integer` | Embedding dimension |
| `distance_metric` | `string` | Distance metric used |

#### Example

```bash
curl http://localhost:8000/memory/stats
```

#### Error Responses

**500 Internal Server Error** - Server error
```json
{
  "detail": "Memory stats error: <error message>"
}
```

---

## Data Models

### Message Object

```json
{
  "role": "user",
  "content": "Message text"
}
```

| Field | Type | Values | Description |
|-------|------|--------|-------------|
| `role` | `string` | "user", "assistant", "system" | Message role |
| `content` | `string` | - | Message content |

### Metadata Object

Custom key-value pairs for filtering and organization:

```json
{
  "topic": "programming",
  "category": "work",
  "importance": "high",
  "tags": ["python", "ml"]
}
```

### Filter Object

Used in search to filter by metadata:

```json
{
  "topic": "programming",
  "importance": "high"
}
```

Supports exact match only. All specified filters must match (AND logic).

---

## Rate Limits

Currently no rate limits are enforced. For production use, consider implementing:

- Per-user rate limits
- API key authentication
- Request throttling

---

## Best Practices

### 1. User Identification

Always provide a `user_id` for personalized memories:

```json
{
  "user_id": "user_12345",
  "messages": [...]
}
```

### 2. Metadata Organization

Use consistent metadata schemas:

```json
{
  "metadata": {
    "category": "personal|work|education",
    "topic": "...",
    "importance": "low|medium|high",
    "tags": ["tag1", "tag2"]
  }
}
```

### 3. Query Formulation

- Be specific in queries
- Use natural language
- Include context when needed

**Good:**
```json
{"query": "What programming languages does the user know?"}
```

**Less effective:**
```json
{"query": "programming"}
```

### 4. Temporal Decay Usage

**Recent events:**
```json
{"use_temporal_decay": true}  // Favor recent memories
```

**Facts/Knowledge:**
```json
{"use_temporal_decay": false}  // All memories equal
```

### 5. Result Limits

- Start with small limits (5-10)
- Increase only if needed
- Higher limits = slower responses

---

## Examples by Use Case

### Personal Assistant

```bash
# Store preferences
curl -X POST http://localhost:8000/memory/add \
  -d '{
    "messages": [{"role": "user", "content": "I prefer dark mode"}],
    "user_id": "user123",
    "metadata": {"category": "preferences"}
  }'

# Retrieve preferences
curl -X POST http://localhost:8000/memory/search \
  -d '{
    "query": "user interface preferences",
    "user_id": "user123",
    "filters": {"category": "preferences"}
  }'
```

### Customer Support

```bash
# Store issue
curl -X POST http://localhost:8000/memory/add \
  -d '{
    "messages": [
      {"role": "user", "content": "My order #12345 is delayed"},
      {"role": "assistant", "content": "Let me check that for you"}
    ],
    "user_id": "customer_67890",
    "metadata": {"type": "support", "order_id": "12345"}
  }'

# Retrieve history
curl -X POST http://localhost:8000/memory/search \
  -d '{
    "query": "order issues",
    "user_id": "customer_67890",
    "filters": {"type": "support"}
  }'
```

### Learning Platform

```bash
# Store completed lesson
curl -X POST http://localhost:8000/memory/add \
  -d '{
    "messages": [{"role": "user", "content": "Completed Python basics lesson"}],
    "user_id": "student_456",
    "metadata": {"type": "progress", "course": "python"}
  }'

# Check progress
curl -X POST http://localhost:8000/memory/search \
  -d '{
    "query": "python course progress",
    "user_id": "student_456",
    "filters": {"type": "progress", "course": "python"}
  }'
```

---

## Changelog

### v1.0.0 (Initial Release)

- POST /memory/add - Add conversation memories
- POST /memory/search - Search with temporal decay
- DELETE /memory/forget/{id} - Delete memories
- GET /memory/stats - System statistics
- Mem0 integration for fact extraction
- Qdrant vector storage
- Redis metadata storage
- Configurable temporal decay
- User-specific memories
- Metadata filtering

---

## Support

For issues and questions:

- Check [MEMORY_README.md](MEMORY_README.md) for detailed documentation
- See [MEMORY_QUICKSTART.md](MEMORY_QUICKSTART.md) for quick start guide
- Run `python examples/memory_example.py` for working examples
- Check server logs: `docker compose logs api-server`
