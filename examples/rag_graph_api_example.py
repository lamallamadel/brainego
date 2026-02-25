#!/usr/bin/env python3
"""
Example script demonstrating graph-enriched RAG API endpoints.

This script shows how to:
1. Use the /v1/rag/search/graph-enriched endpoint for enhanced search
2. Use the /v1/rag/query/graph-enriched endpoint for augmented responses
3. Compare standard RAG vs graph-enriched RAG results
"""

import httpx
import asyncio
import json
from typing import Dict, List, Any, Optional


API_BASE_URL = "http://localhost:8000"


async def ingest_documents_with_graph(documents: List[Dict[str, Any]]):
    """Ingest documents into both RAG and Graph systems."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        # Ingest to RAG
        rag_response = await client.post(
            f"{API_BASE_URL}/v1/rag/ingest/batch",
            json={"documents": documents}
        )
        rag_response.raise_for_status()
        rag_result = rag_response.json()
        
        # Extract to graph
        graph_results = []
        for doc in documents:
            graph_response = await client.post(
                f"{API_BASE_URL}/v1/graph/process",
                json={
                    "text": doc["text"],
                    "metadata": doc.get("metadata", {})
                }
            )
            if graph_response.status_code == 200:
                graph_results.append(graph_response.json())
        
        return rag_result, graph_results


async def graph_enriched_search(
    query: str,
    limit: int = 5,
    filters: Optional[Dict[str, Any]] = None,
    graph_depth: int = 1,
    graph_limit: int = 10
):
    """Perform graph-enriched search."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{API_BASE_URL}/v1/rag/search/graph-enriched",
            json={
                "query": query,
                "limit": limit,
                "filters": filters,
                "graph_depth": graph_depth,
                "graph_limit": graph_limit,
                "include_entity_context": True
            }
        )
        response.raise_for_status()
        return response.json()


async def graph_enriched_query(
    query: str,
    k: int = 5,
    filters: Optional[Dict[str, Any]] = None,
    graph_depth: int = 1,
    graph_limit: int = 10,
    messages: Optional[List[Dict[str, str]]] = None,
    temperature: float = 0.7,
    max_tokens: int = 2048
):
    """Query with graph-enriched RAG."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        payload = {
            "query": query,
            "k": k,
            "graph_depth": graph_depth,
            "graph_limit": graph_limit,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "include_context": True
        }
        
        if filters:
            payload["filters"] = filters
        
        if messages:
            payload["messages"] = messages
        
        response = await client.post(
            f"{API_BASE_URL}/v1/rag/query/graph-enriched",
            json=payload
        )
        response.raise_for_status()
        return response.json()


async def standard_rag_query(
    query: str,
    k: int = 5,
    filters: Optional[Dict[str, Any]] = None,
    temperature: float = 0.7,
    max_tokens: int = 2048
):
    """Standard RAG query for comparison."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{API_BASE_URL}/v1/rag/query",
            json={
                "query": query,
                "k": k,
                "filters": filters,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "include_context": True
            }
        )
        response.raise_for_status()
        return response.json()


def print_search_results(results: Dict[str, Any], show_graph: bool = True):
    """Pretty print graph-enriched search results."""
    print(f"\n{'='*80}")
    print(f"GRAPH-ENRICHED SEARCH RESULTS")
    print(f"{'='*80}")
    
    print(f"\nQuery: {results['query']}")
    print(f"Enriched: {results['enriched']}")
    
    stats = results.get('stats', {})
    print(f"\n📊 STATISTICS:")
    print(f"  • Vector results: {stats.get('vector_results_count', 0)}")
    print(f"  • Entities found: {stats.get('entities_found', 0)}")
    print(f"  • Entities in graph: {stats.get('entities_in_graph', 0)}")
    print(f"  • Relationships: {stats.get('relationships_found', 0)}")
    
    vector_results = results.get('vector_results', [])
    print(f"\n📄 TOP RESULTS ({len(vector_results)}):")
    for i, result in enumerate(vector_results[:3], 1):
        print(f"\n  {i}. Score: {result['score']:.4f}")
        print(f"     Text: {result['text'][:150]}...")
        
        graph_entities = result.get('graph_entities', [])
        if graph_entities and show_graph:
            print(f"     Graph Entities ({len(graph_entities)}):")
            for entity in graph_entities:
                print(f"       • {entity['entity']} ({entity['type']}) - {entity['neighbor_count']} neighbors")
    
    if show_graph:
        graph_context = results.get('graph_context', {})
        if graph_context and graph_context.get('relationships'):
            print(f"\n🕸️  KEY RELATIONSHIPS:")
            for rel in graph_context['relationships'][:10]:
                rel_str = ' → '.join(rel['relation_types'])
                print(f"  • {rel['source']} {rel_str} {rel['target']}")


