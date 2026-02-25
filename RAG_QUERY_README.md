# RAG Query Endpoint Documentation

## Overview

The `/v1/rag/query` endpoint provides retrieval-augmented generation (RAG) capabilities by combining cosine similarity search with LLM-based response generation. It retrieves relevant context from the vector database and uses it to generate more accurate, context-aware responses.

## Endpoint

**POST** `/v1/rag/query`

## Features

- **Cosine Similarity Search**: Uses Qdrant's cosine distance metric for semantic similarity
- **Top-k Retrieval**: Configurable number of most relevant chunks (default k=5, range 1-20)
- **Metadata Filtering**: Filter retrieved documents by metadata fields
- **Context-Augmented Generation**: Injects retrieved context into prompts for MAX Serve
- **Multi-turn Conversations**: Supports chat history for contextual follow-up questions
- **Performance Metrics**: Tracks retrieval time, generation time, and similarity scores
- **Flexible Configuration**: Adjustable temperature, top_p, max_tokens parameters

## Request Schema

```json
{
  "query": "string (required)",
  "k": 5,
  "filters": {
    "key": "value"
  },
  "messages": [
    {
      "role": "user",
      "content": "previous message"
    }
  ],
  "temperature": 0.7,
  "top_p": 0.9,
  "max_tokens": 2048,
  "include_context": true
}
```

### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `query` | string | Yes | - | User query text to search for relevant context |
| `k` | integer | No | 5 | Number of top results to retrieve (1-20) |
| `filters` | object | No | null | Metadata filters for retrieval (key-value pairs) |
| `messages` | array | No | null | Optional chat history for multi-turn conversations |
| `temperature` | float | No | 0.7 | Sampling temperature (0.0-2.0) |
| `top_p` | float | No | 0.9 | Nucleus sampling parameter (0.0-1.0) |
| `max_tokens` | integer | No | 2048 | Maximum tokens to generate |
| `include_context` | boolean | No | true | Include retrieved context chunks in response |

## Response Schema

```json
{
  "id": "rag-abc123...",
  "object": "rag.query.completion",
  "created": 1234567890,
  "query": "What is machine learning?",
  "context": [
    {
      "text": "Machine learning is...",
      "score": 0.8756,
      "metadata": {
        "title": "ML Guide",
        "category": "ai"
      },
      "id": "uuid-..."
    }
  ],
  "response": "Machine learning is a subset of AI...",
  "usage": {
    "prompt_tokens": 150,
    "completion_tokens": 75,
    "total_tokens": 225
  },
  "retrieval_stats": {
    "chunks_retrieved": 5,
    "retrieval_time_ms": 45.23,
    "generation_time_ms": 823.45,
    "total_time_ms": 868.68,
    "top_score": 0.8756,
    "avg_score": 0.7832,
    "min_score": 0.6945
  }
}
```

### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique identifier for the query |
| `object` | string | Object type ("rag.query.completion") |
| `created` | integer | Unix timestamp |
| `query` | string | Original query text |
| `context` | array | Retrieved context chunks (if include_context=true) |
| `response` | string | Generated response augmented with context |
| `usage` | object | Token usage statistics |
| `retrieval_stats` | object | Performance and similarity metrics |

## How It Works

1. **Query Embedding**: Converts the user query to a vector using Nomic Embed v1.5
2. **Cosine Similarity Search**: Searches Qdrant for the top-k most similar chunks
3. **Optional Filtering**: Applies metadata filters if provided
4. **Context Construction**: Formats retrieved chunks as context
5. **Prompt Augmentation**: Injects context into system message
6. **Generation**: Calls MAX Serve with augmented prompt
7. **Response Formatting**: Returns generated text with metadata

## Usage Examples

### Basic Query

```python
import httpx

response = httpx.post(
    "http://localhost:8000/v1/rag/query",
    json={
        "query": "What is machine learning?",
        "k": 5
    }
)
result = response.json()
print(result["response"])
```

### Query with Top-k Configuration

```python
# Retrieve only top 3 most relevant chunks
response = httpx.post(
    "http://localhost:8000/v1/rag/query",
    json={
        "query": "Explain neural networks",
        "k": 3,
        "temperature": 0.6
    }
)
```

### Query with Metadata Filtering

```python
# Only search in "technology" category
response = httpx.post(
    "http://localhost:8000/v1/rag/query",
    json={
        "query": "What are the latest developments?",
        "k": 5,
        "filters": {
            "category": "technology",
            "year": "2024"
        }
    }
)
```

### Multi-turn Conversation

