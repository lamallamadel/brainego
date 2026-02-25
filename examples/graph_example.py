#!/usr/bin/env python3
"""
Example usage of the Knowledge Graph API.

This script demonstrates:
1. Processing documents to extract entities and relations
2. Querying the graph with Cypher
3. Finding entity neighbors
4. Searching for entities
5. Getting graph statistics
"""

import httpx
import json
from typing import Dict, Any


API_BASE_URL = "http://localhost:8000"


def print_section(title: str):
    """Print section header."""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


def print_response(response: Dict[str, Any]):
    """Pretty print API response."""
    print(json.dumps(response, indent=2))


def example_1_process_documents():
    """Example 1: Process documents to build knowledge graph."""
    print_section("Example 1: Process Documents")
    
    documents = [
        {
            "text": """
            Alice and Bob are working on the Quantum Computing Research Project.
            The project aims to develop quantum algorithms for cryptography.
            Alice specializes in quantum entanglement while Bob focuses on
            quantum error correction.
            
            The team encountered a decoherence problem that was caused by
            environmental noise. This problem was solved by implementing better
            isolation techniques.
            
            An important lesson learned: quantum systems require extreme isolation
            from the environment. This lesson came from months of experimentation.
            """,
            "document_id": "quantum_project_001",
            "metadata": {
                "title": "Quantum Computing Research Project",
                "team": "Quantum Lab",
                "date": "2024-01-20"
            }
        },
        {
            "text": """
            The Artificial Intelligence Ethics Initiative is led by Carol.
            The initiative explores ethical implications of AI systems.
            David works on bias detection in machine learning models.
            
            The concept of algorithmic fairness relates to ethical AI development.
            Transparency and explainability are key concepts in this domain.
            
            A major problem identified was bias amplification in training data.
            This problem was caused by historical biases in datasets. Carol and
            David are working together to solve this through careful data curation.
            """,
            "document_id": "ai_ethics_001",
            "metadata": {
                "title": "AI Ethics Initiative",
                "team": "Ethics Lab",
                "date": "2024-01-22"
            }
        }
    ]
    
    with httpx.Client(timeout=30.0) as client:
        for doc in documents:
            print(f"Processing: {doc['metadata']['title']}")
            response = client.post(f"{API_BASE_URL}/graph/process", json=doc)
            result = response.json()
            
            print(f"✓ Entities: {result['entities_extracted']} extracted, "
                  f"{result['entities_added']} added")
            print(f"✓ Relations: {result['relations_extracted']} extracted, "
                  f"{result['relations_added']} added")
            print(f"  Methods: {result['relations_by_method']}\n")


def example_2_cypher_queries():
    """Example 2: Execute Cypher queries."""
    print_section("Example 2: Execute Cypher Queries")
    
    queries = [
        {
            "name": "Find all people and their projects",
            "query": """
                MATCH (person:Person)-[:WORKS_ON]->(project:Project)
                RETURN person.name as person, project.name as project
                ORDER BY person
            """
        },
        {
            "name": "Find all problems and their causes",
            "query": """
                MATCH (problem:Problem)-[:CAUSED_BY]->(cause)
                RETURN problem.name as problem, 
                       cause.name as cause,
                       labels(cause)[0] as cause_type
            """
        },
        {
            "name": "Find lessons and what they were learned from",
            "query": """
                MATCH (lesson:Lesson)-[:LEARNED_FROM]->(source)
                RETURN lesson.name as lesson,
                       source.name as source,
                       labels(source)[0] as source_type
            """
        },
        {
            "name": "Find concepts and their relationships",
            "query": """
                MATCH (c1:Concept)-[:RELATES_TO]-(c2:Concept)
                RETURN DISTINCT c1.name as concept1, c2.name as concept2
                LIMIT 10
            """
        }
    ]
    
    with httpx.Client(timeout=30.0) as client:
        for query_info in queries:
            print(f"\n{query_info['name']}:")
            print(f"Query: {query_info['query'].strip()}\n")
            
            payload = {"query": query_info["query"], "parameters": {}}
            response = client.post(f"{API_BASE_URL}/graph/query", json=payload)
            result = response.json()
            
            if result["count"] > 0:
                print(f"Results ({result['count']} records):")
                for record in result["results"]:
                    print(f"  {record}")
            else:
                print("  (No results)")


