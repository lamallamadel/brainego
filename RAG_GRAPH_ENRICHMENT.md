# Graph-Enriched RAG Implementation

## Overview

This implementation integrates Neo4j knowledge graph context enrichment into the RAG (Retrieval-Augmented Generation) retriever, combining vector similarity search with relational context from a knowledge graph to provide more comprehensive and contextually-aware retrieval results.

## Architecture

### Components

1. **RAG Service (rag_service.py)**
   - Extended with `search_with_graph_enrichment()` method
   - Integrates with Graph Service for entity extraction and graph queries
   - Formats graph context for LLM consumption
   
2. **Graph Service (graph_service.py)**
   - Performs Named Entity Recognition (NER)
   - Extracts entity relationships
   - Stores entities and relations in Neo4j
   - Provides graph traversal and querying

3. **API Server (api_server.py)**
   - Two new endpoints:
     - `/v1/rag/search/graph-enriched` - Enhanced search with graph context
     - `/v1/rag/query/graph-enriched` - LLM responses with graph-enriched context

### Data Flow

```
User Query
    ↓
1. Vector Similarity Search (Qdrant)
    ↓
2. Extract Entities from Query + Top Results (SpaCy NER)
    ↓
3. Query Knowledge Graph for Entity Neighborhoods (Neo4j Cypher)
    ↓
4. Enrich Vector Results with Graph Context
    ↓
5. Format Combined Context for LLM
    ↓
Response with Vector + Graph Context
```

## Key Features

### 1. Graph-Enriched Search

Combines vector search results with knowledge graph context:

- **Vector Search**: Semantic similarity using embeddings (Nomic Embed v1.5)
- **Entity Extraction**: NER on query and top results
- **Graph Traversal**: Cypher queries to find related entities
- **Context Enrichment**: Augment results with entity relationships

### 2. Multi-Hop Graph Queries

Support for configurable graph traversal depth:

- `graph_depth=1`: Direct neighbors (1-hop)
- `graph_depth=2`: Neighbors of neighbors (2-hop)
- `graph_depth=3`: Extended relationships (3-hop)

### 3. Relationship Types

The system tracks various relationship types:

- `WORKS_ON`: Person → Project
- `RELATES_TO`: General associations
- `CAUSED_BY`: Problem → Concept/Action
- `SOLVED_BY`: Problem → Person/Concept
- `LEARNED_FROM`: Lesson → Problem/Project

### 4. Context Formatting

Graph context is formatted into human-readable text for LLM prompts:

```
Knowledge Graph Entities:
  - John Smith (Person) with 3 related entities
  - TensorFlow (Project) with 5 related entities

Entity Relationships:
  John Smith:
    - WORKS_ON → TensorFlow (Project)
    - RELATES_TO → Mary Johnson (Person)
```

## API Reference

### POST /v1/rag/search/graph-enriched

Graph-enriched search endpoint.

**Request Body:**
```json
{
  "query": "Who works on machine learning projects?",
  "limit": 10,
  "filters": {"category": "research"},
  "graph_depth": 1,
  "graph_limit": 10,
  "include_entity_context": true
}
```

**Response:**
```json
{
  "query": "Who works on machine learning projects?",
  "vector_results": [
    {
      "id": "uuid",
      "score": 0.85,
      "text": "...",
      "metadata": {...},
      "graph_entities": [
        {
          "entity": "John Smith",
          "type": "Person",
          "neighbor_count": 3,
          "neighbors": [...]
        }
      ]
    }
  ],
  "graph_context": {
    "entities": [...],
    "relationships": [...],
    "subgraphs": [...]
  },
  "enriched": true,
  "stats": {
    "vector_results_count": 10,
    "entities_found": 15,
    "entities_in_graph": 8,
    "relationships_found": 12,
    "subgraphs": 5
  }
}
```

### POST /v1/rag/query/graph-enriched

Graph-enriched query endpoint with LLM response generation.

**Request Body:**
```json
{
  "query": "Tell me about researchers working on transformers",
  "k": 5,
  "graph_depth": 2,
  "graph_limit": 15,
  "temperature": 0.7,
  "max_tokens": 2048,
  "include_context": true
}
```

**Response:**
```json
{
  "id": "rag-graph-xxxx",
  "object": "rag.graph.query.completion",
  "created": 1234567890,
  "query": "Tell me about researchers working on transformers",
  "vector_context": [...],
  "graph_context": {...},
  "graph_context_formatted": "Knowledge Graph Entities:\n...",
  "response": "Based on the context...",
  "usage": {
    "prompt_tokens": 500,
    "completion_tokens": 300,
    "total_tokens": 800
  },
  "retrieval_stats": {
    "chunks_retrieved": 5,
    "entities_in_graph": 8,
    "relationships_found": 12,
    "retrieval_time_ms": 150.5,
    "generation_time_ms": 800.2,
    "total_time_ms": 950.7,
    "top_score": 0.89,
    "avg_score": 0.76
  }
}
```