```python
# Follow-up question with context
response = httpx.post(
    "http://localhost:8000/v1/rag/query",
    json={
        "query": "What are its applications?",
        "k": 4,
        "messages": [
            {"role": "user", "content": "Tell me about deep learning"},
            {"role": "assistant", "content": "Deep learning is..."}
        ]
    }
)
```

### Without Context Details

```python
# Get response without context chunks in output
response = httpx.post(
    "http://localhost:8000/v1/rag/query",
    json={
        "query": "Summarize the main points",
        "k": 5,
        "include_context": false
    }
)
```

### Custom Generation Parameters

```python
response = httpx.post(
    "http://localhost:8000/v1/rag/query",
    json={
        "query": "Provide a detailed explanation",
        "k": 7,
        "temperature": 0.8,
        "top_p": 0.95,
        "max_tokens": 1024
    }
)
```

## Performance Considerations

### Top-k Selection

- **k=1-3**: Fast retrieval, focused context, may miss relevant information
- **k=5** (default): Balanced retrieval time and context coverage
- **k=10-20**: Comprehensive context, slower retrieval, larger prompts

### Metadata Filtering

- Reduces search space, improving retrieval speed
- Ensures results match specific criteria (category, date, source, etc.)
- Can be combined with top-k for precise control

### Temperature Settings

- **0.0-0.3**: Deterministic, factual responses
- **0.5-0.7**: Balanced creativity and accuracy
- **0.8-2.0**: More creative, less predictable

## Retrieval Statistics

The `retrieval_stats` object provides insights into query performance:

- `chunks_retrieved`: Number of chunks found (≤ k)
- `retrieval_time_ms`: Time spent searching Qdrant
- `generation_time_ms`: Time spent generating with MAX Serve
- `total_time_ms`: End-to-end query time
- `top_score`: Highest cosine similarity score (0.0-1.0)
- `avg_score`: Average similarity across retrieved chunks
- `min_score`: Lowest similarity among retrieved chunks

Higher similarity scores (closer to 1.0) indicate better semantic matches.

## Error Handling

### Common Errors

**400 Bad Request**
```json
{
  "detail": "Query text cannot be empty"
}
```

**500 Internal Server Error**
```json
{
  "detail": "RAG query error: [error details]"
}
```

**503 Service Unavailable**
```json
{
  "detail": "MAX Serve error: Connection timeout"
}
```

## Integration with Other Endpoints

### Complete Workflow

1. **Ingest Documents**: `POST /v1/rag/ingest` or `/v1/rag/ingest/batch`
2. **Verify Stats**: `GET /v1/rag/stats`
3. **Search (Optional)**: `POST /v1/rag/search` to test retrieval
4. **Query with RAG**: `POST /v1/rag/query` for augmented responses
5. **Manage Documents**: `DELETE /v1/rag/documents/{id}` as needed

## Best Practices

1. **Start with k=5**: Default provides good balance
2. **Use Metadata Filters**: Narrow search scope for better relevance
3. **Monitor Similarity Scores**: Low scores may indicate poor matches
4. **Adjust Temperature**: Lower for factual queries, higher for creative tasks
5. **Include Context**: Set `include_context=true` for debugging
6. **Handle Empty Results**: Check `chunks_retrieved` before relying on context

## Example Use Cases

### Technical Documentation Q&A

```python
# Ingest API documentation
httpx.post("/v1/rag/ingest", json={
    "text": "API documentation...",
    "metadata": {"type": "docs", "version": "2.0"}
})

# Query with filtering
httpx.post("/v1/rag/query", json={
    "query": "How do I authenticate?",
    "k": 3,
    "filters": {"type": "docs", "version": "2.0"}
})
```

### Knowledge Base Search

```python
httpx.post("/v1/rag/query", json={
    "query": "Troubleshoot login issues",
    "k": 5,
    "filters": {"category": "troubleshooting"},
    "temperature": 0.5
})
```

### Research Assistant

```python
httpx.post("/v1/rag/query", json={
    "query": "Summarize recent findings on topic X",
    "k": 10,
    "filters": {"year": "2024"},
    "temperature": 0.7,
    "max_tokens": 2048
})
```

## See Also

- [RAG Implementation Summary](RAG_IMPLEMENTATION_SUMMARY.md)
- [RAG API Reference](RAG_API_REFERENCE.md)
- [Example Scripts](examples/)
  - `rag_query_example.py` - Comprehensive query examples
  - `rag_ingest_example.py` - Full RAG workflow
- [Test Suite](test_rag.py)