def example_3_find_neighbors():
    """Example 3: Find neighbors of entities."""
    print_section("Example 3: Find Entity Neighbors")
    
    entities = [
        {"name": "Alice", "type": "Person", "depth": 2},
        {"name": "Quantum Computing Research Project", "type": "Project", "depth": 1},
        {"name": "algorithmic fairness", "type": "Concept", "depth": 1},
    ]
    
    with httpx.Client(timeout=30.0) as client:
        for entity in entities:
            print(f"\nNeighbors of '{entity['name']}' (depth={entity['depth']}):")
            
            params = {
                "entity_type": entity["type"],
                "max_depth": entity["depth"],
                "limit": 20
            }
            
            response = client.get(
                f"{API_BASE_URL}/graph/neighbors/{entity['name']}",
                params=params
            )
            result = response.json()
            
            if result["neighbors_count"] > 0:
                for neighbor in result["neighbors"]:
                    rels = " -> ".join(neighbor["relation_types"])
                    print(f"  [{neighbor['distance']}] {neighbor['name']} "
                          f"({neighbor['type']}) via {rels}")
            else:
                print("  (No neighbors found)")


def example_4_search_entities():
    """Example 4: Search for entities."""
    print_section("Example 4: Search Entities")
    
    searches = [
        {
            "search_text": "quantum",
            "entity_types": None,
            "limit": 10
        },
        {
            "search_text": "problem",
            "entity_types": ["Problem"],
            "limit": 5
        },
        {
            "search_text": "AI ethics",
            "entity_types": ["Concept", "Project"],
            "limit": 5
        }
    ]
    
    with httpx.Client(timeout=30.0) as client:
        for search in searches:
            print(f"\nSearch: '{search['search_text']}'")
            if search["entity_types"]:
                print(f"Types: {search['entity_types']}")
            
            response = client.post(f"{API_BASE_URL}/graph/search", json=search)
            result = response.json()
            
            if result["count"] > 0:
                print(f"\nResults ({result['count']} entities):")
                for entity in result["results"]:
                    print(f"  [{entity['score']:.2f}] {entity['name']} ({entity['type']})")
            else:
                print("  (No results)")


def example_5_graph_statistics():
    """Example 5: Get graph statistics."""
    print_section("Example 5: Graph Statistics")
    
    with httpx.Client(timeout=30.0) as client:
        response = client.get(f"{API_BASE_URL}/graph/stats")
        stats = response.json()
        
        print(f"Total Nodes: {stats['total_nodes']}")
        print(f"Total Relationships: {stats['total_relationships']}")
        
        print("\nNodes by Type:")
        for node_type, count in sorted(stats['nodes_by_type'].items()):
            if count > 0:
                print(f"  {node_type:15s}: {count:3d}")
        
        print("\nRelationships by Type:")
        for rel_type, count in sorted(stats['relationships_by_type'].items()):
            if count > 0:
                print(f"  {rel_type:15s}: {count:3d}")


def example_6_advanced_queries():
    """Example 6: Advanced graph queries."""
    print_section("Example 6: Advanced Queries")
    
    queries = [
        {
            "name": "Find shortest path between two people",
            "query": """
                MATCH p = shortestPath(
                    (person1:Person {name: $name1})-[*]-(person2:Person {name: $name2})
                )
                RETURN [node in nodes(p) | node.name] as path,
                       length(p) as distance
            """,
            "parameters": {"name1": "Alice", "name2": "Carol"}
        },
        {
            "name": "Find projects with most contributors",
            "query": """
                MATCH (person:Person)-[:WORKS_ON]->(project:Project)
                RETURN project.name as project,
                       count(person) as contributors
                ORDER BY contributors DESC
                LIMIT 5
            """
        },
        {
            "name": "Find problems without solutions",
            "query": """
                MATCH (problem:Problem)
                WHERE NOT (problem)-[:SOLVED_BY]->()
                RETURN problem.name as unsolved_problem
            """
        }
    ]
    
    with httpx.Client(timeout=30.0) as client:
        for query_info in queries:
            print(f"\n{query_info['name']}:")
            
            payload = {
                "query": query_info["query"],
                "parameters": query_info.get("parameters", {})
            }
            
            response = client.post(f"{API_BASE_URL}/graph/query", json=payload)
            result = response.json()
            
            if result["count"] > 0:
                print(f"Results ({result['count']} records):")
                for record in result["results"]:
                    print(f"  {record}")
            else:
                print("  (No results)")


def main():
    """Run all examples."""
    print("\n" + "="*70)
    print("  Knowledge Graph API - Example Usage")
    print("="*70)
    
    try:
        # Check if API is available
        with httpx.Client(timeout=10.0) as client:
            response = client.get(f"{API_BASE_URL}/health")
            response.raise_for_status()
        
        # Run examples
        example_1_process_documents()
        example_2_cypher_queries()
        example_3_find_neighbors()
        example_4_search_entities()
        example_5_graph_statistics()
        example_6_advanced_queries()
        
        print("\n" + "="*70)
        print("  All examples completed successfully!")
        print("="*70 + "\n")
        
    except httpx.ConnectError:
        print(f"\n✗ Error: Cannot connect to API at {API_BASE_URL}")
        print("  Make sure the API server is running.")
    except Exception as e:
        print(f"\n✗ Error: {e}")


if __name__ == "__main__":
    main()
