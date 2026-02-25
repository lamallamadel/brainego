# Knowledge Graph - Quick Start Guide

## Prerequisites

- Docker and Docker Compose installed
- Python 3.9+ (for local testing)
- 2GB+ available RAM for Neo4j

## 1. Start Services

```bash
# Start all services including Neo4j
docker compose up -d

# Check Neo4j is healthy
docker compose ps neo4j

# View Neo4j logs
docker compose logs neo4j
```

## 2. Access Neo4j Browser

Open http://localhost:7474 in your browser:
- Username: `neo4j`
- Password: `neo4j_password`

## 3. Process Your First Document

```bash
curl -X POST http://localhost:8000/graph/process \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Alice works on the Machine Learning Project. Bob also contributes to this project. The project focuses on neural networks and deep learning.",
    "document_id": "ml_project_001",
    "metadata": {
      "title": "ML Project Overview",
      "date": "2024-01-15"
    }
  }'
```

Expected response:
```json
{
  "status": "success",
  "document_id": "ml_project_001",
  "entities_extracted": 8,
  "entities_added": 8,
  "relations_extracted": 5,
  "relations_added": 5,
  "relations_by_method": {
    "co-occurrence": 3,
    "explicit": 2
  }
}
```

## 4. Query the Graph

### Find all people
```bash
curl -X POST http://localhost:8000/graph/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "MATCH (p:Person) RETURN p.name as name"
  }'
```

### Find who works on what
```bash
curl -X POST http://localhost:8000/graph/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "MATCH (p:Person)-[:WORKS_ON]->(proj:Project) RETURN p.name as person, proj.name as project"
  }'
```

## 5. Find Entity Neighbors

```bash
# Get Alice's connections
curl "http://localhost:8000/graph/neighbors/Alice?max_depth=2&limit=10"

# Get project connections
curl "http://localhost:8000/graph/neighbors/Machine%20Learning%20Project?entity_type=Project"
```

## 6. Search Entities

```bash
curl -X POST http://localhost:8000/graph/search \
  -H "Content-Type: application/json" \
  -d '{
    "search_text": "machine learning",
    "limit": 5
  }'
```

## 7. Get Graph Statistics

```bash
curl http://localhost:8000/graph/stats
```

## 8. Run Examples

```bash
# Install dependencies if running locally
pip install -r requirements.txt

# Download SpaCy model
python -m spacy download en_core_web_sm

# Run comprehensive examples
python examples/graph_example.py

# Run test suite
python test_graph.py
```

## 9. Explore in Neo4j Browser

Open http://localhost:7474 and run these queries:

### Visualize the graph
```cypher
MATCH (n)-[r]->(m)
RETURN n, r, m
LIMIT 50
```

### Count nodes by type
```cypher
MATCH (n)
RETURN labels(n)[0] as type, count(*) as count
ORDER BY count DESC
```

### Find all relationships
```cypher
MATCH ()-[r]->()
RETURN type(r) as relationship_type, count(r) as count
ORDER BY count DESC
```

## 10. Process More Documents

```bash
# Document about problems and solutions
curl -X POST http://localhost:8000/graph/process \
  -H "Content-Type: application/json" \
  -d '{
    "text": "The team encountered a memory leak problem. This problem was caused by inefficient tensor operations. Charlie solved this problem by optimizing the memory management code.",
    "document_id": "problem_report_001"
  }'

# Document about lessons learned
curl -X POST http://localhost:8000/graph/process \
  -H "Content-Type: application/json" \
  -d '{
    "text": "An important lesson learned from this project: always profile your code before optimization. This lesson came from spending weeks optimizing the wrong components.",
    "document_id": "lessons_001"
  }'
```

## Common Use Cases

### 1. Find Project Contributors

```bash
curl -X POST http://localhost:8000/graph/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "MATCH (p:Person)-[:WORKS_ON]->(proj:Project {name: $project_name}) RETURN p.name as contributor",
    "parameters": {"project_name": "Machine Learning Project"}
  }'
```

