# RAG Query Implementation Details

## Architecture

The RAG query implementation integrates three main components:

```
┌─────────────────────────────────────────────────────────────┐
│                    Client Application                        │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              POST /v1/rag/query Endpoint                     │
│              (api_server.py)                                 │
└──────────────────────┬──────────────────────────────────────┘
                       │
        ┌──────────────┴──────────────┐
        ▼                              ▼
┌──────────────────┐          ┌──────────────────┐
│  RAG Service     │          │   MAX Serve      │
│  (rag_service.py)│          │   (LLM)          │
└────────┬─────────┘          └──────────────────┘
         │
         ▼
┌──────────────────┐
│   Qdrant VDB     │
│   (Cosine)       │
└──────────────────┘
```

## Implementation Flow

### 1. Query Processing

**File**: `api_server.py` (lines 549-698)

```python
@app.post("/v1/rag/query", response_model=RAGQueryResponse)
async def rag_query(request: RAGQueryRequest):
    # 1. Extract parameters
    query = request.query
    k = request.k  # top-k configuration
    filters = request.filters  # metadata filtering
    
    # 2. Retrieve context
    results = service.search_documents(
        query=query,
        limit=k,
        filters=filters
    )
```

### 2. Cosine Similarity Search

**File**: `rag_service.py` (lines 370-389)

```python
def search_documents(
    self,
    query: str,
    limit: int = 10,
    filters: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    # Convert query to embedding
    query_embedding = self.embedder.embed_text(query)
    
    # Search Qdrant with cosine similarity
    results = self.storage.search(
        query_vector=query_embedding,
        limit=limit,
        filter_conditions=filters
    )
```

**File**: `rag_service.py` (lines 179-225)

```python
def search(
    self,
    query_vector: List[float],
    limit: int = 10,
    filter_conditions: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    # Construct metadata filters
    query_filter = None
    if filter_conditions:
        conditions = []
        for key, value in filter_conditions.items():
            conditions.append(
                FieldCondition(
                    key=f"metadata.{key}",
                    match=MatchValue(value=value)
                )
            )
        query_filter = Filter(must=conditions)
    
    # Perform cosine similarity search
    results = self.client.search(
        collection_name=self.collection_name,
        query_vector=query_vector,
        limit=limit,
        query_filter=query_filter
    )
```

### 3. Context Construction

**File**: `api_server.py` (lines 600-640)

```python
# Format retrieved chunks
if results:
    context_chunks = []
    for idx, result in enumerate(results):
        chunk_text = f"[Context {idx + 1}]\n{result['text']}\n"
        context_chunks.append(chunk_text)
    
    context_text = "\n".join(context_chunks)
    
    # Build augmented prompt
    system_message = ChatMessage(
        role="system",
        content=(
            "You are a helpful assistant. Use the following context "
            "to answer the user's question.\n\n"
            f"Context:\n{context_text}"
        )
    )
```

### 4. Prompt Augmentation

**File**: `api_server.py` (lines 617-641)

```python
messages_list = []

# Add system message with context
if context_text:
    system_message = ChatMessage(
        role="system",
        content=f"Context:\n{context_text}"
    )
    messages_list.append(system_message)

# Add chat history if provided
if request.messages:
    messages_list.extend(request.messages)

# Add current query
messages_list.append(ChatMessage(role="user", content=request.query))

# Format for Llama 3.3
prompt = format_chat_prompt(messages_list)
```

### 5. LLM Generation

**File**: `api_server.py` (lines 643-652)

```python
params = {
    "max_tokens": request.max_tokens,
    "temperature": request.temperature,
    "top_p": request.top_p,
    "stop": ["<|eot_id|>", "<|end_of_text|>"],
}

generated_text, prompt_tokens, completion_tokens = await call_max_serve(
    prompt, params
)
```

## Key Features

### 1. Cosine Similarity Search

- **Distance Metric**: Qdrant configured with `Distance.COSINE` (line 125 in rag_service.py)
- **Score Range**: 0.0 (no similarity) to 1.0 (identical)
- **Normalization**: Nomic Embed vectors are normalized by default

### 2. Top-k Configuration

- **Parameter**: `k` in `RAGQueryRequest` (line 150 in api_server.py)
- **Default**: 5 chunks
- **Range**: 1-20 chunks (configurable via `ge=1, le=20`)
- **Usage**: Controls number of chunks retrieved from Qdrant

### 3. Metadata Filtering

**Implementation** (lines 196-206 in rag_service.py):

```python
if filter_conditions:
    conditions = []
    for key, value in filter_conditions.items():
        conditions.append(
            FieldCondition(
                key=f"metadata.{key}",
                match=MatchValue(value=value)
            )
        )
    query_filter = Filter(must=conditions)
```

**Supported**: Any metadata field stored during ingestion

**Example filters**:
- `{"category": "technology"}`
- `{"author": "John Doe", "year": "2024"}`
- `{"difficulty": "beginner", "topic": "ml"}`

### 4. Retrieval Statistics

**File**: `api_server.py` (lines 609-615)

```python
scores = [r['score'] for r in results]
retrieval_stats = {
    "chunks_retrieved": len(results),
    "retrieval_time_ms": round(retrieval_time_ms, 2),
    "top_score": round(scores[0], 4),
    "avg_score": round(sum(scores) / len(scores), 4),
    "min_score": round(min(scores), 4)
}
```

## Data Models

### Request Model

