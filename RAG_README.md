# RAG Ingestion Service

This document describes the Retrieval-Augmented Generation (RAG) ingestion service integrated into the API server.

## Overview

The RAG ingestion service provides document chunking, embedding generation using Nomic Embed v1.5, and vector storage in Qdrant. It enables semantic search over ingested documents to support RAG-based applications.

## Features

- **Document Chunking**: Automatically splits documents into 1000-character chunks with 100-character overlap
- **Metadata Tagging**: Associate custom metadata with documents for filtering and organization
- **Nomic Embed v1.5**: State-of-the-art embedding model for semantic understanding
- **Qdrant Storage**: Efficient vector database storage and retrieval
- **Batch Processing**: Ingest multiple documents in a single request
- **Semantic Search**: Find relevant document chunks using natural language queries
- **Metadata Filtering**: Filter search results by metadata fields

## Architecture

```
Document → Chunking → Embedding → Qdrant Storage
  (Text)     (1000c)    (Nomic)     (Vectors)
              ↓
          Metadata Tagging
```

### Components

1. **DocumentChunker**: Splits text into overlapping chunks
   - Chunk size: 1000 characters
   - Overlap: 100 characters
   - Preserves context across chunk boundaries

2. **NomicEmbedder**: Generates embeddings using Nomic Embed v1.5
   - Model: `nomic-ai/nomic-embed-text-v1.5`
   - Embedding dimension: 768
   - Supports batch processing

3. **QdrantStorage**: Manages vector storage and retrieval
   - Collection name: `documents` (configurable)
   - Distance metric: Cosine similarity
   - Supports metadata filtering

## API Endpoints

### 1. Ingest Single Document

**POST** `/v1/rag/ingest`

Ingest a single document into the RAG system.

**Request:**
```json
{
  "text": "Your document text here...",
  "metadata": {
    "title": "Document Title",
    "category": "technology",
    "author": "Author Name",
    "date": "2024-01-15"
  }
}
```

**Response:**
```json
{
  "status": "success",
  "document_id": "550e8400-e29b-41d4-a716-446655440000",
  "chunks_created": 5,
  "points_stored": 5,
  "point_ids": ["id1", "id2", "id3", "id4", "id5"],
  "metadata": {
    "title": "Document Title",
    "category": "technology",
    "document_id": "550e8400-e29b-41d4-a716-446655440000",
    "ingestion_timestamp": "2024-01-15T10:30:00"
  }
}
```

### 2. Batch Ingest Documents

**POST** `/v1/rag/ingest/batch`

Ingest multiple documents in a single request.

**Request:**
```json
{
  "documents": [
    {
      "text": "First document text...",
      "metadata": {"title": "Doc 1", "category": "tech"}
    },
    {
      "text": "Second document text...",
      "metadata": {"title": "Doc 2", "category": "science"}
    }
  ]
}
```

**Response:**
```json
{
  "status": "success",
  "documents_processed": 2,
  "total_chunks": 10,
  "total_points": 10,
  "results": [
    {
      "status": "success",
      "document_id": "...",
      "chunks_created": 5,
      "points_stored": 5,
      ...
    },
    ...
  ]
}
```

### 3. Search Documents

**POST** `/v1/rag/search`

Search for relevant document chunks using semantic similarity.

**Request:**
```json
{
  "query": "machine learning algorithms",
  "limit": 10,
  "filters": {
    "category": "technology"
  }
}
```

**Response:**
```json
{
  "results": [
    {
      "id": "point-id",
      "score": 0.8934,
      "text": "Machine learning is a subset of AI...",
      "metadata": {
        "document_id": "...",
        "title": "ML Introduction",
        "category": "technology",
        "chunk_index": 0
      },
      "ingested_at": "2024-01-15T10:30:00"
    },
    ...
  ],
  "query": "machine learning algorithms",
  "limit": 10
}
```

### 4. Delete Document

**DELETE** `/v1/rag/documents/{document_id}`

Delete a document and all its chunks.

**Response:**
```json
{
  "status": "success",
  "document_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "Document deleted successfully"
}
```

### 5. Get Statistics

**GET** `/v1/rag/stats`

Get RAG system statistics.

**Response:**
```json
{
  "collection_info": {
    "name": "documents",
    "vectors_count": 1234,
    "points_count": 1234,
    "status": "green"
  }
}
```

## Usage Examples

### Python with httpx

