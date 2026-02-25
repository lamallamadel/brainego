#!/usr/bin/env python3
"""
Example script demonstrating graph-enriched RAG retrieval.

This script shows how to:
1. Initialize RAG service with Neo4j graph integration
2. Ingest documents and extract entities into knowledge graph
3. Perform graph-enriched retrieval that combines:
   - Vector similarity search (semantic matching)
   - Knowledge graph context (entity relationships)
4. Format and display enriched results
"""

import logging
import sys
from typing import Dict, Any

from rag_service import RAGIngestionService
from graph_service import GraphService

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def print_enriched_results(enriched_data: Dict[str, Any]):
    """Pretty print graph-enriched retrieval results."""
    print(f"\n{'='*80}")
    print(f"GRAPH-ENRICHED RETRIEVAL RESULTS")
    print(f"{'='*80}")
    
    # Query info
    print(f"\nQuery: {enriched_data['query']}")
    print(f"Enriched: {enriched_data['enriched']}")
    
    # Statistics
    stats = enriched_data.get('stats', {})
    print(f"\n📊 STATISTICS:")
    print(f"  • Vector results: {stats.get('vector_results_count', 0)}")
    print(f"  • Entities found: {stats.get('entities_found', 0)}")
    print(f"  • Entities in graph: {stats.get('entities_in_graph', 0)}")
    print(f"  • Relationships found: {stats.get('relationships_found', 0)}")
    print(f"  • Subgraphs: {stats.get('subgraphs', 0)}")
    
    # Vector results with graph enrichment
    vector_results = enriched_data.get('vector_results', [])
    print(f"\n📄 VECTOR SEARCH RESULTS ({len(vector_results)} chunks):")
    for i, result in enumerate(vector_results[:3], 1):
        print(f"\n  Result {i}:")
        print(f"    Score: {result['score']:.4f}")
        print(f"    Text: {result['text'][:200]}...")
        
        # Show graph entities found in this result
        graph_entities = result.get('graph_entities', [])
        if graph_entities:
            print(f"    Graph Entities ({len(graph_entities)}):")
            for entity in graph_entities:
                print(f"      • {entity['entity']} ({entity['type']})")
                print(f"        - {entity['neighbor_count']} neighbors in graph")
                if entity.get('neighbors'):
                    print(f"        - Related to: {', '.join([n['name'] for n in entity['neighbors'][:3]])}")
    
    # Graph context summary
    graph_context = enriched_data.get('graph_context', {})
    if graph_context and graph_context.get('entities'):
        print(f"\n🕸️  KNOWLEDGE GRAPH CONTEXT:")
        
        # Entities
        entities = graph_context.get('entities', [])
        print(f"\n  Entities in Graph ({len(entities)}):")
        for entity in entities:
            print(f"    • {entity['name']} ({entity['type']})")
            print(f"      - {entity['neighbor_count']} related entities")
        
        # Relationships
        relationships = graph_context.get('relationships', [])
        if relationships:
            print(f"\n  Key Relationships ({len(relationships)}):")
            # Group by source
            rel_by_source = {}
            for rel in relationships:
                source = rel['source']
                if source not in rel_by_source:
                    rel_by_source[source] = []
                rel_by_source[source].append(rel)
            
            for source, rels in list(rel_by_source.items())[:5]:
                print(f"\n    {source}:")
                for rel in rels[:3]:
                    rel_types = ' → '.join(rel['relation_types'])
                    print(f"      - {rel_types}: {rel['target']} ({rel['target_type']})")
    
    print(f"\n{'='*80}\n")