def print_query_response(result: Dict[str, Any], title: str = "QUERY RESPONSE"):
    """Pretty print query response."""
    print(f"\n{'='*80}")
    print(title)
    print(f"{'='*80}")
    
    print(f"\nQuery: {result['query']}")
    
    print(f"\n💬 RESPONSE:")
    print(result['response'])
    
    stats = result.get('retrieval_stats', {})
    print(f"\n📊 STATISTICS:")
    print(f"  • Chunks retrieved: {stats.get('chunks_retrieved', 0)}")
    if 'entities_in_graph' in stats:
        print(f"  • Entities in graph: {stats['entities_in_graph']}")
        print(f"  • Relationships found: {stats['relationships_found']}")
    print(f"  • Retrieval time: {stats.get('retrieval_time_ms', 0):.2f}ms")
    print(f"  • Generation time: {stats.get('generation_time_ms', 0):.2f}ms")
    print(f"  • Total time: {stats.get('total_time_ms', 0):.2f}ms")
    
    if stats.get('top_score'):
        print(f"  • Top score: {stats['top_score']:.4f}")
        print(f"  • Avg score: {stats['avg_score']:.4f}")
    
    usage = result['usage']
    print(f"\n💬 TOKEN USAGE:")
    print(f"  • Prompt: {usage['prompt_tokens']}")
    print(f"  • Completion: {usage['completion_tokens']}")
    print(f"  • Total: {usage['total_tokens']}")


