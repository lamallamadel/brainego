#!/usr/bin/env python3
"""
Tests for Memory API endpoints.
"""

import httpx
import time
import urllib.parse
import sys


API_URL = "http://localhost:8000"


def test_health():
    """Test health endpoint."""
    print("\n=== Testing Health Endpoint ===")
    response = httpx.get(f"{API_URL}/health", timeout=10.0)
    response.raise_for_status()
    result = response.json()
    print(f"Status: {result['status']}")
    print(f"Model: {result['model']}")
    return result


def test_memory_add():
    """Test adding a memory."""
    print("\n=== Testing Memory Add ===")
    
    messages = [
        {"role": "user", "content": "I live in San Francisco and work as a software engineer."},
        {"role": "assistant", "content": "That's great! San Francisco has a vibrant tech scene."},
        {"role": "user", "content": "Yes, I enjoy working on AI and machine learning projects."},
        {"role": "assistant", "content": "AI and ML are fascinating fields with lots of opportunities."}
    ]
    
    payload = {
        "messages": messages,
        "user_id": "test_user",
        "metadata": {"test": True, "category": "personal"}
    }
    
    response = httpx.post(f"{API_URL}/memory/add", json=payload, timeout=30.0)
    response.raise_for_status()
    result = response.json()
    
    print(f"Status: {result['status']}")
    print(f"Memory ID: {result['memory_id']}")
    print(f"Facts extracted: {result['facts_extracted']}")
    print(f"Timestamp: {result['timestamp']}")
    
    assert result['status'] == 'success'
    assert 'memory_id' in result
    assert result['facts_extracted'] > 0
    
    return result


def test_memory_search(user_id="test_user"):
    """Test searching memories."""
    print("\n=== Testing Memory Search ===")
    
    payload = {
        "query": "What does the user do for work?",
        "user_id": user_id,
        "limit": 5,
        "use_temporal_decay": True
    }
    
    response = httpx.post(f"{API_URL}/memory/search", json=payload, timeout=30.0)
    response.raise_for_status()
    result = response.json()
    
    print(f"Query: {result['query']}")
    print(f"Results: {len(result['results'])} memories found")
    
    if result['results']:
        for i, memory in enumerate(result['results'][:3], 1):
            print(f"\n  Memory {i}:")
            print(f"    Score: {memory.get('score', 0):.4f}")
            print(f"    Text: {memory['text'][:100]}...")
    
    assert 'results' in result
    assert isinstance(result['results'], list)
    
    return result


def test_memory_search_get(user_id="test_user"):
    """Test searching memories via GET endpoint."""
    print("\n=== Testing Memory Search (GET) ===")

    response = httpx.get(
        f"{API_URL}/memory/search",
        params={
            "query": "What does the user do for work?",
            "user_id": user_id,
            "limit": 5,
            "use_temporal_decay": True,
        },
        timeout=30.0,
    )
    response.raise_for_status()
    result = response.json()

    print(f"Query: {result['query']}")
    print(f"Results: {len(result['results'])} memories found")

    assert 'results' in result
    assert isinstance(result['results'], list)

    return result


def test_memory_search_get_urlencoded_filters(user_id="test_user"):
    """Test GET search with URL-encoded JSON filters."""
    print("\n=== Testing Memory Search (GET, URL-encoded filters) ===")

    encoded_filters = urllib.parse.quote('{"category":"personal"}', safe="")
    url = (
        f"{API_URL}/memory/search?query=software%20engineer"
        f"&user_id={user_id}&limit=5&filters={encoded_filters}"
    )
    response = httpx.get(url, timeout=30.0)
    response.raise_for_status()
    result = response.json()

    assert "results" in result
    assert isinstance(result["results"], list)
    return result


def test_memory_search_get_invalid_filters():
    """Test GET search with invalid JSON in filters."""
    print("\n=== Testing Memory Search (GET, invalid filters JSON) ===")

    response = httpx.get(
        f"{API_URL}/memory/search",
        params={
            "query": "software engineer",
            "filters": "{bad-json}",
        },
        timeout=30.0,
    )

    assert response.status_code == 400
    result = response.json()
    assert "detail" in result
    assert "Invalid filters JSON" in result["detail"]
    return result


