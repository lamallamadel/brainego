#!/usr/bin/env python3
"""
Test script for Feedback Collection System.
Demonstrates all feedback API endpoints and functionality.
"""

import os
import sys
import json
import time
from datetime import datetime, timedelta
import httpx

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")


def test_add_feedback():
    """Test adding feedback with thumbs-up/down."""
    print("\n=== Testing Add Feedback ===")
    
    test_cases = [
        {
            "query": "Write a Python function to calculate fibonacci numbers",
            "response": "Here's a Python function:\n\ndef fibonacci(n):\n    if n <= 1:\n        return n\n    return fibonacci(n-1) + fibonacci(n-2)",
            "model": "qwen-2.5-coder-7b",
            "rating": 1,
            "memory_used": 1024000,
            "tools_called": ["code_generator", "syntax_validator"],
            "intent": "code",
            "project": "test-project-1",
            "user_id": "user-123",
            "session_id": "session-abc"
        },
        {
            "query": "Explain quantum computing",
            "response": "Quantum computing is a revolutionary approach...",
            "model": "llama-3.3-8b-instruct",
            "rating": 1,
            "intent": "general",
            "project": "test-project-1",
            "user_id": "user-123",
            "session_id": "session-abc"
        },
        {
            "query": "Solve this complex math problem",
            "response": "The answer is incorrect calculation...",
            "model": "deepseek-r1-distill-qwen-7b",
            "rating": -1,
            "memory_used": 2048000,
            "intent": "reasoning",
            "project": "test-project-1",
            "user_id": "user-456",
            "session_id": "session-def"
        }
    ]
    
    feedback_ids = []
    
    for i, case in enumerate(test_cases):
        print(f"\n--- Test Case {i+1} ---")
        print(f"Rating: {'👍 Thumbs Up' if case['rating'] == 1 else '👎 Thumbs Down'}")
        print(f"Model: {case['model']}")
        print(f"Intent: {case['intent']}")
        
        try:
            response = httpx.post(
                f"{API_BASE_URL}/v1/feedback",
                json=case,
                timeout=10.0
            )
            response.raise_for_status()
            result = response.json()
            
            print(f"✓ Feedback added: {result['feedback_id']}")
            print(f"  Timestamp: {result['timestamp']}")
            feedback_ids.append(result['feedback_id'])
        except Exception as e:
            print(f"✗ Error: {e}")
    
    return feedback_ids


def test_get_feedback(feedback_id):
    """Test retrieving feedback by ID."""
    print(f"\n=== Testing Get Feedback: {feedback_id} ===")
    
    try:
        response = httpx.get(
            f"{API_BASE_URL}/v1/feedback/{feedback_id}",
            timeout=10.0
        )
        response.raise_for_status()
        result = response.json()
        
        print(f"✓ Retrieved feedback:")
        print(f"  Query: {result['query'][:50]}...")
        print(f"  Model: {result['model']}")
        print(f"  Rating: {'👍' if result['rating'] == 1 else '👎'}")
        print(f"  Intent: {result['intent']}")
        print(f"  Memory Used: {result['memory_used']} bytes")
        print(f"  Tools Called: {result['tools_called']}")
    except Exception as e:
        print(f"✗ Error: {e}")


def test_update_feedback(feedback_id):
    """Test updating feedback."""
    print(f"\n=== Testing Update Feedback: {feedback_id} ===")
    
    try:
        update_data = {
            "intent": "code_review",
            "metadata": {"updated": True, "reviewer": "test-user"}
        }
        
        response = httpx.put(
            f"{API_BASE_URL}/v1/feedback/{feedback_id}",
            json=update_data,
            timeout=10.0
        )
        response.raise_for_status()
        result = response.json()
        
        print(f"✓ Feedback updated: {result['feedback_id']}")
    except Exception as e:
        print(f"✗ Error: {e}")


def test_get_accuracy():
    """Test getting model accuracy metrics."""
    print("\n=== Testing Model Accuracy Metrics ===")
    
    test_filters = [
        {},
        {"model": "qwen-2.5-coder-7b"},
        {"intent": "code"},
        {"model": "llama-3.3-8b-instruct", "intent": "general"}
    ]
    
    for filters in test_filters:
        print(f"\n--- Filters: {filters or 'None'} ---")
        
        try:
            response = httpx.get(
                f"{API_BASE_URL}/v1/feedback/accuracy",
                params=filters,
                timeout=10.0
            )
            response.raise_for_status()
            results = response.json()
            
            if results:
                for metric in results:
                    print(f"  Model: {metric['model']}")
                    print(f"  Intent: {metric['intent']}")
                    print(f"  Project: {metric['project']}")
                    print(f"  Accuracy: {metric['accuracy_percentage']:.2f}%")
                    print(f"  Feedback: {metric['positive_feedback']}👍 / {metric['negative_feedback']}👎 (total: {metric['total_feedback']})")
                    print()
            else:
                print("  No metrics found")
        except Exception as e:
            print(f"✗ Error: {e}")


