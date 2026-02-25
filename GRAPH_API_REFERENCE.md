# Knowledge Graph API Reference

Complete API reference for the Knowledge Graph service endpoints.

## Base URL

```
http://localhost:8000
```

---

## Endpoints

### 1. POST /graph/process

Process a document to extract entities and relations, then add to the knowledge graph.

#### Request

**Headers:**
```
Content-Type: application/json
```

**Body:**
```json
{
  "text": "string (required) - Text content to process",
  "document_id": "string (optional) - Unique document identifier",
  "metadata": {
    "key": "value (optional) - Additional metadata"
  }
}
```

#### Response

**Status:** 200 OK

```json
{
  "status": "success",
  "document_id": "string - Document ID (generated if not provided)",
  "entities_extracted": 0,
  "entities_added": 0,
  "relations_extracted": 0,
  "relations_added": 0,
  "relations_by_method": {
    "co-occurrence": 0,
    "explicit": 0
  }
}
```

#### Example

```bash
curl -X POST http://localhost:8000/graph/process \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Alice works on the ML Project. Bob also contributes.",
    "document_id": "doc_001",
    "metadata": {"team": "ML Team", "date": "2024-01-15"}
  }'
```

---

### 2. POST /graph/query

Execute a Cypher query on the knowledge graph.

#### Request

**Headers:**
```
Content-Type: application/json
```

**Body:**
```json
{
  "query": "string (required) - Cypher query string",
  "parameters": {
    "param_name": "param_value (optional) - Query parameters"
  }
}
```

#### Response

**Status:** 200 OK

```json
{
  "status": "success",
  "results": [
    {
      "column1": "value1",
      "column2": "value2"
    }
  ],
  "count": 0
}
```

#### Example

```bash
curl -X POST http://localhost:8000/graph/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "MATCH (p:Person {name: $name})-[:WORKS_ON]->(proj:Project) RETURN proj.name as project",
    "parameters": {"name": "Alice"}
  }'
```

#### Common Queries

**Find all people:**
```cypher
MATCH (p:Person) RETURN p.name as name
```

**Find project contributors:**
```cypher
MATCH (p:Person)-[:WORKS_ON]->(proj:Project)
RETURN proj.name as project, collect(p.name) as contributors
```

**Find problems and solutions:**
```cypher
MATCH (prob:Problem)-[:SOLVED_BY]->(solver)
RETURN prob.name as problem, solver.name as solution, labels(solver)[0] as type
```

**Find related concepts:**
```cypher
MATCH (c1:Concept)-[:RELATES_TO*1..2]-(c2:Concept)
WHERE c1.name = $concept_name
RETURN DISTINCT c2.name as related
```

---

### 3. GET /graph/neighbors/{entity}

Get entities connected to a specified entity.

#### Path Parameters

- `entity` (string, required): Name of the entity (URL-encoded)

#### Query Parameters

- `entity_type` (string, optional): Filter by entity type
  - Values: `Project`, `Person`, `Concept`, `Document`, `Problem`, `Lesson`
- `relation_types` (string, optional): Comma-separated relation types
  - Values: `WORKS_ON`, `RELATES_TO`, `CAUSED_BY`, `SOLVED_BY`, `LEARNED_FROM`
- `max_depth` (integer, optional): Maximum traversal depth (default: 1)
  - Range: 1-5
- `limit` (integer, optional): Maximum number of results (default: 50)
  - Range: 1-1000

#### Response

**Status:** 200 OK

```json
{
  "entity": "string - Entity name",
  "entity_type": "string or null - Entity type filter",
  "neighbors_count": 0,
  "neighbors": [
    {
      "name": "string - Neighbor entity name",
      "type": "string - Neighbor entity type",
      "relation_types": ["string - List of relation types in path"],
      "distance": 0
    }
  ]
}
```

#### Examples

**Basic usage:**
```bash
curl "http://localhost:8000/graph/neighbors/Alice"
```

**With filters:**
```bash
curl "http://localhost:8000/graph/neighbors/Alice?entity_type=Person&max_depth=2&limit=20"
```