async def main():
    print("="*80)
    print("Graph-Enriched RAG API Example")
    print("="*80)
    
    # Sample documents with rich entity relationships
    print("\n1. Ingesting sample documents...")
    documents = [
        {
            "text": """
            Alice Johnson works on the TensorFlow framework at Google Research. 
            She collaborates with Bob Smith from the PyTorch team at Meta AI. 
            Together they are developing new optimization algorithms for deep 
            learning models. Their work focuses on transformer architectures 
            and attention mechanisms.
            """,
            "metadata": {
                "title": "ML Research Team",
                "category": "research",
                "topic": "machine_learning"
            }
        },
        {
            "text": """
            The transformer architecture solved the vanishing gradient problem 
            that plagued earlier recurrent neural networks. This breakthrough 
            was achieved through self-attention mechanisms. BERT and GPT models 
            are based on transformers. The innovation enabled major advances 
            in natural language processing tasks.
            """,
            "metadata": {
                "title": "Transformer Innovation",
                "category": "technology",
                "topic": "nlp"
            }
        },
        {
            "text": """
            Bob Smith leads computer vision research at Meta AI. His team 
            developed YOLO improvements for real-time object detection. 
            They work closely with autonomous vehicle companies. Bob mentors 
            students at Stanford University on perception systems.
            """,
            "metadata": {
                "title": "Computer Vision Research",
                "category": "research",
                "topic": "computer_vision"
            }
        }
    ]
    
    try:
        rag_result, graph_results = await ingest_documents_with_graph(documents)
        print(f"✓ RAG: {rag_result['documents_processed']} documents, {rag_result['total_chunks']} chunks")
        print(f"✓ Graph: {len(graph_results)} documents processed")
        for gr in graph_results:
            print(f"  - {gr['entities_added']} entities, {gr['relations_added']} relations")
    except Exception as e:
        print(f"✗ Ingestion failed: {e}")
        print("  Note: Make sure Neo4j is running for graph features")
        return
    
    # Example 1: Graph-enriched search
    print("\n2. Graph-enriched search...")
    
    search_queries = [
        {
            "query": "Who works on machine learning frameworks?",
            "graph_depth": 1,
            "graph_limit": 10
        },
        {
            "query": "What problems did transformers solve?",
            "graph_depth": 2,
            "graph_limit": 15
        }
    ]
    
    for sq in search_queries:
        print(f"\n  Query: {sq['query']}")
        try:
            search_result = await graph_enriched_search(
                query=sq['query'],
                limit=3,
                graph_depth=sq['graph_depth'],
                graph_limit=sq['graph_limit']
            )
            print_search_results(search_result)
        except Exception as e:
            print(f"  ✗ Search failed: {e}")
    
    # Example 2: Compare standard vs graph-enriched query
    print("\n3. Comparison: Standard RAG vs Graph-Enriched RAG...")
    comparison_query = "Tell me about the researchers working on AI and their collaborations"
    
    print(f"\n  Query: {comparison_query}")
    
    # Standard RAG
    print("\n  🔹 Standard RAG:")
    try:
        standard_result = await standard_rag_query(
            query=comparison_query,
            k=3,
            temperature=0.7
        )
        print_query_response(standard_result, "STANDARD RAG RESPONSE")
    except Exception as e:
        print(f"  ✗ Standard RAG failed: {e}")
    
    # Graph-enriched RAG
    print("\n  🔹 Graph-Enriched RAG:")
    try:
        enriched_result = await graph_enriched_query(
            query=comparison_query,
            k=3,
            graph_depth=2,
            graph_limit=15,
            temperature=0.7
        )
        print_query_response(enriched_result, "GRAPH-ENRICHED RAG RESPONSE")
        
        # Show graph context
        if enriched_result.get('graph_context_formatted'):
            print(f"\n📝 GRAPH CONTEXT PROVIDED TO LLM:")
            print(enriched_result['graph_context_formatted'])
    except Exception as e:
        print(f"  ✗ Graph-enriched RAG failed: {e}")
    
    # Example 3: Multi-hop graph queries
    print("\n4. Multi-hop graph queries (depth=2)...")
    
    multi_hop_queries = [
        {
            "query": "What technologies are related to Alice Johnson's work?",
            "k": 3,
            "graph_depth": 2,
            "graph_limit": 20
        },
        {
            "query": "How are transformers connected to other AI innovations?",
            "k": 3,
            "graph_depth": 2,
            "graph_limit": 20
        }
    ]
    
    for mq in multi_hop_queries:
        print(f"\n  Query: {mq['query']}")
        print(f"  Parameters: depth={mq['graph_depth']}, limit={mq['graph_limit']}")
        
        try:
            result = await graph_enriched_query(**mq)
            print(f"\n  ✓ Response generated")
            
            stats = result['retrieval_stats']
            print(f"    • Vector chunks: {stats['chunks_retrieved']}")
            print(f"    • Graph entities: {stats['entities_in_graph']}")
            print(f"    • Relationships: {stats['relationships_found']}")
            print(f"    • Total time: {stats['total_time_ms']:.2f}ms")
            
            print(f"\n  Response: {result['response'][:300]}...")
            
        except Exception as e:
            print(f"  ✗ Query failed: {e}")
    
    # Example 4: Filtered graph-enriched search
    print("\n5. Filtered graph-enriched search...")
    
    try:
        filtered_result = await graph_enriched_search(
            query="machine learning research",
            limit=5,
            filters={"category": "research"},
            graph_depth=1,
            graph_limit=10
        )
        print(f"\n  Query: machine learning research (filtered by category='research')")
        print_search_results(filtered_result, show_graph=False)
        
    except Exception as e:
        print(f"  ✗ Filtered search failed: {e}")
    
    print("\n" + "="*80)
    print("Example completed!")
    print("="*80)
    print("\nKey Takeaways:")
    print("  • Graph-enriched RAG adds entity relationships to context")
    print("  • Multi-hop queries (depth > 1) discover indirect connections")
    print("  • Combined approach provides richer, more accurate responses")
    print("  • Graph context helps LLM understand entity relationships")


if __name__ == "__main__":
    asyncio.run(main())