### 2. Find Problems and Solutions

```bash
curl -X POST http://localhost:8000/graph/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "MATCH (prob:Problem)-[:SOLVED_BY]->(solver) RETURN prob.name as problem, solver.name as solution, labels(solver)[0] as solution_type"
  }'
```

### 3. Find Related Concepts

```bash
curl -X POST http://localhost:8000/graph/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "MATCH (c1:Concept {name: $concept})-[:RELATES_TO*1..2]-(c2:Concept) RETURN DISTINCT c2.name as related_concept LIMIT 10",
    "parameters": {"concept": "neural networks"}
  }'
```

### 4. Find Lessons from Projects

```bash
curl -X POST http://localhost:8000/graph/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "MATCH (lesson:Lesson)-[:LEARNED_FROM]->(source) RETURN lesson.name as lesson, source.name as source, labels(source)[0] as source_type"
  }'
```

## Python Client Example

```python
import httpx

API_BASE_URL = "http://localhost:8000"

# Process document
document = {
    "text": "Alice works on the AI project. The project uses TensorFlow and PyTorch.",
    "document_id": "ai_project_001",
    "metadata": {"title": "AI Project", "team": "ML Team"}
}

with httpx.Client() as client:
    # Process
    response = client.post(f"{API_BASE_URL}/graph/process", json=document)
    result = response.json()
    print(f"✓ Processed: {result['entities_added']} entities, {result['relations_added']} relations")
    
    # Query
    query = {
        "query": "MATCH (p:Person)-[:WORKS_ON]->(proj:Project) RETURN p.name, proj.name"
    }
    response = client.post(f"{API_BASE_URL}/graph/query", json=query)
    results = response.json()
    print(f"✓ Query results: {results['count']} records")
    
    # Get neighbors
    response = client.get(f"{API_BASE_URL}/graph/neighbors/Alice")
    neighbors = response.json()
    print(f"✓ Found {neighbors['neighbors_count']} neighbors")
    
    # Search
    search = {"search_text": "AI project", "limit": 5}
    response = client.post(f"{API_BASE_URL}/graph/search", json=search)
    results = response.json()
    print(f"✓ Search found {results['count']} entities")
    
    # Stats
    response = client.get(f"{API_BASE_URL}/graph/stats")
    stats = response.json()
    print(f"✓ Graph has {stats['total_nodes']} nodes and {stats['total_relationships']} relationships")
```

## Troubleshooting

### Neo4j not starting?

```bash
# Check container status
docker compose ps neo4j

# View logs
docker compose logs neo4j

# Restart
docker compose restart neo4j
```

### Connection refused?

```bash
# Check if Neo4j is listening
docker compose exec neo4j cypher-shell -u neo4j -p neo4j_password "RETURN 1"

# Verify port mappings
docker compose port neo4j 7687
```

### SpaCy model not found?

```bash
# Inside the container
docker compose exec api-server python -m spacy download en_core_web_sm

# Or rebuild with model
docker compose build api-server
docker compose up -d api-server
```

### Out of memory?

Increase Neo4j memory in `docker-compose.yaml`:

```yaml
neo4j:
  environment:
    - NEO4J_dbms_memory_heap_max__size=2G
    - NEO4J_dbms_memory_pagecache_size=1G
```

Then restart:
```bash
docker compose up -d neo4j
```

## Next Steps

1. Read the full [GRAPH_README.md](GRAPH_README.md) for detailed documentation
2. Explore example queries in [examples/graph_example.py](examples/graph_example.py)
3. Run the test suite: `python test_graph.py`
4. Integrate with RAG and Memory services
5. Build custom Cypher queries for your use case

## Resources

- Neo4j Browser: http://localhost:7474
- API Documentation: http://localhost:8000/docs
- Graph Stats: http://localhost:8000/graph/stats
- Health Check: http://localhost:8000/health
