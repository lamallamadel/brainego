# Knowledge Graph Service

## Overview

The Knowledge Graph Service provides automatic entity extraction, relation construction, and graph-based knowledge management using Neo4j Community Edition. It combines Named Entity Recognition (NER) with co-occurrence analysis and explicit pattern matching to build a rich knowledge graph from unstructured text.

## Features

- **Named Entity Recognition (NER)**: SpaCy-based entity extraction
- **Relation Construction**: 
  - Co-occurrence analysis (entities appearing together)
  - Explicit pattern matching (e.g., "X works on Y")
- **Graph Schema**: Predefined node types and relationships
- **Full-Text Search**: Search entities by name and description
- **Graph Traversal**: Find neighbors and paths between entities
- **Cypher Queries**: Full Neo4j Cypher query support

## Graph Schema

### Node Types

1. **Project**: Software projects, research initiatives, products
2. **Person**: Individuals, team members, contributors
3. **Concept**: Ideas, technologies, methodologies, principles
4. **Document**: Reports, papers, documentation, articles
5. **Problem**: Issues, bugs, challenges, obstacles
6. **Lesson**: Insights, takeaways, best practices

### Relationship Types

1. **WORKS_ON**: Person → Project
2. **RELATES_TO**: Any → Any (general association)
3. **CAUSED_BY**: Problem → Concept/Action
4. **SOLVED_BY**: Problem → Person/Concept
5. **LEARNED_FROM**: Lesson → Problem/Project

## Architecture

```
┌─────────────────────────────────────────────────────┐
│              Text Document Input                    │
└───────────────────┬─────────────────────────────────┘
                    │
    ┌───────────────▼────────────────┐
    │     NER Pipeline (SpaCy)       │
    │  - Named Entity Recognition    │
    │  - Noun Chunk Extraction       │
    │  - Entity Type Mapping         │
    └───────────────┬────────────────┘
                    │
                    ├──────────────────────────┐
                    │                          │
    ┌───────────────▼────────────┐  ┌─────────▼──────────┐
    │  Co-occurrence Analysis    │  │  Pattern Matching   │
    │  - Sentence windows        │  │  - Explicit rules   │
    │  - Entity proximity        │  │  - Verb patterns    │
    └───────────────┬────────────┘  └─────────┬──────────┘
                    │                          │
                    └──────────┬───────────────┘
                               │
                ┌──────────────▼───────────────┐
                │   Relation Construction      │
                │   - Type inference           │
                │   - Confidence scoring       │
                │   - Deduplication            │
                └──────────────┬───────────────┘
                               │
                ┌──────────────▼───────────────┐
                │      Neo4j Graph DB          │
                │   - Nodes + Properties       │
                │   - Relationships            │
                │   - Embeddings               │
                │   - Full-text index          │
                └──────────────────────────────┘
```

## API Endpoints

### 1. Process Document

Extract entities and relations from text and add to graph.

**Endpoint**: `POST /graph/process`

**Request**:
```json
{
  "text": "Alice works on the Machine Learning Project...",
  "document_id": "ml_project_001",
  "metadata": {
    "title": "ML Project Report",
    "author": "Team ML",
    "date": "2024-01-15"
  }
}
```

**Response**:
```json
{
  "status": "success",
  "document_id": "ml_project_001",
  "entities_extracted": 15,
  "entities_added": 12,
  "relations_extracted": 8,
  "relations_added": 8,
  "relations_by_method": {
    "co-occurrence": 5,
    "explicit": 3
  }
}
```

### 2. Query Graph

Execute Cypher queries on the knowledge graph.

**Endpoint**: `POST /graph/query`

**Request**:
```json
{
  "query": "MATCH (p:Person)-[:WORKS_ON]->(proj:Project) RETURN p.name, proj.name",
  "parameters": {}
}
```

**Response**:
```json
{
  "status": "success",
  "results": [
    {"p.name": "Alice", "proj.name": "Machine Learning Project"},
    {"p.name": "Bob", "proj.name": "Machine Learning Project"}
  ],
  "count": 2
}
```

### 3. Get Neighbors

Find entities connected to a given entity.

**Endpoint**: `GET /graph/neighbors/{entity}`

**Query Parameters**:
- `entity_type`: Filter by entity type (optional)
- `relation_types`: Comma-separated relation types (optional)
- `max_depth`: Maximum traversal depth (default: 1)
- `limit`: Maximum results (default: 50)

**Example**:
```
GET /graph/neighbors/Alice?entity_type=Person&max_depth=2&limit=20
```

**Response**:
```json
{
  "entity": "Alice",
  "entity_type": "Person",
  "neighbors_count": 5,
  "neighbors": [
    {
      "name": "Machine Learning Project",
      "type": "Project",
      "relation_types": ["WORKS_ON"],
      "distance": 1
    },
    {
      "name": "Bob",
      "type": "Person",
      "relation_types": ["WORKS_ON", "WORKS_ON"],
      "distance": 2
    }
  ]
}
```

