#!/usr/bin/env python3
"""
Example: Batch processing multiple prompts efficiently
Demonstrates how to leverage MAX Serve's batching capabilities
"""

import asyncio
import httpx
import time
from typing import List, Dict
import json


async def send_chat_request(
    client: httpx.AsyncClient,
    request_id: int,
    messages: List[Dict[str, str]]
) -> tuple[int, str, float]:
    """Send a single chat request and measure latency."""
    
    url = "http://localhost:8000/v1/chat/completions"
    payload = {
        "model": "llama-3.3-8b-instruct",
        "messages": messages,
        "max_tokens": 100
    }
    
    start_time = time.time()
    
    try:
        response = await client.post(url, json=payload)
        latency = (time.time() - start_time) * 1000
        
        if response.status_code == 200:
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            return request_id, content, latency
        else:
            return request_id, f"Error: HTTP {response.status_code}", latency
    
    except Exception as e:
        latency = (time.time() - start_time) * 1000
        return request_id, f"Error: {e}", latency


async def batch_process_prompts(prompts: List[str], concurrency: int = 10):
    """
    Process multiple prompts concurrently using batch processing.
    
    Args:
        prompts: List of user prompts to process
        concurrency: Number of concurrent requests (should match batch size)
    """
    
    print(f"Processing {len(prompts)} prompts with concurrency={concurrency}")
    print("=" * 60)
    
    messages_list = [
        [{"role": "user", "content": prompt}]
        for prompt in prompts
    ]
    
    start_time = time.time()
    
    async with httpx.AsyncClient(timeout=300.0) as client:
        # Create tasks for all requests
        tasks = [
            send_chat_request(client, i, messages)
            for i, messages in enumerate(messages_list)
        ]
        
        # Execute all tasks concurrently
        results = await asyncio.gather(*tasks)
    
    total_time = time.time() - start_time
    
    print(f"\n✅ Completed in {total_time:.2f} seconds")
    print(f"📊 Throughput: {len(prompts) / total_time:.2f} requests/second\n")
    
    # Display results
    print("Results:")
    print("-" * 60)
    
    latencies = []
    for req_id, content, latency in results:
        latencies.append(latency)
        print(f"\nRequest {req_id} ({latency:.0f}ms):")
        print(f"  {content[:100]}..." if len(content) > 100 else f"  {content}")
    
    # Statistics
    avg_latency = sum(latencies) / len(latencies)
    print(f"\n📈 Latency Statistics:")
    print(f"  Average: {avg_latency:.2f}ms")
    print(f"  Min: {min(latencies):.2f}ms")
    print(f"  Max: {max(latencies):.2f}ms")


async def main():
    """Example usage of batch processing."""
    
    print("Batch Processing Example")
    print("=" * 60)
    print("\nThis example demonstrates efficient batch processing")
    print("using MAX Serve's batching capabilities (max_batch_size=32)\n")
    
    # Example prompts
    prompts = [
        "What is artificial intelligence?",
        "Explain machine learning in one sentence.",
        "What is the capital of France?",
        "How does photosynthesis work?",
        "What is quantum computing?",
        "Explain blockchain technology briefly.",
        "What is the speed of light?",
        "How do neural networks work?",
        "What is cryptocurrency?",
        "Explain cloud computing in simple terms.",
    ]
    
    # Process with different concurrency levels
    for concurrency in [5, 10]:
        print(f"\n{'='*60}")
        print(f"Testing with concurrency = {concurrency}")
        print(f"{'='*60}\n")
        
        await batch_process_prompts(prompts, concurrency=concurrency)
        
        # Wait between tests
        await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())
