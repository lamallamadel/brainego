#!/usr/bin/env python3
"""
Example script demonstrating RAG document ingestion.

This script shows how to:
1. Ingest a single document with metadata
2. Ingest multiple documents in batch
3. Search for relevant documents
4. Get RAG system statistics
5. Delete documents
"""

import httpx
import asyncio
import json
from typing import Dict, List, Any


API_BASE_URL = "http://localhost:8000"


async def ingest_single_document(text: str, metadata: Dict[str, Any] = None):
    """Ingest a single document."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{API_BASE_URL}/v1/rag/ingest",
            json={
                "text": text,
                "metadata": metadata or {}
            }
        )
        response.raise_for_status()
        return response.json()


async def ingest_batch_documents(documents: List[Dict[str, Any]]):
    """Ingest multiple documents in batch."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{API_BASE_URL}/v1/rag/ingest/batch",
            json={"documents": documents}
        )
        response.raise_for_status()
        return response.json()


async def search_documents(query: str, limit: int = 5, filters: Dict[str, Any] = None):
    """Search for relevant documents."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{API_BASE_URL}/v1/rag/search",
            json={
                "query": query,
                "limit": limit,
                "filters": filters
            }
        )
        response.raise_for_status()
        return response.json()


async def delete_document(document_id: str):
    """Delete a document by ID."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.delete(
            f"{API_BASE_URL}/v1/rag/documents/{document_id}"
        )
        response.raise_for_status()
        return response.json()


async def get_rag_stats():
    """Get RAG system statistics."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(f"{API_BASE_URL}/v1/rag/stats")
        response.raise_for_status()
        return response.json()


async def main():
    print("=" * 80)
    print("RAG Ingestion Example")
    print("=" * 80)
    
    # Example 1: Ingest a single document
    print("\n1. Ingesting a single document...")
    doc_text = """
    Artificial Intelligence (AI) is transforming the way we work and live. 
    Machine learning, a subset of AI, enables computers to learn from data 
    without explicit programming. Deep learning, using neural networks with 
    multiple layers, has achieved breakthrough results in image recognition, 
    natural language processing, and game playing. Recent advances in large 
    language models like GPT have demonstrated remarkable capabilities in 
    understanding and generating human-like text.
    """
    
    result = await ingest_single_document(
        text=doc_text,
        metadata={
            "title": "Introduction to AI",
            "category": "technology",
            "author": "AI Researcher",
            "date": "2024-01-15"
        }
    )
    print(f"✓ Document ingested successfully!")
    print(f"  Document ID: {result['document_id']}")
    print(f"  Chunks created: {result['chunks_created']}")
    print(f"  Points stored: {result['points_stored']}")
    doc_id_1 = result['document_id']
    
    # Example 2: Ingest multiple documents in batch
    print("\n2. Ingesting multiple documents in batch...")
    documents = [
        {
            "text": """
            Python is a high-level, interpreted programming language known for its 
            simplicity and readability. It supports multiple programming paradigms 
            including procedural, object-oriented, and functional programming. 
            Python's extensive standard library and vast ecosystem of third-party 
            packages make it ideal for web development, data science, automation, 
            and artificial intelligence applications.
            """,
            "metadata": {
                "title": "Python Programming",
                "category": "programming",
                "author": "Developer",
                "date": "2024-01-16"
            }
        },
        {
            "text": """
            Quantum computing leverages quantum mechanics principles to process 
            information in fundamentally different ways than classical computers. 
            Qubits can exist in superposition, representing both 0 and 1 simultaneously, 
            enabling quantum computers to explore multiple solutions in parallel. 
            Quantum entanglement allows qubits to be correlated in ways that classical 
            bits cannot, potentially solving certain problems exponentially faster 
            than classical computers.
            """,
            "metadata": {
                "title": "Quantum Computing Basics",
                "category": "technology",
                "author": "Quantum Physicist",
                "date": "2024-01-17"
            }
        }
    ]
    
    batch_result = await ingest_batch_documents(documents)
    print(f"✓ Batch ingestion completed!")
    print(f"  Documents processed: {batch_result['documents_processed']}")
    print(f"  Total chunks: {batch_result['total_chunks']}")
    print(f"  Total points: {batch_result['total_points']}")
    
    # Example 3: Get RAG statistics
    print("\n3. Getting RAG system statistics...")
    stats = await get_rag_stats()
    print(f"✓ Collection info:")
    print(f"  Name: {stats['collection_info']['name']}")
    print(f"  Points count: {stats['collection_info']['points_count']}")
    print(f"  Vectors count: {stats['collection_info']['vectors_count']}")
    print(f"  Status: {stats['collection_info']['status']}")
    
    # Example 4: Search for relevant documents
    print("\n4. Searching for documents...")
    queries = [
        "machine learning and neural networks",
        "programming languages for AI",
        "quantum superposition"
    ]
    
    for query in queries:
        print(f"\n  Query: '{query}'")
        search_results = await search_documents(query, limit=3)
        print(f"  Found {len(search_results['results'])} results:")
        
        for i, result in enumerate(search_results['results'], 1):
            print(f"\n    Result {i}:")
            print(f"      Score: {result['score']:.4f}")
            print(f"      Text snippet: {result['text'][:100]}...")
            if result['metadata']:
                print(f"      Metadata: {json.dumps(result['metadata'], indent=8)}")
    
    # Example 5: Search with metadata filters
    print("\n5. Searching with metadata filters...")
    filtered_results = await search_documents(
        query="technology",
        limit=5,
        filters={"category": "technology"}
    )
    print(f"✓ Found {len(filtered_results['results'])} results in 'technology' category")
    
    # Example 6: Delete a document
    print(f"\n6. Deleting document {doc_id_1}...")
    delete_result = await delete_document(doc_id_1)
    print(f"✓ {delete_result['message']}")
    
    # Final statistics
    print("\n7. Final statistics after deletion...")
    final_stats = await get_rag_stats()
    print(f"✓ Collection info:")
    print(f"  Points count: {final_stats['collection_info']['points_count']}")
    
    print("\n" + "=" * 80)
    print("Example completed successfully!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