### 4. Search Entities

Full-text search across entity names and descriptions.

**Endpoint**: `POST /graph/search`

**Request**:
```json
{
  "search_text": "machine learning",
  "entity_types": ["Concept", "Project"],
  "limit": 10
}
```

**Response**:
```json
{
  "search_text": "machine learning",
  "results": [
    {
      "name": "Machine Learning Project",
      "type": "Project",
      "score": 2.45,
      "created_at": "2024-01-15T10:30:00",
      "entity_label": "ORG"
    }
  ],
  "count": 1
}
```

### 5. Graph Statistics

Get overall graph statistics.

**Endpoint**: `GET /graph/stats`

**Response**:
```json
{
  "total_nodes": 127,
  "total_relationships": 89,
  "nodes_by_type": {
    "Project": 12,
    "Person": 25,
    "Concept": 58,
    "Document": 8,
    "Problem": 15,
    "Lesson": 9
  },
  "relationships_by_type": {
    "WORKS_ON": 30,
    "RELATES_TO": 35,
    "CAUSED_BY": 10,
    "SOLVED_BY": 8,
    "LEARNED_FROM": 6
  }
}
```

## Entity Extraction Pipeline

### 1. Named Entity Recognition

Uses SpaCy's pre-trained models to identify:
- **PERSON**: Individual names
- **ORG**: Organizations, projects
- **PRODUCT**: Products, technologies
- **EVENT**: Events, problems
- **GPE**: Locations, places
- **CONCEPT**: General concepts

### 2. Noun Chunk Extraction

Extracts multi-word noun phrases as potential concepts:
- "machine learning algorithm"
- "neural network architecture"
- "memory management system"

### 3. Entity Type Mapping

Maps SpaCy entity types to graph node types:
- PERSON → Person
- ORG, PRODUCT → Project
- EVENT → Problem
- Other → Concept

## Relation Construction

### Co-occurrence Method

Identifies relations based on entity proximity:
- Entities in same sentence: high confidence
- Entities within N-sentence window: medium confidence
- Uses configurable window size (default: 3 sentences)

**Example**:
```
"Alice works on the ML Project. Bob also contributes."
→ Alice WORKS_ON ML Project
→ Bob WORKS_ON ML Project
→ Alice RELATES_TO Bob (co-occurrence)
```

### Pattern Matching Method

Uses regex patterns to detect explicit relations:

**WORKS_ON patterns**:
- "X works on Y"
- "X developed Y"
- "X is working on Y"

**CAUSED_BY patterns**:
- "X caused by Y"
- "X due to Y"
- "X resulted from Y"

**SOLVED_BY patterns**:
- "X solved by Y"
- "X fixed by Y"
- "X resolved by Y"

**LEARNED_FROM patterns**:
- "X learned from Y"
- "lesson from Y"
- "X derived from Y"

## Example Cypher Queries

### Find all projects and their contributors
```cypher
MATCH (p:Person)-[:WORKS_ON]->(proj:Project)
RETURN proj.name as project, 
       collect(p.name) as contributors
```

### Find problems and their solutions
```cypher
MATCH (prob:Problem)-[:SOLVED_BY]->(solver)
RETURN prob.name as problem,
       solver.name as solution,
       labels(solver)[0] as solution_type
```

### Find related concepts (depth 2)
```cypher
MATCH (c1:Concept {name: "Machine Learning"})-[:RELATES_TO*1..2]-(c2:Concept)
RETURN DISTINCT c2.name as related_concept
```

### Find shortest path between entities
```cypher
MATCH p = shortestPath(
  (start:Person {name: "Alice"})-[*]-(end:Person {name: "Bob"})
)
RETURN [node in nodes(p) | node.name] as path,
       length(p) as distance
```

### Find lessons from specific project
```cypher
MATCH (lesson:Lesson)-[:LEARNED_FROM]->(proj:Project {name: "ML Project"})
RETURN lesson.name
```

### Find unsolved problems
```cypher
MATCH (prob:Problem)
WHERE NOT (prob)-[:SOLVED_BY]->()
RETURN prob.name as unsolved
```

## Configuration

### Environment Variables

```bash
# Neo4j Connection
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=neo4j_password

# NLP Models
SPACY_MODEL=en_core_web_sm
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
```

### Docker Compose

Neo4j Community is included in `docker-compose.yaml`:

```yaml
neo4j:
  image: neo4j:5.15-community
  ports:
    - "7474:7474"  # Browser UI
    - "7687:7687"  # Bolt protocol
  environment:
    - NEO4J_AUTH=neo4j/neo4j_password
  volumes:
    - neo4j-data:/data
```

## Usage Examples

### Python Client