**Filter by relation types:**
```bash
curl "http://localhost:8000/graph/neighbors/Alice?relation_types=WORKS_ON,RELATES_TO"
```

---

### 4. POST /graph/search

Search for entities using full-text search.

#### Request

**Headers:**
```
Content-Type: application/json
```

**Body:**
```json
{
  "search_text": "string (required) - Search query text",
  "entity_types": ["string (optional) - List of entity types to filter"],
  "limit": 20
}
```

#### Response

**Status:** 200 OK

```json
{
  "search_text": "string - Original search text",
  "results": [
    {
      "name": "string - Entity name",
      "type": "string - Entity type",
      "score": 0.0,
      "created_at": "string or null - Creation timestamp",
      "entity_label": "string - Original NER label"
    }
  ],
  "count": 0
}
```

#### Examples

**Search all entity types:**
```bash
curl -X POST http://localhost:8000/graph/search \
  -H "Content-Type: application/json" \
  -d '{
    "search_text": "machine learning",
    "limit": 10
  }'
```

**Search specific types:**
```bash
curl -X POST http://localhost:8000/graph/search \
  -H "Content-Type: application/json" \
  -d '{
    "search_text": "optimization",
    "entity_types": ["Concept", "Problem"],
    "limit": 5
  }'
```

---

### 5. GET /graph/stats

Get overall knowledge graph statistics.

#### Request

No parameters required.

#### Response

**Status:** 200 OK

```json
{
  "total_nodes": 0,
  "total_relationships": 0,
  "nodes_by_type": {
    "Project": 0,
    "Person": 0,
    "Concept": 0,
    "Document": 0,
    "Problem": 0,
    "Lesson": 0
  },
  "relationships_by_type": {
    "WORKS_ON": 0,
    "RELATES_TO": 0,
    "CAUSED_BY": 0,
    "SOLVED_BY": 0,
    "LEARNED_FROM": 0
  }
}
```

#### Example

```bash
curl http://localhost:8000/graph/stats
```

---

## Error Responses

All endpoints may return the following error responses:

### 400 Bad Request

Invalid request parameters or malformed JSON.

```json
{
  "detail": "Error message describing the issue"
}
```

### 500 Internal Server Error

Server-side error during processing.

```json
{
  "detail": "Error message describing the issue"
}
```

### 503 Service Unavailable

Neo4j database is not available.

```json
{
  "detail": "Graph query error: Cannot connect to Neo4j"
}
```

---

## Data Models

### Node Types

#### Project
- **Description**: Software projects, research initiatives, products
- **Properties**: name, created_at, updated_at, embedding, entity_label, source_document

#### Person
- **Description**: Individuals, team members, contributors
- **Properties**: name, created_at, updated_at, embedding, entity_label, source_document

#### Concept
- **Description**: Ideas, technologies, methodologies, principles
- **Properties**: name, created_at, updated_at, embedding, entity_label, source_document

#### Document
- **Description**: Reports, papers, documentation, articles
- **Properties**: name, title, created_at, metadata

#### Problem
- **Description**: Issues, bugs, challenges, obstacles
- **Properties**: name, created_at, updated_at, embedding, entity_label, source_document

#### Lesson
- **Description**: Insights, takeaways, best practices
- **Properties**: name, created_at, updated_at, embedding, entity_label, source_document

### Relationship Types

#### WORKS_ON
- **Source**: Person
- **Target**: Project
- **Properties**: created_at, updated_at, method, confidence, source_document

#### RELATES_TO
- **Source**: Any
- **Target**: Any
- **Properties**: created_at, updated_at, method, confidence, source_document
- **Description**: General association between entities

#### CAUSED_BY
- **Source**: Problem
- **Target**: Concept/Action
- **Properties**: created_at, updated_at, method, confidence, source_document

#### SOLVED_BY
- **Source**: Problem
- **Target**: Person/Concept
- **Properties**: created_at, updated_at, method, confidence, source_document

#### LEARNED_FROM
- **Source**: Lesson
- **Target**: Problem/Project
- **Properties**: created_at, updated_at, method, confidence, source_document

---

## Rate Limits

