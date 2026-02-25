# Graph-Enriched RAG Quick Start

## 1-Minute Setup

### Prerequisites
```bash
# Ensure services are running
docker-compose up -d neo4j qdrant
```

### Basic Usage

#### Python SDK

```python
from rag_service import RAGIngestionService
from graph_service import GraphService

# Initialize
graph = GraphService(neo4j_uri="bolt://localhost:7687")
rag = RAGIngestionService(
    qdrant_host="localhost",
    graph_service=graph
)

# Ingest document
result = rag.ingest_document("Alice works on TensorFlow...")
graph.process_document(result["text"], result["document_id"])

# Graph-enriched search
enriched = rag.search_with_graph_enrichment(
    query="Who works on TensorFlow?",
    graph_depth=1
)

print(enriched["stats"])
# {'vector_results_count': 5, 'entities_in_graph': 3, 'relationships_found': 4}
```

#### HTTP API

```bash
# Search with graph enrichment
curl -X POST http://localhost:8000/v1/rag/search/graph-enriched \
  -H "Content-Type: application/json" \
  -d '{"query": "machine learning", "graph_depth": 1}'

# Query with LLM response
curl -X POST http://localhost:8000/v1/rag/query/graph-enriched \
  -H "Content-Type: application/json" \
  -d '{"query": "Tell me about AI researchers", "k": 5, "graph_depth": 2}'
```

## Key Parameters

| Parameter | Default | Range | Description |
|-----------|---------|-------|-------------|
| `graph_depth` | 1 | 1-3 | Graph traversal depth (hops) |
| `graph_limit` | 10 | 1-50 | Max neighbors per entity |
| `k` | 5 | 1-20 | Top-k vector results |
| `limit` | 10 | 1-100 | Max search results |

## Common Patterns

### Pattern 1: Direct Relationships (Fast)
```python
# Find directly connected entities
enriched = rag.search_with_graph_enrichment(
    query="Who works with John?",
    graph_depth=1,  # Direct connections only
    graph_limit=10
)
```

### Pattern 2: Multi-Hop Discovery (Comprehensive)
```python
# Discover indirect relationships
enriched = rag.search_with_graph_enrichment(
    query="What technologies relate to Alice?",
    graph_depth=2,  # Friends of friends
    graph_limit=20
)
```

### Pattern 3: Filtered Search
```python
# Search with metadata filtering
enriched = rag.search_with_graph_enrichment(
    query="research projects",
    filters={"category": "research"},
    graph_depth=1
)
```

## Examples

Run complete examples:

```bash
# Local Python example
python examples/rag_graph_enriched_example.py

# API example
python examples/rag_graph_api_example.py
```

## Troubleshooting

**Issue**: Graph service not available
```python
# Check if graph service is None
if rag.graph_service:
    # Use graph enrichment
    enriched = rag.search_with_graph_enrichment(...)
else:
    # Fallback to standard search
    results = rag.search_documents(...)
```

**Issue**: No graph context returned
- Ensure documents were processed with `graph.process_document()`
- Check that entities were extracted (view Neo4j browser)
- Verify Neo4j is running: `docker-compose ps neo4j`

**Issue**: Slow queries
- Reduce `graph_depth` (use 1 instead of 2)
- Lower `graph_limit` (use 10 instead of 50)
- Add metadata filters to narrow search

## Next Steps

1. Read full documentation: `RAG_GRAPH_ENRICHMENT.md`
2. Review API reference: Section "API Reference"
3. Run tests: `python -m pytest test_rag_graph_enrichment.py`
4. Explore graph in Neo4j Browser: http://localhost:7474

## Architecture

```
Query → [Vector Search] → [Entity Extraction] → [Graph Query] → [Context Enrichment] → Response
           (Qdrant)           (SpaCy NER)          (Neo4j)         (Combine)            (LLM)
```

## Key Benefits

✅ **Richer Context**: Combines semantic + relational
✅ **Multi-Hop**: Discover indirect connections  
✅ **Explainable**: Clear entity relationships
✅ **Scalable**: Efficient graph queries