## Usage Examples

### Python SDK Usage

```python
from rag_service import RAGIngestionService
from graph_service import GraphService

# Initialize services
graph_service = GraphService(
    neo4j_uri="bolt://localhost:7687",
    neo4j_user="neo4j",
    neo4j_password="neo4j_password"
)

rag_service = RAGIngestionService(
    qdrant_host="localhost",
    qdrant_port=6333,
    graph_service=graph_service  # Enable graph enrichment
)

# Ingest document to both vector DB and graph
result = rag_service.ingest_document(
    text="John works on TensorFlow at Google...",
    metadata={"title": "ML Team"}
)

graph_service.process_document(
    text="John works on TensorFlow at Google...",
    document_id=result["document_id"],
    metadata={"title": "ML Team"}
)

# Graph-enriched search
enriched_results = rag_service.search_with_graph_enrichment(
    query="Who works on ML frameworks?",
    limit=5,
    graph_depth=2,
    graph_limit=15
)

# Format graph context for LLM
graph_context_str = rag_service.format_graph_context_for_llm(
    enriched_results["graph_context"]
)

print(graph_context_str)
```

### HTTP API Usage

```bash
# Graph-enriched search
curl -X POST http://localhost:8000/v1/rag/search/graph-enriched \
  -H "Content-Type: application/json" \
  -d '{
    "query": "machine learning researchers",
    "limit": 5,
    "graph_depth": 2,
    "graph_limit": 10
  }'

# Graph-enriched query with LLM response
curl -X POST http://localhost:8000/v1/rag/query/graph-enriched \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What are the relationships between AI researchers?",
    "k": 5,
    "graph_depth": 2,
    "graph_limit": 15,
    "temperature": 0.7
  }'
```

## Performance Considerations

### Optimization Tips

1. **Graph Depth**: Keep `graph_depth` ≤ 2 for most queries
   - Depth 1: Fast, direct relationships (~100-200ms)
   - Depth 2: Moderate, multi-hop queries (~200-500ms)
   - Depth 3: Slower, extensive traversal (>500ms)

2. **Graph Limit**: Adjust based on entity density
   - Low limit (5-10): Focused context, faster
   - High limit (20-50): Comprehensive but slower

3. **Entity Filtering**: Use metadata filters to reduce search space

4. **Caching**: Consider caching frequently queried graph patterns

### Performance Metrics

Typical latencies (on sample workload):

- Vector search only: 50-100ms
- Graph enrichment (depth=1): +50-100ms
- Graph enrichment (depth=2): +100-200ms
- LLM generation: 500-1500ms
- **Total (enriched query)**: 600-1800ms

## Configuration

### Environment Variables

```bash
# Neo4j Configuration
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=neo4j_password

# Qdrant Configuration
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_COLLECTION=documents
```

### Graph Schema

**Node Types:**
- Project
- Person
- Concept
- Document
- Problem
- Lesson

**Relationship Types:**
- WORKS_ON (Person → Project)
- RELATES_TO (Any → Any)
- CAUSED_BY (Problem → Concept/Action)
- SOLVED_BY (Problem → Person/Concept)
- LEARNED_FROM (Lesson → Problem/Project)

## Testing

Run the test suite:

```bash
# Unit tests
python -m pytest test_rag_graph_enrichment.py -v

# Run example
python examples/rag_graph_enriched_example.py

# API example
python examples/rag_graph_api_example.py
```

## Benefits

### 1. Enhanced Context Understanding

- **Vector Search**: Semantic similarity
- **Graph Context**: Explicit relationships
- **Combined**: Richer, more accurate context

### 2. Multi-Hop Reasoning

- Discover indirect relationships
- Traverse entity networks
- Find hidden connections

### 3. Structured Knowledge

- Formal entity relationships
- Typed connections
- Query-able graph structure

### 4. Explainable Retrieval

- Clear entity extraction
- Explicit relationship paths
- Traceable context sources

## Limitations

1. **Dependency on Neo4j**: Requires Neo4j instance
2. **Entity Extraction Quality**: Depends on NER accuracy
3. **Graph Population**: Requires upfront entity/relation extraction
4. **Latency**: Additional overhead from graph queries
5. **Memory**: Graph traversal can be memory-intensive

## Future Enhancements

1. **Graph Embeddings**: Use graph neural networks for entity embeddings
2. **Hybrid Ranking**: Combine vector and graph scores
3. **Temporal Relationships**: Add time-aware graph queries
4. **Dynamic Graphs**: Real-time graph updates
5. **Graph Summarization**: Compress large subgraphs
6. **Cross-Document Links**: Automatic entity linking across documents

## References

- RAG Service: `rag_service.py`
- Graph Service: `graph_service.py`
- API Endpoints: `api_server.py`
- Examples: `examples/rag_graph_enriched_example.py`, `examples/rag_graph_api_example.py`
- Tests: `test_rag_graph_enrichment.py`