Currently, there are no rate limits enforced. However, consider:
- Batch processing for large document collections
- Limiting query complexity for production use
- Implementing pagination for large result sets

---

## Authentication

Currently, no authentication is required. For production:
- Add API key authentication
- Implement role-based access control
- Restrict Cypher query access

---

## Webhooks

Not currently supported. Future enhancement.

---

## Versioning

Current API version: **v1** (implicit in URL structure)

No explicit versioning in URLs yet. Breaking changes will be announced.

---

## SDKs and Libraries

### Python

```python
import httpx

class GraphClient:
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
        self.client = httpx.Client()
    
    def process_document(self, text, document_id=None, metadata=None):
        response = self.client.post(
            f"{self.base_url}/graph/process",
            json={
                "text": text,
                "document_id": document_id,
                "metadata": metadata
            }
        )
        return response.json()
    
    def query(self, cypher_query, parameters=None):
        response = self.client.post(
            f"{self.base_url}/graph/query",
            json={
                "query": cypher_query,
                "parameters": parameters or {}
            }
        )
        return response.json()
    
    def get_neighbors(self, entity, entity_type=None, max_depth=1):
        params = {"max_depth": max_depth}
        if entity_type:
            params["entity_type"] = entity_type
        
        response = self.client.get(
            f"{self.base_url}/graph/neighbors/{entity}",
            params=params
        )
        return response.json()
    
    def search(self, text, entity_types=None, limit=20):
        response = self.client.post(
            f"{self.base_url}/graph/search",
            json={
                "search_text": text,
                "entity_types": entity_types,
                "limit": limit
            }
        )
        return response.json()
    
    def get_stats(self):
        response = self.client.get(f"{self.base_url}/graph/stats")
        return response.json()

# Usage
client = GraphClient()
result = client.process_document("Alice works on ML project")
print(result)
```

### JavaScript/TypeScript

```typescript
class GraphClient {
  constructor(private baseUrl = "http://localhost:8000") {}
  
  async processDocument(
    text: string,
    documentId?: string,
    metadata?: Record<string, any>
  ) {
    const response = await fetch(`${this.baseUrl}/graph/process`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, document_id: documentId, metadata })
    });
    return response.json();
  }
  
  async query(cypherQuery: string, parameters?: Record<string, any>) {
    const response = await fetch(`${this.baseUrl}/graph/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: cypherQuery, parameters })
    });
    return response.json();
  }
  
  async getNeighbors(
    entity: string,
    options?: { entityType?: string; maxDepth?: number }
  ) {
    const params = new URLSearchParams();
    if (options?.entityType) params.set("entity_type", options.entityType);
    if (options?.maxDepth) params.set("max_depth", String(options.maxDepth));
    
    const response = await fetch(
      `${this.baseUrl}/graph/neighbors/${entity}?${params}`
    );
    return response.json();
  }
  
  async search(
    text: string,
    entityTypes?: string[],
    limit = 20
  ) {
    const response = await fetch(`${this.baseUrl}/graph/search`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        search_text: text,
        entity_types: entityTypes,
        limit
      })
    });
    return response.json();
  }
  
  async getStats() {
    const response = await fetch(`${this.baseUrl}/graph/stats`);
    return response.json();
  }
}

// Usage
const client = new GraphClient();
const result = await client.processDocument("Alice works on ML project");
console.log(result);
```

---

## Best Practices

1. **Document IDs**: Use meaningful, unique identifiers
2. **Batch Processing**: Process large collections in batches of 10-50 documents
3. **Query Limits**: Always use LIMIT in Cypher queries
4. **Parameterized Queries**: Use parameters to prevent injection
5. **Error Handling**: Always handle 500 errors and retry
6. **Metadata**: Include rich metadata for better filtering
7. **Entity Types**: Specify entity_types in search for better precision

---

## Support

- Documentation: [GRAPH_README.md](GRAPH_README.md)
- Quick Start: [GRAPH_QUICKSTART.md](GRAPH_QUICKSTART.md)
- Examples: [examples/graph_example.py](examples/graph_example.py)
- Tests: [test_graph.py](test_graph.py)
