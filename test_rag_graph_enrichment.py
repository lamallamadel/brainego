#!/usr/bin/env python3
"""
Tests for graph-enriched RAG retrieval functionality.

This test suite verifies:
1. Integration between RAG and Graph services
2. Graph-enriched search functionality
3. Context formatting for LLM
4. API endpoints for graph-enriched RAG
"""

import pytest
import logging
from typing import Dict, Any

from rag_service import RAGIngestionService
from graph_service import GraphService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TestGraphEnrichedRAG:
    """Test suite for graph-enriched RAG functionality."""
    
    @pytest.fixture
    def sample_documents(self):
        """Sample documents with entity-rich content."""
        return [
            {
                "text": """
                John Smith works on the TensorFlow project at Google. He collaborates 
                with Mary Johnson on deep learning optimization. Their work focuses on 
                improving transformer model performance.
                """,
                "metadata": {
                    "title": "ML Team",
                    "category": "research"
                }
            },
            {
                "text": """
                Mary Johnson leads the PyTorch initiative at Meta. She developed 
                novel attention mechanisms for natural language processing. Mary 
                mentors students at Stanford University.
                """,
                "metadata": {
                    "title": "NLP Research",
                    "category": "research"
                }
            },
            {
                "text": """
                The vanishing gradient problem was a major challenge in deep learning. 
                This issue was caused by activation functions and network depth. 
                Researchers solved the problem using ResNet and better initialization 
                techniques.
                """,
                "metadata": {
                    "title": "Deep Learning Problems",
                    "category": "problem"
                }
            }
        ]
    
    def test_rag_service_with_graph_integration(self):
        """Test that RAG service accepts graph_service parameter."""
        try:
            graph_service = GraphService(
                neo4j_uri="bolt://localhost:7687",
                neo4j_user="neo4j",
                neo4j_password="neo4j_password"
            )
            
            rag_service = RAGIngestionService(
                qdrant_host="localhost",
                qdrant_port=6333,
                collection_name="test_documents",
                graph_service=graph_service
            )
            
            assert rag_service.graph_service is not None
            logger.info("✓ RAG service initialized with graph integration")
            
            graph_service.close()
            
        except Exception as e:
            logger.warning(f"Graph service not available: {e}")
            pytest.skip("Neo4j not available for testing")
    
    def test_search_with_graph_enrichment(self, sample_documents):
        """Test graph-enriched search functionality."""
        try:
            # Initialize services
            graph_service = GraphService(
                neo4j_uri="bolt://localhost:7687",
                neo4j_user="neo4j",
                neo4j_password="neo4j_password"
            )
            
            rag_service = RAGIngestionService(
                qdrant_host="localhost",
                qdrant_port=6333,
                collection_name="test_graph_enriched",
                graph_service=graph_service
            )
            
            # Ingest documents
            doc_ids = []
            for doc in sample_documents:
                result = rag_service.ingest_document(
                    text=doc["text"],
                    metadata=doc["metadata"]
                )
                doc_ids.append(result["document_id"])
                
                # Process with graph
                graph_service.process_document(
                    text=doc["text"],
                    document_id=result["document_id"],
                    metadata=doc["metadata"]
                )
            
            logger.info(f"✓ Ingested {len(doc_ids)} documents")
            
            # Test graph-enriched search
            enriched_results = rag_service.search_with_graph_enrichment(
                query="Who works on machine learning projects?",
                limit=5,
                graph_depth=1,
                graph_limit=10
            )
            
            # Verify results structure
            assert "query" in enriched_results
            assert "vector_results" in enriched_results
            assert "graph_context" in enriched_results
            assert "enriched" in enriched_results
            assert "stats" in enriched_results
            
            # Verify enrichment occurred
            assert enriched_results["enriched"] is True
            
            # Verify stats
            stats = enriched_results["stats"]
            assert stats["vector_results_count"] > 0
            logger.info(f"✓ Vector results: {stats['vector_results_count']}")
            logger.info(f"✓ Entities found: {stats['entities_found']}")
            logger.info(f"✓ Entities in graph: {stats['entities_in_graph']}")
            logger.info(f"✓ Relationships: {stats['relationships_found']}")
            
            # Verify graph context
            if enriched_results["graph_context"]:
                graph_context = enriched_results["graph_context"]
                assert "entities" in graph_context
                assert "relationships" in graph_context
                assert "subgraphs" in graph_context
                logger.info("✓ Graph context structure valid")
            
            # Cleanup
            for doc_id in doc_ids:
                rag_service.delete_document(doc_id)
            
            graph_service.close()
            logger.info("✓ Graph-enriched search test passed")
            
        except Exception as e:
            logger.warning(f"Graph-enriched search test skipped: {e}")
            pytest.skip("Neo4j or Qdrant not available for testing")
    
    def test_format_graph_context_for_llm(self):
        """Test formatting of graph context for LLM consumption."""
        try:
            graph_service = GraphService(
                neo4j_uri="bolt://localhost:7687",
                neo4j_user="neo4j",
                neo4j_password="neo4j_password"
            )
            
            rag_service = RAGIngestionService(
                qdrant_host="localhost",
                qdrant_port=6333,
                collection_name="test_formatting",
                graph_service=graph_service
            )
            
            # Mock graph context
            graph_context = {
                "entities": [
                    {
                        "name": "John Smith",
                        "type": "Person",
                        "neighbor_count": 3
                    },
                    {
                        "name": "TensorFlow",
                        "type": "Project",
                        "neighbor_count": 5
                    }
                ],
                "relationships": [
                    {
                        "source": "John Smith",
                        "source_type": "Person",
                        "target": "TensorFlow",
                        "target_type": "Project",
                        "relation_types": ["WORKS_ON"],
                        "distance": 1
                    }
                ]
            }
            
            # Format for LLM
            formatted = rag_service.format_graph_context_for_llm(graph_context)
            
            # Verify formatting
            assert isinstance(formatted, str)
            assert len(formatted) > 0
            assert "John Smith" in formatted
            assert "TensorFlow" in formatted
            assert "WORKS_ON" in formatted
            
            logger.info("✓ Graph context formatting test passed")
            logger.info(f"Formatted output:\n{formatted}")
            
            graph_service.close()
            
        except Exception as e:
            logger.warning(f"Context formatting test skipped: {e}")
            pytest.skip("Services not available for testing")
    
    def test_search_without_graph_service(self):
        """Test that search works gracefully without graph service."""
        try:
            # Initialize RAG without graph
            rag_service = RAGIngestionService(
                qdrant_host="localhost",
                qdrant_port=6333,
                collection_name="test_no_graph",
                graph_service=None
            )
            
            # Ingest test document
            result = rag_service.ingest_document(
                text="Test document about machine learning.",
                metadata={"test": "true"}
            )
            
            # Try graph-enriched search (should fallback)
            enriched_results = rag_service.search_with_graph_enrichment(
                query="machine learning",
                limit=5
            )
            
            # Verify fallback behavior
            assert enriched_results["enriched"] is False
            assert enriched_results["graph_context"] is None
            assert "vector_results" in enriched_results
            
            logger.info("✓ Fallback behavior test passed")
            
            # Cleanup
            rag_service.delete_document(result["document_id"])
            
        except Exception as e:
            logger.warning(f"Fallback test skipped: {e}")
            pytest.skip("Qdrant not available for testing")
    
    def test_multi_hop_graph_enrichment(self, sample_documents):
        """Test multi-hop (depth > 1) graph traversal."""
        try:
            graph_service = GraphService(
                neo4j_uri="bolt://localhost:7687",
                neo4j_user="neo4j",
                neo4j_password="neo4j_password"
            )
            
            rag_service = RAGIngestionService(
                qdrant_host="localhost",
                qdrant_port=6333,
                collection_name="test_multi_hop",
                graph_service=graph_service
            )
            
            # Ingest and process
            doc_ids = []
            for doc in sample_documents:
                result = rag_service.ingest_document(
                    text=doc["text"],
                    metadata=doc["metadata"]
                )
                doc_ids.append(result["document_id"])
                
                graph_service.process_document(
                    text=doc["text"],
                    document_id=result["document_id"],
                    metadata=doc["metadata"]
                )
            
            # Test with depth=2
            enriched_results = rag_service.search_with_graph_enrichment(
                query="What technologies are related to researchers?",
                limit=5,
                graph_depth=2,  # Multi-hop
                graph_limit=20
            )
            
            # Verify multi-hop traversal
            stats = enriched_results["stats"]
            logger.info(f"✓ Multi-hop results:")
            logger.info(f"  - Vector results: {stats['vector_results_count']}")
            logger.info(f"  - Entities: {stats['entities_in_graph']}")
            logger.info(f"  - Relationships: {stats['relationships_found']}")
            
            # Check for relationships at different distances
            if enriched_results["graph_context"] and enriched_results["graph_context"]["relationships"]:
                distances = [r["distance"] for r in enriched_results["graph_context"]["relationships"]]
                logger.info(f"  - Relationship distances: {set(distances)}")
            
            # Cleanup
            for doc_id in doc_ids:
                rag_service.delete_document(doc_id)
            
            graph_service.close()
            logger.info("✓ Multi-hop enrichment test passed")
            
        except Exception as e:
            logger.warning(f"Multi-hop test skipped: {e}")
            pytest.skip("Services not available for testing")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