def test_memory_stats():
    """Test getting memory statistics."""
    print("\n=== Testing Memory Stats ===")
    
    response = httpx.get(f"{API_URL}/memory/stats", timeout=30.0)
    response.raise_for_status()
    result = response.json()
    
    print(f"Collection: {result['collection_name']}")
    print(f"Qdrant points: {result['qdrant_points']}")
    print(f"Redis memories: {result['redis_memories']}")
    print(f"Vector dimension: {result['vector_dimension']}")
    
    assert 'collection_name' in result
    assert result['qdrant_points'] >= 0
    
    return result


def test_memory_forget(memory_id: str):
    """Test deleting a memory."""
    print("\n=== Testing Memory Forget ===")
    
    response = httpx.delete(f"{API_URL}/memory/forget/{memory_id}", timeout=30.0)
    response.raise_for_status()
    result = response.json()
    
    print(f"Status: {result['status']}")
    print(f"Message: {result['message']}")
    
    assert result['status'] == 'success'
    assert result['memory_id'] == memory_id
    
    return result


def test_temporal_decay():
    """Test temporal decay scoring."""
    print("\n=== Testing Temporal Decay ===")
    
    # Search with temporal decay
    payload_with = {
        "query": "software engineer",
        "user_id": "test_user",
        "limit": 5,
        "use_temporal_decay": True
    }
    
    response = httpx.post(f"{API_URL}/memory/search", json=payload_with, timeout=30.0)
    response.raise_for_status()
    result_with = response.json()
    
    # Search without temporal decay
    payload_without = {
        "query": "software engineer",
        "user_id": "test_user",
        "limit": 5,
        "use_temporal_decay": False
    }
    
    response = httpx.post(f"{API_URL}/memory/search", json=payload_without, timeout=30.0)
    response.raise_for_status()
    result_without = response.json()
    
    print(f"With temporal decay: {len(result_with['results'])} results")
    if result_with['results']:
        print(f"  Top score: {result_with['results'][0].get('score', 0):.4f}")
        if 'cosine_score' in result_with['results'][0]:
            print(f"  Cosine: {result_with['results'][0]['cosine_score']:.4f}")
            print(f"  Temporal: {result_with['results'][0]['temporal_score']:.4f}")
    
    print(f"\nWithout temporal decay: {len(result_without['results'])} results")
    if result_without['results']:
        print(f"  Top score: {result_without['results'][0].get('score', 0):.4f}")
    
    return result_with, result_without


def run_tests():
    """Run all memory API tests."""
    print("=" * 60)
    print("Memory API Tests")
    print("=" * 60)
    
    try:
        # Test health
        test_health()
        
        # Test adding memory
        add_result = test_memory_add()
        memory_id = add_result['memory_id']
        
        # Wait for indexing
        print("\nWaiting for indexing...")
        time.sleep(2)
        
        # Test searching
        test_memory_search()
        
        # Test temporal decay
        test_temporal_decay()

        # Test GET search
        test_memory_search_get()
        test_memory_search_get_urlencoded_filters()
        test_memory_search_get_invalid_filters()
        
        # Test statistics
        stats_before = test_memory_stats()
        
        # Test deletion
        test_memory_forget(memory_id)
        
        # Wait and verify deletion
        time.sleep(1)
        stats_after = test_memory_stats()
        
        print("\n" + "=" * 60)
        print("All tests passed successfully!")
        print("=" * 60)
        
        return True
        
    except httpx.HTTPError as e:
        print(f"\n❌ Test failed with HTTP error: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response: {e.response.text}")
        return False
    except AssertionError as e:
        print(f"\n❌ Test assertion failed: {e}")
        return False
    except Exception as e:
        print(f"\n❌ Test failed with unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