def test_get_stats():
    """Test getting feedback statistics."""
    print("\n=== Testing Feedback Statistics ===")
    
    test_params = [
        {"days": 7},
        {"model": "qwen-2.5-coder-7b", "days": 30},
        {"intent": "code", "days": 7}
    ]
    
    for params in test_params:
        print(f"\n--- Params: {params} ---")
        
        try:
            response = httpx.get(
                f"{API_BASE_URL}/v1/feedback/stats",
                params=params,
                timeout=10.0
            )
            response.raise_for_status()
            stats = response.json()
            
            print(f"  Total Feedback: {stats['total_feedback']}")
            print(f"  Positive: {stats['positive_count']} ({stats['positive_percentage']:.2f}%)")
            print(f"  Negative: {stats['negative_count']}")
            print(f"  Avg Memory: {stats['avg_memory_used']} bytes")
            print(f"  Unique Users: {stats['unique_users']}")
            print(f"  Unique Sessions: {stats['unique_sessions']}")
        except Exception as e:
            print(f"✗ Error: {e}")


def test_export_finetuning():
    """Test exporting fine-tuning dataset."""
    print("\n=== Testing Fine-tuning Dataset Export ===")
    
    output_path = "/tmp/finetuning_dataset.jsonl"
    
    # Calculate date range (last 7 days)
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=7)
    
    export_request = {
        "output_path": output_path,
        "start_date": start_date.isoformat() + "Z",
        "end_date": end_date.isoformat() + "Z",
        "format": "jsonl"
    }
    
    print(f"Export Range: {start_date.date()} to {end_date.date()}")
    
    try:
        response = httpx.post(
            f"{API_BASE_URL}/v1/feedback/export/finetuning",
            json=export_request,
            timeout=30.0
        )
        response.raise_for_status()
        result = response.json()
        
        print(f"✓ Dataset exported to: {result['output_path']}")
        print(f"  Total Samples: {result['total_samples']}")
        print(f"  Positive Samples: {result['positive_samples']} (2.0x weight)")
        print(f"  Negative Samples: {result['negative_samples']} (0.5x weight)")
        print(f"  Total Weight: {result['total_weight']:.2f}")
        
        # Read and display sample
        try:
            with open(output_path, 'r') as f:
                sample = json.loads(f.readline())
                print(f"\n  Sample Entry:")
                print(f"    Weight: {sample['weight']}")
                print(f"    Metadata: {sample['metadata']}")
                print(f"    Instruction: {sample['instruction']}")
                print(f"    Input chars: {len(sample['input'])}")
                print(f"    Output chars: {len(sample['output'])}")
        except Exception as e:
            print(f"  (Could not read sample: {e})")
    except Exception as e:
        print(f"✗ Error: {e}")


def test_delete_feedback(feedback_id):
    """Test deleting feedback."""
    print(f"\n=== Testing Delete Feedback: {feedback_id} ===")
    
    try:
        response = httpx.delete(
            f"{API_BASE_URL}/v1/feedback/{feedback_id}",
            timeout=10.0
        )
        response.raise_for_status()
        result = response.json()
        
        print(f"✓ Feedback deleted: {result['feedback_id']}")
    except Exception as e:
        print(f"✗ Error: {e}")


def main():
    """Run all feedback tests."""
    print("=" * 60)
    print("Feedback Collection System - Test Suite")
    print("=" * 60)
    print(f"API Base URL: {API_BASE_URL}")
    
    try:
        # Test health check
        print("\n=== Testing API Health ===")
        response = httpx.get(f"{API_BASE_URL}/health", timeout=5.0)
        response.raise_for_status()
        print("✓ API is healthy")
    except Exception as e:
        print(f"✗ API health check failed: {e}")
        print("Make sure the API server is running!")
        sys.exit(1)
    
    # Run tests
    feedback_ids = test_add_feedback()
    
    if feedback_ids:
        time.sleep(1)
        test_get_feedback(feedback_ids[0])
        test_update_feedback(feedback_ids[0])
    
    time.sleep(1)
    test_get_accuracy()
    
    time.sleep(1)
    test_get_stats()
    
    time.sleep(1)
    test_export_finetuning()
    
    # Cleanup (optional - comment out to keep test data)
    # if feedback_ids:
    #     print("\n=== Cleanup ===")
    #     for fid in feedback_ids:
    #         test_delete_feedback(fid)
    
    print("\n" + "=" * 60)
    print("All tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