def main():
    print("="*80)
    print("Graph-Enriched RAG Retrieval Example")
    print("="*80)
    
    # Initialize services
    print("\n1. Initializing services...")
    
    # Initialize Graph Service
    try:
        graph_service = GraphService(
            neo4j_uri="bolt://localhost:7687",
            neo4j_user="neo4j",
            neo4j_password="neo4j_password",
            spacy_model="en_core_web_sm"
        )
        print("✓ Graph Service initialized")
    except Exception as e:
        logger.error(f"Failed to initialize Graph Service: {e}")
        print("✗ Graph Service initialization failed")
        print("  Make sure Neo4j is running on bolt://localhost:7687")
        sys.exit(1)
    
    # Initialize RAG Service with Graph integration
    try:
        rag_service = RAGIngestionService(
            qdrant_host="localhost",
            qdrant_port=6333,
            collection_name="documents",
            chunk_size=500,
            chunk_overlap=50,
            embedding_model="nomic-ai/nomic-embed-text-v1.5",
            graph_service=graph_service
        )
        print("✓ RAG Service initialized with graph integration")
    except Exception as e:
        logger.error(f"Failed to initialize RAG Service: {e}")
        print("✗ RAG Service initialization failed")
        print("  Make sure Qdrant is running on localhost:6333")
        sys.exit(1)
    
    # Sample documents with rich entity content
    print("\n2. Ingesting sample documents with entity extraction...")
    documents = [
        {
            "text": """
            John Smith works on the TensorFlow project at Google. He has been 
            developing machine learning algorithms for computer vision applications. 
            The project focuses on optimizing neural network architectures for 
            image classification tasks. John collaborates with Sarah Johnson who 
            leads the PyTorch initiative at Meta.
            """,
            "metadata": {
                "title": "ML Project Team",
                "category": "project",
                "topic": "machine_learning"
            }
        },
        {
            "text": """
            The transformer architecture revolutionized natural language processing. 
            Introduced by Vaswani et al. in 2017, transformers use self-attention 
            mechanisms to process sequential data. BERT and GPT models are based 
            on transformer architecture. This innovation solved long-standing problems 
            in NLP related to long-range dependencies.
            """,
            "metadata": {
                "title": "Transformers in NLP",
                "category": "technology",
                "topic": "nlp"
            }
        },
        {
            "text": """
            Deep learning suffered from the vanishing gradient problem in early 
            implementations. This issue was caused by activation functions and 
            network depth. Researchers solved the problem by introducing ResNet 
            residual connections and better initialization techniques. The lesson 
            learned from this challenge led to modern deep network architectures.
            """,
            "metadata": {
                "title": "Deep Learning Challenges",
                "category": "problem",
                "topic": "deep_learning"
            }
        },
        {
            "text": """
            Sarah Johnson leads the Computer Vision team at Stanford University. 
            Her research focuses on object detection and semantic segmentation. 
            She developed the YOLO algorithm improvements that enhanced real-time 
            detection capabilities. Sarah mentors students working on autonomous 
            vehicle perception systems.
            """,
            "metadata": {
                "title": "Computer Vision Research",
                "category": "project",
                "topic": "computer_vision"
            }
        }
    ]
    
    # Ingest documents and extract to graph
    for i, doc in enumerate(documents, 1):
        try:
            # Ingest to vector DB
            result = rag_service.ingest_document(
                text=doc["text"],
                metadata=doc["metadata"]
            )
            doc_id = result["document_id"]
            print(f"  ✓ Document {i}/{len(documents)} ingested: {result['chunks_created']} chunks")
            
            # Extract entities and relations to graph
            graph_result = graph_service.process_document(
                text=doc["text"],
                document_id=doc_id,
                metadata=doc["metadata"]
            )
            print(f"    → Graph: {graph_result['entities_added']} entities, "
                  f"{graph_result['relations_added']} relations")
            
        except Exception as e:
            logger.error(f"Error processing document {i}: {e}")
            print(f"  ✗ Document {i} failed: {e}")
    
    # Get graph statistics
    print("\n3. Knowledge Graph Statistics...")
    try:
        graph_stats = graph_service.get_graph_stats()
        print(f"  • Total nodes: {graph_stats['total_nodes']}")
        print(f"  • Total relationships: {graph_stats['total_relationships']}")
        print(f"  • Nodes by type:")
        for node_type, count in graph_stats['nodes_by_type'].items():
            if count > 0:
                print(f"    - {node_type}: {count}")
    except Exception as e:
        logger.error(f"Error getting graph stats: {e}")
    
    # Example queries with graph enrichment
    print("\n4. Performing graph-enriched retrieval...")
    
    queries = [
        {
            "query": "Who works on machine learning projects?",
            "limit": 3,
            "graph_depth": 1,
            "graph_limit": 10
        },
        {
            "query": "What problems did deep learning face?",
            "limit": 3,
            "graph_depth": 2,
            "graph_limit": 15
        },
        {
            "query": "Tell me about transformer architecture",
            "limit": 3,
            "graph_depth": 1,
            "graph_limit": 10
        }
    ]
    
    for i, query_config in enumerate(queries, 1):
        print(f"\n  Query {i}: {query_config['query']}")
        
        try:
            # Perform graph-enriched search
            enriched_results = rag_service.search_with_graph_enrichment(
                query=query_config['query'],
                limit=query_config['limit'],
                graph_depth=query_config['graph_depth'],
                graph_limit=query_config['graph_limit']
            )
            
            # Display results
            print_enriched_results(enriched_results)
            
            # Format graph context for LLM
            if enriched_results['enriched'] and enriched_results.get('graph_context'):
                graph_context_str = rag_service.format_graph_context_for_llm(
                    enriched_results['graph_context']
                )
                if graph_context_str:
                    print(f"📝 FORMATTED GRAPH CONTEXT FOR LLM:")
                    print(graph_context_str)
                    print()
            
        except Exception as e:
            logger.error(f"Error in query {i}: {e}")
            print(f"  ✗ Query failed: {e}")
    
    # Example: Compare standard vs graph-enriched search
    print("\n5. Comparison: Standard vs Graph-Enriched Search...")
    comparison_query = "What are the relationships between ML researchers?"
    
    print(f"\n  Query: {comparison_query}")
    
    # Standard search
    print("\n  🔹 Standard Vector Search:")
    try:
        standard_results = rag_service.search_documents(
            query=comparison_query,
            limit=3
        )
        print(f"    Found {len(standard_results)} results")
        for i, result in enumerate(standard_results[:2], 1):
            print(f"    {i}. Score: {result['score']:.4f}")
            print(f"       {result['text'][:150]}...")
    except Exception as e:
        print(f"    ✗ Failed: {e}")
    
    # Graph-enriched search
    print("\n  🔹 Graph-Enriched Search:")
    try:
        enriched = rag_service.search_with_graph_enrichment(
            query=comparison_query,
            limit=3,
            graph_depth=2,
            graph_limit=15
        )
        print(f"    Found {enriched['stats']['vector_results_count']} vector results")
        print(f"    + {enriched['stats']['entities_in_graph']} entities from graph")
        print(f"    + {enriched['stats']['relationships_found']} relationships")
        
        # Show the added value
        if enriched['graph_context'] and enriched['graph_context'].get('relationships'):
            print(f"\n    Additional Context from Graph:")
            for rel in enriched['graph_context']['relationships'][:5]:
                print(f"      • {rel['source']} → {rel['target']} "
                      f"({', '.join(rel['relation_types'])})")
    except Exception as e:
        print(f"    ✗ Failed: {e}")
    
    # Cleanup
    print("\n6. Cleaning up...")
    try:
        graph_service.close()
        print("  ✓ Graph service closed")
    except Exception as e:
        logger.error(f"Error closing graph service: {e}")
    
    print("\n" + "="*80)
    print("Example completed successfully!")
    print("="*80)


if __name__ == "__main__":
    main()