```python
import httpx

# Ingest a document
response = httpx.post(
    "http://localhost:8000/v1/rag/ingest",
    json={
        "text": "Your document text...",
        "metadata": {"title": "My Document"}
    },
    timeout=60.0
)
result = response.json()
print(f"Document ID: {result['document_id']}")

# Search documents
response = httpx.post(
    "http://localhost:8000/v1/rag/search",
    json={
        "query": "search query",
        "limit": 5
    },
    timeout=30.0
)
results = response.json()
for item in results['results']:
    print(f"Score: {item['score']:.4f} - {item['text'][:100]}...")
```

### cURL

```bash
# Ingest a document
curl -X POST http://localhost:8000/v1/rag/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Your document text...",
    "metadata": {"title": "My Document"}
  }'

# Search documents
curl -X POST http://localhost:8000/v1/rag/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "search query",
    "limit": 5
  }'

# Get statistics
curl http://localhost:8000/v1/rag/stats

# Delete a document
curl -X DELETE http://localhost:8000/v1/rag/documents/{document_id}
```

## Configuration

Configure the RAG service using environment variables:

```bash
# Qdrant connection
export QDRANT_HOST=localhost
export QDRANT_PORT=6333
export QDRANT_COLLECTION=documents

# Start the API server
python api_server.py
```

In Docker Compose, these are configured in `docker-compose.yaml`:

```yaml
environment:
  - QDRANT_HOST=qdrant
  - QDRANT_PORT=6333
  - QDRANT_COLLECTION=documents
```

## Running Tests

### Basic functionality test
```bash
python test_rag.py
```

### Comprehensive example
```bash
python examples/rag_ingest_example.py
```

## Best Practices

### Chunking Strategy

The default chunk size (1000 characters) and overlap (100 characters) work well for most use cases, but you may want to adjust based on your needs:

- **Shorter chunks (500-700 chars)**: Better for precise retrieval, more granular results
- **Longer chunks (1500-2000 chars)**: More context per chunk, fewer total chunks
- **Overlap**: Prevents important information from being split across boundaries

### Metadata Design

Use metadata effectively for filtering and organization:

```json
{
  "document_id": "auto-generated",
  "title": "Document Title",
  "category": "technology",
  "source": "web|pdf|api",
  "author": "Author Name",
  "date": "2024-01-15",
  "language": "en",
  "version": "1.0"
}
```

### Search Optimization

- **Query formulation**: Use natural language questions or key phrases
- **Limit**: Start with 5-10 results, adjust based on needs
- **Filters**: Use metadata filters to narrow search scope
- **Score threshold**: Consider filtering results below 0.7 similarity score

## Troubleshooting

### Qdrant Connection Issues

```python
# Check Qdrant health
curl http://localhost:6333/health

# Verify collection exists
curl http://localhost:6333/collections/documents
```

### Embedding Model Loading

The Nomic Embed model is downloaded on first use (~500MB). Ensure sufficient disk space and network connectivity.

### Performance Optimization

- Use batch ingestion for multiple documents
- Implement caching for frequently accessed embeddings
- Consider increasing Qdrant resources for large datasets
- Monitor memory usage during embedding generation

## Technical Details

### Nomic Embed v1.5 Specifications

- **Architecture**: Transformer-based
- **Dimension**: 768
- **Max sequence length**: 8192 tokens
- **Languages**: Primarily English, supports multilingual
- **License**: Apache 2.0

### Qdrant Configuration

- **Collection**: documents
- **Distance metric**: Cosine similarity
- **Vector size**: 768 (matches Nomic Embed)
- **Indexing**: HNSW (Hierarchical Navigable Small World)

## Integration with Chat Completions

Combine RAG search with chat completions for knowledge-augmented responses:

```python
# 1. Search for relevant context
search_response = httpx.post(
    "http://localhost:8000/v1/rag/search",
    json={"query": user_query, "limit": 3}
)
context_chunks = search_response.json()['results']

# 2. Build context-augmented prompt
context = "\n\n".join([chunk['text'] for chunk in context_chunks])
messages = [
    {"role": "system", "content": "Answer based on the provided context."},
    {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {user_query}"}
]

# 3. Get chat completion
chat_response = httpx.post(
    "http://localhost:8000/v1/chat/completions",
    json={"messages": messages, "max_tokens": 500}
)
answer = chat_response.json()['choices'][0]['message']['content']
```

## License

This RAG implementation uses:
- **Nomic Embed v1.5**: Apache 2.0 License
- **Qdrant**: Apache 2.0 License
- **Sentence Transformers**: Apache 2.0 License