```python
class RAGQueryRequest(BaseModel):
    query: str = Field(..., description="Query text")
    k: int = Field(5, ge=1, le=20, description="Top-k results")
    filters: Optional[Dict[str, Any]] = Field(None)
    messages: Optional[List[ChatMessage]] = Field(None)
    temperature: Optional[float] = Field(0.7, ge=0.0, le=2.0)
    top_p: Optional[float] = Field(0.9, ge=0.0, le=1.0)
    max_tokens: Optional[int] = Field(2048, ge=1)
    include_context: Optional[bool] = Field(True)
```

### Response Model

```python
class RAGQueryResponse(BaseModel):
    id: str
    object: str = "rag.query.completion"
    created: int
    query: str
    context: Optional[List[Dict[str, Any]]]
    response: str
    usage: ChatCompletionUsage
    retrieval_stats: Dict[str, Any]
```

## Configuration

### Collection Setup

**File**: `rag_service.py` (lines 111-131)

```python
def create_collection(self, vector_size: int):
    self.client.create_collection(
        collection_name=self.collection_name,
        vectors_config=VectorParams(
            size=vector_size,  # 768 for Nomic Embed v1.5
            distance=Distance.COSINE  # Cosine similarity
        )
    )
```

### Embedding Model

**File**: `rag_service.py` (lines 78-85)

```python
class NomicEmbedder:
    def __init__(self, model_name: str = "nomic-ai/nomic-embed-text-v1.5"):
        self.model = SentenceTransformer(
            model_name,
            trust_remote_code=True
        )
        self.dimension = self.model.get_sentence_embedding_dimension()
```

## Performance Optimization

### 1. Batch Embedding

```python
def embed_batch(self, texts: List[str]) -> List[List[float]]:
    embeddings = self.model.encode(
        texts,
        convert_to_numpy=True,
        show_progress_bar=False
    )
    return embeddings.tolist()
```

### 2. Async Operations

All endpoint handlers are async for non-blocking I/O:

```python
async def rag_query(request: RAGQueryRequest):
    # Async HTTP calls to MAX Serve
    generated_text, tokens = await call_max_serve(prompt, params)
```

### 3. Metrics Tracking

```python
start_time = time.time()
retrieval_start = time.time()
results = service.search_documents(...)
retrieval_time_ms = (time.time() - retrieval_start) * 1000

generation_start = time.time()
generated_text = await call_max_serve(...)
generation_time_ms = (time.time() - generation_start) * 1000
```

## Error Handling

```python
try:
    service = get_rag_service()
    results = service.search_documents(...)
    generated_text = await call_max_serve(...)
    
except HTTPException:
    metrics.record_request(..., error=True)
    raise
    
except Exception as e:
    logger.error(f"Error in RAG query: {e}", exc_info=True)
    raise HTTPException(status_code=500, detail=f"RAG query error: {str(e)}")
```

## Testing

### Test Coverage

**File**: `test_rag.py` (lines 139-237)

1. **Basic Query**: Default k=5, include context
2. **Filtered Query**: Metadata filtering by batch tag
3. **Top-k Variations**: Test k=1, 3, 5

### Example Test

```python
def test_rag_query():
    response = httpx.post(
        f"{API_BASE_URL}/v1/rag/query",
        json={
            "query": "What is a test document?",
            "k": 3,
            "temperature": 0.7,
            "include_context": True
        },
        timeout=120.0
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert "query" in data
    assert "response" in data
    assert "retrieval_stats" in data
    assert data["retrieval_stats"]["chunks_retrieved"] <= 3
```

## Files Modified

1. **api_server.py**
   - Added `RAGQueryRequest` model (lines 147-156)
   - Added `RAGQueryResponse` model (lines 158-166)
   - Added `/v1/rag/query` endpoint (lines 549-698)
   - Updated root endpoint docs (line 306)

2. **examples/rag_ingest_example.py**
   - Added `rag_query()` function (lines 80-102)
   - Added RAG query examples (lines 219-270)

3. **examples/rag_query_example.py**
   - New comprehensive example file
   - Demonstrates all RAG query features

4. **test_rag.py**
   - Added `test_rag_query()` (lines 139-186)
   - Added `test_rag_query_with_filters()` (lines 189-214)
   - Added `test_rag_query_top_k_variations()` (lines 217-237)

## Dependencies

All dependencies already present in `requirements.txt`:

- `fastapi==0.104.1` - API framework
- `httpx==0.25.1` - Async HTTP client
- `qdrant-client==1.7.0` - Vector database client
- `sentence-transformers==2.2.2` - Embedding model
- `pydantic==2.5.0` - Data validation

## Usage Summary

### Quick Start

```python
import httpx

# Query with default settings
response = httpx.post(
    "http://localhost:8000/v1/rag/query",
    json={"query": "Your question here"}
)
result = response.json()
print(result["response"])
```

### Advanced Usage

```python
response = httpx.post(
    "http://localhost:8000/v1/rag/query",
    json={
        "query": "Your question",
        "k": 7,  # Retrieve top 7 chunks
        "filters": {"category": "docs"},  # Filter by metadata
        "temperature": 0.5,  # Lower temperature for factual
        "max_tokens": 1024,  # Limit response length
        "include_context": True  # Show retrieved chunks
    }
)
```

## See Also

- [RAG Query README](RAG_QUERY_README.md) - User documentation
- [AGENTS.md](AGENTS.md) - Project conventions and commands
- [api_server.py](api_server.py) - Full implementation
- [rag_service.py](rag_service.py) - RAG service logic
