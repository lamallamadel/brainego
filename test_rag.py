#!/usr/bin/env python3
"""
Test script for RAG ingestion endpoints.
"""

import httpx
import time


API_BASE_URL = "http://localhost:8000"


def test_rag_ingest():
    """Test single document ingestion."""
    print("Testing RAG document ingestion...")
    
    test_text = """
    The quick brown fox jumps over the lazy dog. This is a test document for 
    the RAG ingestion service. It should be chunked into smaller pieces and 
    stored in the Qdrant vector database with embeddings from Nomic Embed v1.5.
    """ * 10
    
    response = httpx.post(
        f"{API_BASE_URL}/v1/rag/ingest",
        json={
            "text": test_text,
            "metadata": {
                "title": "Test Document",
                "category": "test",
                "source": "test_script"
            }
        },
        timeout=60.0
    )
    
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    data = response.json()
    
    assert "document_id" in data
    assert "chunks_created" in data
    assert "points_stored" in data
    assert data["status"] == "success"
    assert data["chunks_created"] > 0
    assert data["points_stored"] > 0
    
    print(f"✓ Document ingested successfully!")
    print(f"  Document ID: {data['document_id']}")
    print(f"  Chunks: {data['chunks_created']}")
    print(f"  Points: {data['points_stored']}")
    
    return data["document_id"]


def test_rag_batch_ingest():
    """Test batch document ingestion."""
    print("\nTesting RAG batch ingestion...")
    
    documents = [
        {
            "text": "Document 1: This is the first test document. " * 50,
            "metadata": {"title": "Doc 1", "batch": "test_batch"}
        },
        {
            "text": "Document 2: This is the second test document. " * 50,
            "metadata": {"title": "Doc 2", "batch": "test_batch"}
        }
    ]
    
    response = httpx.post(
        f"{API_BASE_URL}/v1/rag/ingest/batch",
        json={"documents": documents},
        timeout=120.0
    )
    
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    data = response.json()
    
    assert data["status"] == "success"
    assert data["documents_processed"] == 2
    assert data["total_chunks"] > 0
    assert data["total_points"] > 0
    
    print(f"✓ Batch ingestion successful!")
    print(f"  Documents: {data['documents_processed']}")
    print(f"  Total chunks: {data['total_chunks']}")
    print(f"  Total points: {data['total_points']}")


def test_rag_search():
    """Test document search."""
    print("\nTesting RAG search...")
    
    response = httpx.post(
        f"{API_BASE_URL}/v1/rag/search",
        json={
            "query": "test document",
            "limit": 5
        },
        timeout=30.0
    )
    
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    data = response.json()
    
    assert "results" in data
    assert "query" in data
    assert len(data["results"]) > 0
    
    print(f"✓ Search successful!")
    print(f"  Query: {data['query']}")
    print(f"  Results: {len(data['results'])}")
    
    for i, result in enumerate(data["results"][:3], 1):
        print(f"\n  Result {i}:")
        print(f"    Score: {result['score']:.4f}")
        print(f"    Text: {result['text'][:80]}...")


def test_rag_stats():
    """Test RAG statistics endpoint."""
    print("\nTesting RAG stats...")
    
    response = httpx.get(f"{API_BASE_URL}/v1/rag/stats", timeout=30.0)
    
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    data = response.json()
    
    assert "collection_info" in data
    info = data["collection_info"]
    assert "name" in info
    assert "points_count" in info
    
    print(f"✓ Stats retrieved!")
    print(f"  Collection: {info['name']}")
    print(f"  Points: {info['points_count']}")
    print(f"  Status: {info.get('status', 'unknown')}")


def test_rag_delete(document_id: str):
    """Test document deletion."""
    print(f"\nTesting RAG delete for document {document_id}...")
    
    response = httpx.delete(
        f"{API_BASE_URL}/v1/rag/documents/{document_id}",
        timeout=30.0
    )
    
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    data = response.json()
    
    assert data["status"] == "success"
    assert data["document_id"] == document_id
    
    print(f"✓ Document deleted successfully!")


def main():
    print("=" * 80)
    print("RAG Ingestion API Tests")
    print("=" * 80)
    
    try:
        response = httpx.get(f"{API_BASE_URL}/health", timeout=5.0)
        if response.status_code != 200:
            print("Error: API server is not healthy")
            return
    except Exception as e:
        print(f"Error: Cannot connect to API server at {API_BASE_URL}")
        print(f"Make sure the server is running: python api_server.py")
        return
    
    try:
        doc_id = test_rag_ingest()
        test_rag_batch_ingest()
        test_rag_search()
        test_rag_stats()
        test_rag_delete(doc_id)
        
        print("\n" + "=" * 80)
        print("All tests passed! ✓")
        print("=" * 80)
        
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
    except Exception as e:
        print(f"\n✗ Error: {e}")


if __name__ == "__main__":
    main()
