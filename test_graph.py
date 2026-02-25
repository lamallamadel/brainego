#!/usr/bin/env python3
"""
Test script for Graph Service functionality.
"""

import os
import sys
import json
import httpx
from typing import Dict, Any

# Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "neo4j_password")


def print_section(title: str):
    """Print a section header."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def print_json(data: Dict[str, Any]):
    """Pretty print JSON data."""
    print(json.dumps(data, indent=2))


def test_graph_process():
    """Test document processing for entity and relation extraction."""
    print_section("Test 1: Process Document for Graph")
    
    sample_text = """
    Alice works on the Machine Learning Project. The project focuses on developing
    neural networks for natural language processing. Bob also works on this project
    and specializes in transformer models.
    
    The team encountered a memory leak problem that was caused by inefficient tensor
    operations. This problem was solved by Charlie, who optimized the memory management.
    
    The lesson learned from this project is that proper profiling is essential for
    performance optimization. This lesson was derived from several debugging sessions.
    """
    
    payload = {
        "text": sample_text,
        "document_id": "ml_project_report_001",
        "metadata": {
            "title": "Machine Learning Project Report",
            "author": "Team ML",
            "date": "2024-01-15"
        }
    }
    
    print("Request payload:")
    print_json(payload)
    
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(f"{API_BASE_URL}/graph/process", json=payload)
            response.raise_for_status()
            result = response.json()
            
            print("\nResponse:")
            print_json(result)
            print(f"\n✓ Document processed successfully")
            print(f"  - Entities extracted: {result['entities_extracted']}")
            print(f"  - Entities added: {result['entities_added']}")
            print(f"  - Relations extracted: {result['relations_extracted']}")
            print(f"  - Relations added: {result['relations_added']}")
            
            return True
    except Exception as e:
        print(f"\n✗ Error: {e}")
        return False


def test_graph_query():
    """Test Cypher query execution."""
    print_section("Test 2: Execute Cypher Query")
    
    queries = [
        {
            "name": "Find all Person nodes",
            "query": "MATCH (p:Person) RETURN p.name as name LIMIT 10",
            "parameters": {}
        },
        {
            "name": "Find WORKS_ON relationships",
            "query": """
                MATCH (person:Person)-[:WORKS_ON]->(project:Project)
                RETURN person.name as person, project.name as project
            """,
            "parameters": {}
        },
        {
            "name": "Find problem solutions",
            "query": """
                MATCH (problem:Problem)-[:SOLVED_BY]->(solver)
                RETURN problem.name as problem, solver.name as solver, labels(solver)[0] as solver_type
            """,
            "parameters": {}
        }
    ]
    
    success_count = 0
    
    for query_info in queries:
        print(f"\nQuery: {query_info['name']}")
        print(f"Cypher: {query_info['query'].strip()}")
        
        payload = {
            "query": query_info["query"],
            "parameters": query_info["parameters"]
        }
        
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(f"{API_BASE_URL}/graph/query", json=payload)
                response.raise_for_status()
                result = response.json()
                
                print(f"\nResults ({result['count']} records):")
                for record in result["results"]:
                    print(f"  {record}")
                
                success_count += 1
        except Exception as e:
            print(f"✗ Error: {e}")
    
    print(f"\n✓ {success_count}/{len(queries)} queries executed successfully")
    return success_count == len(queries)


def test_graph_neighbors():
    """Test getting neighbors of entities."""
    print_section("Test 3: Get Entity Neighbors")
    
    test_cases = [
        {
            "entity": "Alice",
            "entity_type": "Person",
            "max_depth": 1,
            "limit": 20
        },
        {
            "entity": "Machine Learning Project",
            "entity_type": "Project",
            "max_depth": 2,
            "limit": 20
        }
    ]
    
    success_count = 0
    
    for case in test_cases:
        entity = case["entity"]
        params = {
            "entity_type": case.get("entity_type"),
            "max_depth": case.get("max_depth", 1),
            "limit": case.get("limit", 50)
        }
        
        print(f"\nFinding neighbors of: {entity}")
        print(f"Parameters: {params}")
        
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.get(
                    f"{API_BASE_URL}/graph/neighbors/{entity}",
                    params=params
                )
                response.raise_for_status()
                result = response.json()
                
                print(f"\nFound {result['neighbors_count']} neighbors:")
                for neighbor in result["neighbors"][:5]:
                    print(f"  - {neighbor['name']} ({neighbor['type']}) "
                          f"[distance: {neighbor['distance']}, "
                          f"relations: {neighbor['relation_types']}]")
                
                if result['neighbors_count'] > 5:
                    print(f"  ... and {result['neighbors_count'] - 5} more")
                
                success_count += 1
        except Exception as e:
            print(f"✗ Error: {e}")
    
    print(f"\n✓ {success_count}/{len(test_cases)} neighbor queries successful")
    return success_count == len(test_cases)


def test_graph_search():
    """Test entity search."""
    print_section("Test 4: Search Entities")
    
    search_queries = [
        {
            "search_text": "Machine Learning",
            "entity_types": None,
            "limit": 10
        },
        {
            "search_text": "problem",
            "entity_types": ["Problem"],
            "limit": 5
        },
        {
            "search_text": "project",
            "entity_types": ["Project"],
            "limit": 5
        }
    ]
    
    success_count = 0
    
    for query in search_queries:
        print(f"\nSearching for: '{query['search_text']}'")
        if query["entity_types"]:
            print(f"Entity types: {query['entity_types']}")
        
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(f"{API_BASE_URL}/graph/search", json=query)
                response.raise_for_status()
                result = response.json()
                
                print(f"\nFound {result['count']} entities:")
                for entity in result["results"]:
                    print(f"  - {entity['name']} ({entity['type']}) "
                          f"[score: {entity['score']:.2f}]")
                
                success_count += 1
        except Exception as e:
            print(f"✗ Error: {e}")
    
    print(f"\n✓ {success_count}/{len(search_queries)} searches successful")
    return success_count == len(search_queries)


def test_graph_stats():
    """Test graph statistics."""
    print_section("Test 5: Get Graph Statistics")
    
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(f"{API_BASE_URL}/graph/stats")
            response.raise_for_status()
            result = response.json()
            
            print("Graph Statistics:")
            print(f"  Total Nodes: {result['total_nodes']}")
            print(f"  Total Relationships: {result['total_relationships']}")
            
            print("\n  Nodes by Type:")
            for node_type, count in result['nodes_by_type'].items():
                print(f"    - {node_type}: {count}")
            
            print("\n  Relationships by Type:")
            for rel_type, count in result['relationships_by_type'].items():
                print(f"    - {rel_type}: {count}")
            
            print("\n✓ Graph statistics retrieved successfully")
            return True
    except Exception as e:
        print(f"\n✗ Error: {e}")
        return False


def test_additional_documents():
    """Test processing additional documents."""
    print_section("Test 6: Process Additional Documents")
    
    documents = [
        {
            "text": """
            The Data Pipeline Project is a critical infrastructure component. Sarah
            leads this project and works closely with the DevOps team. The pipeline
            handles real-time data processing using Apache Kafka and Spark.
            
            A scalability problem occurred when traffic increased 10x. The problem
            was caused by insufficient partitioning. David solved this by implementing
            dynamic partition allocation.
            """,
            "document_id": "data_pipeline_doc",
            "metadata": {"title": "Data Pipeline Project", "category": "Infrastructure"}
        },
        {
            "text": """
            Key lesson: Always design for scalability from day one. This lesson was
            learned from the Data Pipeline Project incidents. Another lesson is that
            monitoring and alerting must be comprehensive.
            
            The concept of microservices relates to scalability and fault isolation.
            Event-driven architecture is another important concept that relates to
            real-time processing.
            """,
            "document_id": "lessons_learned_doc",
            "metadata": {"title": "Lessons Learned", "category": "Documentation"}
        }
    ]
    
    success_count = 0
    
    for doc in documents:
        print(f"\nProcessing: {doc['metadata']['title']}")
        
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(f"{API_BASE_URL}/graph/process", json=doc)
                response.raise_for_status()
                result = response.json()
                
                print(f"  ✓ Processed: {result['entities_extracted']} entities, "
                      f"{result['relations_extracted']} relations")
                success_count += 1
        except Exception as e:
            print(f"  ✗ Error: {e}")
    
    print(f"\n✓ {success_count}/{len(documents)} documents processed")
    return success_count == len(documents)


def main():
    """Run all graph tests."""
    print("\n" + "="*60)
    print("  Knowledge Graph Service Test Suite")
    print("="*60)
    print(f"\nAPI Base URL: {API_BASE_URL}")
    print(f"Neo4j URI: {NEO4J_URI}")
    
    tests = [
        ("Process Document", test_graph_process),
        ("Execute Queries", test_graph_query),
        ("Get Neighbors", test_graph_neighbors),
        ("Search Entities", test_graph_search),
        ("Graph Statistics", test_graph_stats),
        ("Additional Documents", test_additional_documents),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n✗ Test '{test_name}' failed with exception: {e}")
            results.append((test_name, False))
    
    # Summary
    print_section("Test Summary")
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
