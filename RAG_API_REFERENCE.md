# RAG API Quick Reference

## Endpoints Overview

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/v1/rag/ingest` | Ingest a single document |
| POST | `/v1/rag/ingest/batch` | Ingest multiple documents |
| POST | `/v1/rag/search` | Search for documents |
| DELETE | `/v1/rag/documents/{id}` | Delete a document |
| GET | `/v1/rag/stats` | Get system statistics |

## Quick Examples

### Ingest a Document

```bash
curl -X POST http://localhost:8000/v1/rag/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Your document text here...",
    "metadata": {
      "title": "My Document",
      "category": "technology"
    }
  }'
```

### Search Documents

```bash
curl -X POST http://localhost:8000/v1/rag/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "your search query",
    "limit": 5
  }'
```

### Get Statistics

```bash
curl http://localhost:8000/v1/rag/stats
```

## Request/Response Formats

### Ingest Request

```json
{
  "text": "string (required)",
  "metadata": {
    "key": "value (optional)"
  }
}
```

### Ingest Response

```json
{
  "status": "success",
  "document_id": "uuid",
  "chunks_created": 5,
  "points_stored": 5,
  "point_ids": ["id1", "id2"],
  "metadata": {}
}
```

### Search Request

```json
{
  "query": "string (required)",
  "limit": 10,
  "filters": {
    "metadata_key": "value"
  }
}
```

### Search Response

```json
{
  "results": [
    {
      "id": "point-id",
      "score": 0.89,
      "text": "chunk text",
      "metadata": {},
      "ingested_at": "timestamp"
    }
  ],
  "query": "original query",
  "limit": 10
}
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| QDRANT_HOST | localhost | Qdrant server host |
| QDRANT_PORT | 6333 | Qdrant server port |
| QDRANT_COLLECTION | documents | Collection name |

## Chunking Parameters

- **Chunk Size**: 1000 characters
- **Overlap**: 100 characters
- **Embedding Model**: nomic-ai/nomic-embed-text-v1.5
- **Embedding Dimension**: 768
- **Distance Metric**: Cosine similarity

## Common Use Cases

### 1. Knowledge Base

```python
# Ingest documentation
for doc in documentation:
    httpx.post(f"{API}/v1/rag/ingest", json={
        "text": doc.content,
        "metadata": {
            "title": doc.title,
            "category": doc.category,
            "version": doc.version
        }
    })

# Search for answers
results = httpx.post(f"{API}/v1/rag/search", json={
    "query": user_question,
    "limit": 3
})
```

### 2. Document Q&A

```python
# Search for context
search_response = httpx.post(f"{API}/v1/rag/search", json={
    "query": question,
    "limit": 5
})

# Use context with chat
context = "\n".join([r['text'] for r in search_response.json()['results']])
chat_response = httpx.post(f"{API}/v1/chat/completions", json={
    "messages": [
        {"role": "system", "content": "Answer using the context."},
        {"role": "user", "content": f"Context:\n{context}\n\nQ: {question}"}
    ]
})
```

### 3. Semantic Search

```python
# Search with metadata filters
results = httpx.post(f"{API}/v1/rag/search", json={
    "query": "machine learning",
    "limit": 10,
    "filters": {
        "category": "ai",
        "year": "2024"
    }
})
```

### 4. Semantic Search Across Collections

```python
# Top-k semantic search with filters and optional collection override
results = httpx.post(f"{API}/v1/rag/semantic-search", json={
    "query": "vector indexing strategy",
    "top_k": 8,
    "collection_name": "engineering-docs",
    "filters": {
        "project": "brainego",
        "source": {"any": ["github", "notion"]}
    }
})
```

### Qdrant Filter Semantics Reference

- Qdrant supports `match: { any: [...] }` for "one-of" matching (IN-style filtering).
- For better filtered-search performance at scale, create payload indexes on frequently filtered metadata fields.

References:
- https://qdrant.tech/documentation/concepts/filtering/
- https://qdrant.tech/documentation/concepts/search/

## Error Codes

| Code | Description |
|------|-------------|
| 200 | Success |
| 400 | Invalid request (empty text, invalid parameters) |
| 500 | Server error (Qdrant connection, embedding generation) |
| 503 | Service unavailable (dependencies not ready) |

## Performance Tips

1. **Batch Processing**: Use `/v1/rag/ingest/batch` for multiple documents
2. **Appropriate Limits**: Start with limit=5-10 for searches
3. **Metadata Filters**: Use filters to reduce search space
4. **Caching**: Cache frequently accessed document embeddings
5. **Chunking**: Adjust chunk size based on document type

## Testing

```bash
# Run basic tests
python test_rag.py

# Run comprehensive examples
python examples/rag_ingest_example.py
```

## Monitoring

```bash
# Check RAG statistics
curl http://localhost:8000/v1/rag/stats

# Check overall health
curl http://localhost:8000/health

# View metrics
curl http://localhost:8000/metrics
```