```python
import httpx

# Process a document
document = {
    "text": "Alice works on the AI project...",
    "document_id": "doc_001",
    "metadata": {"title": "AI Project"}
}

with httpx.Client() as client:
    response = client.post(
        "http://localhost:8000/graph/process",
        json=document
    )
    result = response.json()
    print(f"Entities: {result['entities_extracted']}")
    print(f"Relations: {result['relations_extracted']}")
```

### cURL

```bash
# Process document
curl -X POST http://localhost:8000/graph/process \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Alice works on ML project",
    "document_id": "doc_001"
  }'

# Query graph
curl -X POST http://localhost:8000/graph/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "MATCH (p:Person) RETURN p.name LIMIT 10"
  }'

# Get neighbors
curl "http://localhost:8000/graph/neighbors/Alice?max_depth=2"

# Search entities
curl -X POST http://localhost:8000/graph/search \
  -H "Content-Type: application/json" \
  -d '{
    "search_text": "machine learning",
    "limit": 10
  }'

# Get statistics
curl http://localhost:8000/graph/stats
```

## Performance Considerations

### Indexing

The service automatically creates:
- Uniqueness constraints on entity names
- B-tree indexes for faster lookups
- Full-text search indexes for entity search

### Batching

For large document collections, process in batches:
```python
documents = [...]  # Large list
batch_size = 10

for i in range(0, len(documents), batch_size):
    batch = documents[i:i+batch_size]
    for doc in batch:
        client.post("/graph/process", json=doc)
```

### Memory Management

Neo4j memory settings (in docker-compose.yaml):
```yaml
environment:
  - NEO4J_dbms_memory_pagecache_size=512M
  - NEO4J_dbms_memory_heap_max__size=1G
```

## Testing

Run the test suite:

```bash
# Basic tests
python test_graph.py

# Example usage
python examples/graph_example.py
```

## Neo4j Browser

Access the Neo4j Browser UI:
- URL: http://localhost:7474
- Username: neo4j
- Password: neo4j_password

### Useful Browser Queries

```cypher
// View all node types
CALL db.labels()

// View all relationship types
CALL db.relationshipTypes()

// Count nodes by type
MATCH (n) RETURN labels(n)[0] as type, count(*) as count

// Visualize a subgraph
MATCH (p:Person)-[r]->(proj:Project)
RETURN p, r, proj
LIMIT 25
```

## Troubleshooting

### Connection Issues

```python
# Test Neo4j connection
from neo4j import GraphDatabase

driver = GraphDatabase.driver(
    "bolt://localhost:7687",
    auth=("neo4j", "neo4j_password")
)

with driver.session() as session:
    result = session.run("RETURN 1 as num")
    print(result.single()["num"])  # Should print 1

driver.close()
```

### SpaCy Model Not Found

```bash
# Download the model
python -m spacy download en_core_web_sm

# For better accuracy, use larger model
python -m spacy download en_core_web_md
```

### Memory Issues

If Neo4j runs out of memory:
1. Increase heap size in docker-compose.yaml
2. Reduce batch size for processing
3. Add pagination to queries

## Best Practices

1. **Document IDs**: Use meaningful, unique identifiers
2. **Metadata**: Include rich metadata for better filtering
3. **Batch Processing**: Process large collections in batches
4. **Query Optimization**: Use indexed properties in WHERE clauses
5. **Relation Confidence**: Favor explicit > co-occurrence relations
6. **Graph Cleanup**: Periodically remove orphaned nodes
7. **Backup**: Regular Neo4j database backups

## Integration with Other Services

### RAG Integration

Combine graph context with RAG retrieval:
```python
# 1. Search graph for relevant entities
neighbors = client.get(f"/graph/neighbors/{entity}")

# 2. Use entity names in RAG query
entity_names = [n["name"] for n in neighbors["neighbors"]]
query = f"Information about {', '.join(entity_names)}"

# 3. Perform RAG query
rag_result = client.post("/v1/rag/query", json={"query": query})
```

### Memory Integration

Store entity relationships in memory service:
```python
# Extract entity facts for memory
entities = process_result["entities"]
messages = [
    {"role": "user", "content": f"Tell me about {entity['name']}"},
    {"role": "assistant", "content": f"Entity details..."}
]

client.post("/memory/add", json={"messages": messages})
```

## Future Enhancements

- [ ] Temporal graphs (time-aware relationships)
- [ ] Graph embeddings (node2vec, graph neural networks)
- [ ] Automatic relation type classification
- [ ] Entity disambiguation and resolution
- [ ] Graph-based recommendations
- [ ] Subgraph pattern mining
- [ ] Community detection algorithms
- [ ] Graph visualization API

## References

- [Neo4j Documentation](https://neo4j.com/docs/)
- [SpaCy Documentation](https://spacy.io/usage)
- [Cypher Query Language](https://neo4j.com/docs/cypher-manual/)
- [Graph Data Science](https://neo4j.com/docs/graph-data-science/)
