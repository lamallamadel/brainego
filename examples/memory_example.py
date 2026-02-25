#!/usr/bin/env python3
"""
Example usage of the Memory API with Mem0.

Features:
- Add memories from conversations with automatic fact extraction
- Search memories with cosine similarity + temporal decay scoring
- Delete memories
- View memory statistics
"""

import httpx
import json
import time
from typing import List, Dict


API_URL = "http://localhost:8000"


def add_memory(messages: List[Dict[str, str]], user_id: str = None, metadata: Dict = None):
    """Add a memory from conversation messages."""
    url = f"{API_URL}/memory/add"
    payload = {
        "messages": messages,
        "user_id": user_id,
        "metadata": metadata or {}
    }
    
    print(f"\n=== Adding Memory ===")
    print(f"Messages: {len(messages)} messages")
    if user_id:
        print(f"User ID: {user_id}")
    
    response = httpx.post(url, json=payload, timeout=30.0)
    response.raise_for_status()
    result = response.json()
    
    print(f"Status: {result['status']}")
    print(f"Memory ID: {result['memory_id']}")
    print(f"Facts extracted: {result['facts_extracted']}")
    print(f"Timestamp: {result['timestamp']}")
    
    return result


def search_memory(query: str, user_id: str = None, limit: int = 5, use_temporal_decay: bool = True):
    """Search memories."""
    url = f"{API_URL}/memory/search"
    payload = {
        "query": query,
        "user_id": user_id,
        "limit": limit,
        "use_temporal_decay": use_temporal_decay
    }
    
    print(f"\n=== Searching Memory ===")
    print(f"Query: {query}")
    if user_id:
        print(f"User ID: {user_id}")
    print(f"Temporal decay: {'enabled' if use_temporal_decay else 'disabled'}")
    
    response = httpx.post(url, json=payload, timeout=30.0)
    response.raise_for_status()
    result = response.json()
    
    print(f"\nResults: {len(result['results'])} memories found")
    
    for i, memory in enumerate(result['results'], 1):
        print(f"\n--- Memory {i} ---")
        print(f"Memory ID: {memory.get('memory_id', 'N/A')}")
        print(f"Score: {memory.get('score', 0):.4f}")
        if 'cosine_score' in memory:
            print(f"  Cosine: {memory['cosine_score']:.4f}")
        if 'temporal_score' in memory:
            print(f"  Temporal: {memory['temporal_score']:.4f}")
        print(f"Text: {memory['text'][:200]}...")
        if 'timestamp' in memory:
            print(f"Timestamp: {memory['timestamp']}")
    
    return result


def forget_memory(memory_id: str):
    """Delete a memory by ID."""
    url = f"{API_URL}/memory/forget/{memory_id}"
    
    print(f"\n=== Deleting Memory ===")
    print(f"Memory ID: {memory_id}")
    
    response = httpx.delete(url, timeout=30.0)
    response.raise_for_status()
    result = response.json()
    
    print(f"Status: {result['status']}")
    print(f"Message: {result['message']}")
    
    return result


def get_memory_stats():
    """Get memory system statistics."""
    url = f"{API_URL}/memory/stats"
    
    print(f"\n=== Memory Statistics ===")
    
    response = httpx.get(url, timeout=30.0)
    response.raise_for_status()
    result = response.json()
    
    print(f"Collection: {result['collection_name']}")
    print(f"Qdrant points: {result['qdrant_points']}")
    print(f"Redis memories: {result['redis_memories']}")
    print(f"Vector dimension: {result['vector_dimension']}")
    print(f"Distance metric: {result['distance_metric']}")
    
    return result


def main():
    """Demo the Memory API."""
    print("=" * 60)
    print("Memory API Demo")
    print("=" * 60)
    
    # Example 1: Add a personal conversation
    print("\n\n1. Adding personal conversation memory...")
    messages1 = [
        {"role": "user", "content": "My name is Alice and I love Python programming."},
        {"role": "assistant", "content": "Nice to meet you, Alice! Python is a great language."},
        {"role": "user", "content": "I'm working on a machine learning project using scikit-learn."},
        {"role": "assistant", "content": "That's exciting! Scikit-learn is excellent for ML."}
    ]
    result1 = add_memory(messages1, user_id="alice", metadata={"topic": "programming"})
    memory_id_1 = result1["memory_id"]
    
    # Example 2: Add another conversation
    print("\n\n2. Adding another conversation...")
    messages2 = [
        {"role": "user", "content": "I'm planning a trip to Japan next summer."},
        {"role": "assistant", "content": "That sounds wonderful! Have you decided which cities to visit?"},
        {"role": "user", "content": "I want to see Tokyo, Kyoto, and maybe Osaka."},
        {"role": "assistant", "content": "Great choices! Don't miss the temples in Kyoto."}
    ]
    result2 = add_memory(messages2, user_id="alice", metadata={"topic": "travel"})
    
    # Wait a moment for indexing
    print("\n\nWaiting for indexing...")
    time.sleep(2)
    
    # Example 3: Search for programming-related memories
    print("\n\n3. Searching for programming memories...")
    search_memory("What programming languages does Alice like?", user_id="alice", limit=3)
    
    # Example 4: Search for travel-related memories
    print("\n\n4. Searching for travel plans...")
    search_memory("Where is Alice traveling?", user_id="alice", limit=3)
    
    # Example 5: Search without user filter
    print("\n\n5. Searching across all users...")
    search_memory("machine learning", limit=3)
    
    # Example 6: Compare with and without temporal decay
    print("\n\n6. Comparing temporal decay effect...")
    print("\nWith temporal decay:")
    search_memory("Python", user_id="alice", limit=2, use_temporal_decay=True)
    
    print("\nWithout temporal decay:")
    search_memory("Python", user_id="alice", limit=2, use_temporal_decay=False)
    
    # Example 7: Get statistics
    print("\n\n7. Getting memory statistics...")
    get_memory_stats()
    
    # Example 8: Delete a memory
    print("\n\n8. Deleting a memory...")
    forget_memory(memory_id_1)
    
    # Verify deletion
    print("\n\n9. Verifying deletion with updated stats...")
    get_memory_stats()
    
    print("\n\n" + "=" * 60)
    print("Demo completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except httpx.HTTPError as e:
        print(f"\nError: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response: {e.response.text}")
    except Exception as e:
        print(f"\nUnexpected error: {e}")
