#!/usr/bin/env python3
"""
Simple test script to verify the API is working correctly.
"""

import requests
import json
import time

API_BASE_URL = "http://localhost:8000"


def test_health():
    """Test the health endpoint."""
    print("Testing /health endpoint...")
    response = requests.get(f"{API_BASE_URL}/health")
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    print()


def test_chat_completion():
    """Test the chat completions endpoint."""
    print("Testing /v1/chat/completions endpoint...")
    
    payload = {
        "model": "llama-3.3-8b-instruct",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "What is the capital of France?"}
        ],
        "max_tokens": 100,
        "temperature": 0.7
    }
    
    start_time = time.time()
    response = requests.post(
        f"{API_BASE_URL}/v1/chat/completions",
        json=payload,
        timeout=300
    )
    latency = (time.time() - start_time) * 1000
    
    print(f"Status: {response.status_code}")
    print(f"Latency: {latency:.2f}ms")
    
    if response.status_code == 200:
        data = response.json()
        print(f"\nResponse:")
        print(f"  ID: {data['id']}")
        print(f"  Model: {data['model']}")
        print(f"  Message: {data['choices'][0]['message']['content']}")
        print(f"  Usage: {data['usage']}")
    else:
        print(f"Error: {response.text}")
    
    print()


def test_chat_completion_stream():
    """Test streaming chat completions endpoint."""
    print("Testing /v1/chat/completions endpoint (stream=true)...")

    payload = {
        "model": "llama-3.3-8b-instruct",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Say hello in one short sentence."}
        ],
        "max_tokens": 60,
        "temperature": 0.7,
        "stream": True
    }

    response = requests.post(
        f"{API_BASE_URL}/v1/chat/completions",
        json=payload,
        timeout=300,
        stream=True
    )

    print(f"Status: {response.status_code}")

    if response.status_code != 200:
        print(f"Error: {response.text}")
        print()
        return

    chunks = []
    done_seen = False
    for line in response.iter_lines(decode_unicode=True):
        if not line:
            continue
        if line.startswith("data: "):
            data = line[len("data: "):]
            chunks.append(data)
            if data == "[DONE]":
                done_seen = True
                break

    print(f"Received chunks: {len(chunks)}")
    print(f"DONE marker received: {done_seen}")
    if chunks:
        print(f"First chunk: {chunks[0]}")
    print()


def test_metrics():
    """Test the metrics endpoint."""
    print("Testing /metrics endpoint...")
    response = requests.get(f"{API_BASE_URL}/metrics")
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    print()


if __name__ == "__main__":
    print("=" * 60)
    print("API Testing Script")
    print("=" * 60)
    print()
    
    try:
        test_health()
        test_chat_completion()
        test_chat_completion_stream()
        test_metrics()
        
        print("=" * 60)
        print("All tests completed!")
        print("=" * 60)
        
    except requests.exceptions.ConnectionError:
        print("❌ Error: Could not connect to the API.")
        print("   Make sure the API server is running on", API_BASE_URL)
    except Exception as e:
        print(f"❌ Error: {e}")
